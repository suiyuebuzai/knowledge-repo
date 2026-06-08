"""
索引本地文档目录，将文档向量化后存入 ChromaDB；或扫描目录生成文档索引。

用法：
    python ingest.py                          # 索引 config.DOCS_DIR
    python ingest.py --dir ./my_docs          # 索引指定目录

    python ingest.py find                     # 扫描 config.DOCS_DIR，输出 docs_index.md
    python ingest.py find --dir ./my_docs     # 扫描指定目录
    python ingest.py find --query 财务        # 模糊过滤：文件名含"财务"
    python ingest.py find --ext .md .txt      # 指定格式（默认 .pdf/.docx/.txt/.md）
    python ingest.py find --out my_index.md   # 指定输出文件
    python ingest.py find --no-recursive      # 仅扫描顶层，不递归
"""
import argparse
import fnmatch
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Set

import config

SUPPORTED = {
    ".pdf", ".docx", ".txt", ".md",
    ".xlsx", ".xls", ".pptx",
    ".csv", ".html", ".htm",
}
FIND_SUPPORTED = SUPPORTED


# ─────────────────────────── ingest ───────────────────────────

def ingest_directory(docs_dir: str = config.DOCS_DIR) -> None:
    import chunker  # noqa: PLC0415  -- 延迟导入，避免 find 子命令加载 ML 依赖
    import embedder
    import store

    files = [f for f in Path(docs_dir).iterdir() if f.suffix.lower() in SUPPORTED]
    if not files:
        print(f"[WARN] {docs_dir} 中没有找到支持的文档（{' / '.join(sorted(SUPPORTED))}）")
        return

    print(f"找到 {len(files)} 个文档，开始解析...")
    all_chunks = []
    for f in files:
        try:
            chunks = chunker.load_and_chunk(str(f))
            all_chunks.extend(chunks)
            print(f"  [OK] {f.name}: {len(chunks)} 个 chunk")
        except Exception as e:
            print(f"  [SKIP] {f.name}: {e}", file=sys.stderr)

    if not all_chunks:
        print("[WARN] 没有成功解析任何文档")
        return

    print(f"\n向量化 {len(all_chunks)} 个 chunk（本地推理，首次较慢）...")
    texts = [c["text"] for c in all_chunks]
    embeddings = embedder.embed(texts)

    print("写入 ChromaDB ...")
    store.upsert(all_chunks, embeddings)
    print(f"\n[OK] 索引完成，共 {len(all_chunks)} 个 chunk 写入 {config.CHROMA_DIR}")


# ─────────────────────────── find ───────────────────────────

def find_documents(
    root_dir: str,
    extensions: Optional[Set[str]] = None,
    query: Optional[str] = None,
    recursive: bool = True,
) -> List[Path]:
    """递归扫描 root_dir，返回符合格式的文档列表。

    Args:
        root_dir:   要扫描的根目录。
        extensions: 允许的扩展名集合，如 {".pdf", ".md"}；None 时使用 FIND_SUPPORTED。
        query:      文件名模糊过滤关键词或 glob 通配符（如 "财务"、"*.pdf"）。
        recursive:  是否递归子目录，默认 True。
    """
    exts = {
        (e if e.startswith(".") else f".{e}").lower()
        for e in extensions
    } if extensions else FIND_SUPPORTED

    root = Path(root_dir)
    if not root.exists():
        print(f"[ERROR] 目录不存在：{root_dir}", file=sys.stderr)
        return []

    glob_pattern = "**/*" if recursive else "*"
    files = [f for f in root.glob(glob_pattern) if f.is_file() and f.suffix.lower() in exts]

    if query:
        q = query.lower()
        if any(c in q for c in ("*", "?", "[")):
            # glob 通配符模式
            files = [f for f in files if fnmatch.fnmatch(f.name.lower(), q)]
        else:
            # 普通子串模糊匹配
            files = [f for f in files if q in f.name.lower()]

    return sorted(files)


def _fmt_size(size_bytes: int) -> str:
    """将字节数格式化为易读字符串。"""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def write_index_md(
    files: List[Path],
    output_path: str,
    root_dir: str,
    query: Optional[str] = None,
) -> None:
    """将文档列表写入 Markdown 索引文件，按子目录分组。"""
    root = Path(root_dir).resolve()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 按父目录分组
    groups: dict[str, list[Path]] = defaultdict(list)
    for f in files:
        try:
            rel = f.relative_to(root)
            group_key = str(rel.parent) if str(rel.parent) != "." else "（根目录）"
        except ValueError:
            group_key = str(f.parent)
        groups[group_key].append(f)

    lines: list[str] = [
        "# 文档索引",
        "",
        f"> **根目录**：`{root_dir}`  ",
        f"> **生成时间**：{now}  ",
        f"> **共 {len(files)} 个文档**" + (f"，过滤关键词：`{query}`" if query else ""),
        "",
    ]

    # 目录导航（超过 3 组时显示）
    if len(groups) > 3:
        lines += ["## 目录", ""]
        for group in sorted(groups):
            anchor = group.replace(" ", "-").replace("（", "").replace("）", "").replace("/", "-").replace("\\", "-")
            lines.append(f"- [{group}](#{anchor})（{len(groups[group])} 个）")
        lines.append("")

    # 各分组明细
    for group in sorted(groups):
        lines += [f"## {group}", ""]
        lines += ["| # | 文件名 | 类型 | 大小 | 修改时间 | 相对路径 |",
                  "|---|--------|------|------|----------|----------|"]
        for i, f in enumerate(sorted(groups[group]), 1):
            try:
                rel_path = f.relative_to(root)
            except ValueError:
                rel_path = f
            stat = f.stat()
            mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d")
            size = _fmt_size(stat.st_size)
            lines.append(
                f"| {i} | {f.name} | `{f.suffix.upper()}` | {size} | {mtime} | `{rel_path}` |"
            )
        lines.append("")

    output = Path(output_path)
    output.write_text("\n".join(lines), encoding="utf-8")
    print(f"[OK] 索引已写入 {output_path}（{len(files)} 个文档，{len(groups)} 个目录组）")


# ─────────────────────────── CLI ───────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="知识库工具：索引文档 或 扫描生成文档索引",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    # ── ingest 子命令（默认行为）──
    p_ingest = sub.add_parser("ingest", help="向量化文档并写入 ChromaDB")
    p_ingest.add_argument("--dir", default=config.DOCS_DIR, help="文档目录路径")

    # ── find 子命令 ──
    p_find = sub.add_parser("find", help="扫描目录，生成文档列表 Markdown")
    p_find.add_argument("--dir", default=config.DOCS_DIR, help="要扫描的根目录")
    p_find.add_argument("--out", default="docs_index.md", help="输出 Markdown 文件路径")
    p_find.add_argument(
        "--ext", nargs="+", metavar="EXT",
        help="限定扩展名，如 --ext .pdf .md（默认 .pdf .docx .txt .md）",
    )
    p_find.add_argument("--query", "-q", default=None, help="文件名模糊过滤（支持子串或 * ? 通配符）")
    p_find.add_argument("--no-recursive", action="store_true", help="仅扫描顶层，不递归子目录")
    p_find.add_argument("--print", action="store_true", dest="print_list", help="同时在终端打印文件列表")

    # 顶层保留 --dir 以向后兼容（无子命令时执行 ingest）
    parser.add_argument("--dir", default=config.DOCS_DIR, help=argparse.SUPPRESS)

    return parser


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "find":
        exts = set(args.ext) if args.ext else None
        files = find_documents(
            root_dir=args.dir,
            extensions=exts,
            query=args.query,
            recursive=not args.no_recursive,
        )
        if not files:
            print(f"[WARN] 未找到符合条件的文档（目录：{args.dir}，关键词：{args.query}）")
            sys.exit(0)

        if args.print_list:
            print(f"\n找到 {len(files)} 个文档：")
            for f in files:
                print(f"  {f}")
            print()

        write_index_md(files, output_path=args.out, root_dir=args.dir, query=args.query)

    else:
        # 无子命令 或 ingest 子命令，均执行索引
        ingest_directory(args.dir)
