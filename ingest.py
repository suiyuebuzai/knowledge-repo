"""
索引本地文档目录，将文档向量化后存入 ChromaDB。

用法：
    python ingest.py                  # 索引 config.DOCS_DIR
    python ingest.py --dir ./my_docs  # 索引指定目录
"""
import argparse
import sys
from pathlib import Path

import config
import chunker
import embedder
import store

SUPPORTED = {".pdf", ".docx", ".txt"}


def ingest_directory(docs_dir: str = config.DOCS_DIR) -> None:
    files = [f for f in Path(docs_dir).iterdir() if f.suffix.lower() in SUPPORTED]
    if not files:
        print(f"[WARN] {docs_dir} 中没有找到支持的文档（.pdf / .docx / .txt）")
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="索引本地文档到知识库")
    parser.add_argument("--dir", default=config.DOCS_DIR, help="文档目录路径")
    args = parser.parse_args()
    ingest_directory(args.dir)
