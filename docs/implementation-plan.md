# knowledge-server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建 knowledge-server，让 AI Agent 通过 MCP 工具对本地文档（PDF/Word/TXT）进行语义检索和 RAG 问答，并提供 Web 界面进行文档问答、语义检索和上传索引。

**Architecture:** 手写 RAG 流水线，不依赖 LlamaIndex 等重框架。索引时：chunker 解析文档 → embedder 本地向量化 → store 写入 ChromaDB。查询时：retriever 组合 embedder + store，server 暴露 2 个 MCP 工具。Web App (FastAPI) 直接 import 现有模块，Jinja2 服务端渲染页面，问答使用 SSE 流式输出。

**Tech Stack:** `sentence-transformers`（本地 Embedding）, `chromadb`（向量数据库）, `pypdf`（PDF 解析）, `python-docx`（Word 解析）, `mcp[cli]` + `FastMCP`（MCP Server）, `anthropic` SDK（ask_document 内部调 Claude）, `fastapi` + `uvicorn` + `jinja2` + `python-multipart`（Web App）

---

## File Map

| 文件 | 职责 |
|------|------|
| `knowledge-server/config.py` | 配置常量（路径、模型名、分块参数、WEB_PORT） |
| `knowledge-server/embedder.py` | sentence-transformers 向量化，纯函数 |
| `knowledge-server/store.py` | ChromaDB 读写封装 |
| `knowledge-server/chunker.py` | 文档解析与分块 |
| `knowledge-server/retriever.py` | 组合 embedder + store，供 server 调用 |
| `knowledge-server/ingest.py` | 扫描目录、索引所有文档，命令行触发 |
| `knowledge-server/server.py` | FastMCP Server，2 个工具 |
| `knowledge-server/web_app.py` | FastAPI 应用入口，所有 Web 路由 |
| `knowledge-server/templates/base.html` | Jinja2 公共布局（导航栏 + 内容容器） |
| `knowledge-server/templates/ask.html` | 问答页（输入框 + SSE 流式展示区） |
| `knowledge-server/templates/search.html` | 检索页（搜索框 + 结果表格） |
| `knowledge-server/templates/upload.html` | 上传页（文件选择 + 已索引列表） |
| `knowledge-server/static/style.css` | 全局样式 |
| `knowledge-server/tests/conftest.py` | pytest 路径配置 |
| `knowledge-server/tests/test_embedder.py` | embedder 单元测试 |
| `knowledge-server/tests/test_store.py` | store 单元测试 |
| `knowledge-server/tests/test_chunker.py` | chunker 单元测试 |
| `knowledge-server/tests/test_retriever.py` | retriever 集成测试 |

---

## Part 1: MCP Server 核心模块

### Task 1: 目录结构 + 依赖 + config.py

**Files:**
- Create: `knowledge-server/config.py`
- Create: `knowledge-server/docs_input/.gitkeep`
- Create: `knowledge-server/tests/conftest.py`

- [ ] **Step 1: 创建目录结构**

```bash
cd C:/1AI/personal-md-database/yangli2026/work/20260519mcp
mkdir -p knowledge-server/docs_input
mkdir -p knowledge-server/chroma_db
mkdir -p knowledge-server/tests
```

- [ ] **Step 2: 安装依赖**

```bash
C:/1AI/.pvenv/Scripts/python.exe -m pip install sentence-transformers chromadb pypdf python-docx
```

首次运行 sentence-transformers 会下载模型（~420MB），需要网络。

- [ ] **Step 3: 创建 config.py**

```python
# knowledge-server/config.py
from pathlib import Path

BASE_DIR = Path(__file__).parent

DOCS_DIR    = str(BASE_DIR / "docs_input")
CHROMA_DIR  = str(BASE_DIR / "chroma_db")

EMBED_MODEL  = "paraphrase-multilingual-MiniLM-L12-v2"  # 384 维，支持中文
CLAUDE_MODEL = "claude-sonnet-4-6"

CHUNK_SIZE    = 500   # 每块最大字符数
CHUNK_OVERLAP = 50    # 相邻块重叠字符数（保留上下文）
TOP_K         = 5     # 检索返回 top-k 个 chunk
```

- [ ] **Step 4: 创建 tests/conftest.py（确保测试能 import 父目录模块）**

```python
# knowledge-server/tests/conftest.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
```

- [ ] **Step 5: 验证 config 可导入**

```bash
cd knowledge-server
C:/1AI/.pvenv/Scripts/python.exe -c "import config; print(config.EMBED_MODEL)"
```

预期输出：`paraphrase-multilingual-MiniLM-L12-v2`

- [ ] **Step 6: Commit**

```bash
git add knowledge-server/
git commit -m "feat: scaffold knowledge-server structure and config"
```

---

### Task 2: embedder.py（TDD）

**Files:**
- Create: `knowledge-server/embedder.py`
- Create: `knowledge-server/tests/test_embedder.py`

- [ ] **Step 1: 写失败测试**

```python
# knowledge-server/tests/test_embedder.py
import embedder


def test_embed_returns_list_of_floats():
    result = embedder.embed(["hello world"])
    assert isinstance(result, list)
    assert len(result) == 1
    assert isinstance(result[0], list)
    assert isinstance(result[0][0], float)


def test_embed_dimension_is_384():
    result = embedder.embed(["测试文本"])
    assert len(result[0]) == 384


def test_embed_batch():
    texts = ["文本一", "文本二", "文本三"]
    result = embedder.embed(texts)
    assert len(result) == 3
    assert all(len(v) == 384 for v in result)
```

- [ ] **Step 2: 运行，确认失败**

```bash
cd knowledge-server
C:/1AI/.pvenv/Scripts/python.exe -m pytest tests/test_embedder.py -v
```

预期：`ModuleNotFoundError: No module named 'embedder'`

- [ ] **Step 3: 实现 embedder.py**

```python
# knowledge-server/embedder.py
from sentence_transformers import SentenceTransformer
import config

_model = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(config.EMBED_MODEL)
    return _model


def embed(texts: list[str]) -> list[list[float]]:
    """批量向量化文本，返回 384 维 float 列表。"""
    model = _get_model()
    return model.encode(texts, normalize_embeddings=True).tolist()
```

- [ ] **Step 4: 运行，确认通过**

```bash
C:/1AI/.pvenv/Scripts/python.exe -m pytest tests/test_embedder.py -v
```

预期：3 个测试全部 PASS（首次运行会下载模型，需等待）

- [ ] **Step 5: Commit**

```bash
git add knowledge-server/embedder.py knowledge-server/tests/test_embedder.py
git commit -m "feat: add embedder with sentence-transformers"
```

---

### Task 3: store.py（TDD）

**Files:**
- Create: `knowledge-server/store.py`
- Create: `knowledge-server/tests/test_store.py`

- [ ] **Step 1: 写失败测试**

```python
# knowledge-server/tests/test_store.py
import pytest
import store
import embedder


@pytest.fixture(autouse=True)
def temp_chroma(tmp_path, monkeypatch):
    """每个测试用独立的临时 ChromaDB，避免相互污染。"""
    import config
    monkeypatch.setattr(config, "CHROMA_DIR", str(tmp_path / "chroma"))
    store._collection = None  # 重置单例
    yield
    store._collection = None


def test_upsert_and_count():
    chunks = [
        {"id": "doc1#0", "text": "Python 是一种编程语言", "metadata": {"source": "doc1.txt", "page": 0}},
        {"id": "doc1#1", "text": "它语法简洁、易于学习", "metadata": {"source": "doc1.txt", "page": 0}},
    ]
    embeddings = embedder.embed([c["text"] for c in chunks])
    store.upsert(chunks, embeddings)
    assert store._get_collection().count() == 2


def test_search_returns_relevant_result():
    chunks = [
        {"id": "a#0", "text": "合同有效期为一年", "metadata": {"source": "合同.txt", "page": 0}},
        {"id": "b#0", "text": "Python 是编程语言", "metadata": {"source": "技术.txt", "page": 0}},
    ]
    embeddings = embedder.embed([c["text"] for c in chunks])
    store.upsert(chunks, embeddings)

    query_emb = embedder.embed(["合同期限"])[0]
    results = store.search(query_emb, top_k=1)

    assert len(results) == 1
    assert results[0]["source"] == "合同.txt"
    assert 0 <= results[0]["score"] <= 1


def test_search_empty_collection_returns_empty():
    query_emb = embedder.embed(["test"])[0]
    results = store.search(query_emb, top_k=5)
    assert results == []


def test_upsert_same_id_overwrites():
    chunk = {"id": "x#0", "text": "原始内容", "metadata": {"source": "x.txt", "page": 0}}
    emb = embedder.embed([chunk["text"]])
    store.upsert([chunk], emb)

    chunk_updated = {"id": "x#0", "text": "更新内容", "metadata": {"source": "x.txt", "page": 0}}
    emb_updated = embedder.embed([chunk_updated["text"]])
    store.upsert([chunk_updated], emb_updated)

    assert store._get_collection().count() == 1
```

- [ ] **Step 2: 运行，确认失败**

```bash
C:/1AI/.pvenv/Scripts/python.exe -m pytest tests/test_store.py -v
```

预期：`ModuleNotFoundError: No module named 'store'`

- [ ] **Step 3: 实现 store.py**

```python
# knowledge-server/store.py
import chromadb
import config

_collection = None


def _get_collection():
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(path=config.CHROMA_DIR)
        _collection = client.get_or_create_collection(
            "knowledge",
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def upsert(chunks: list[dict], embeddings: list[list[float]]) -> None:
    """写入 ChromaDB，相同 id 自动覆盖。"""
    col = _get_collection()
    col.upsert(
        ids=[c["id"] for c in chunks],
        documents=[c["text"] for c in chunks],
        metadatas=[c["metadata"] for c in chunks],
        embeddings=embeddings,
    )


def search(query_embedding: list[float], top_k: int) -> list[dict]:
    """语义检索，返回 top-k 最相关 chunks。集合为空时返回 []。"""
    col = _get_collection()
    count = col.count()
    if count == 0:
        return []
    actual_k = min(top_k, count)
    results = col.query(
        query_embeddings=[query_embedding],
        n_results=actual_k,
        include=["documents", "metadatas", "distances"],
    )
    output = []
    for text, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        output.append({
            "text": text,
            "source": meta.get("source", ""),
            "score": round(1 - dist, 4),  # cosine distance → similarity
        })
    return output
```

- [ ] **Step 4: 运行，确认通过**

```bash
C:/1AI/.pvenv/Scripts/python.exe -m pytest tests/test_store.py -v
```

预期：4 个测试全部 PASS

- [ ] **Step 5: Commit**

```bash
git add knowledge-server/store.py knowledge-server/tests/test_store.py
git commit -m "feat: add ChromaDB store with cosine similarity"
```

---

### Task 4: chunker.py（TDD）

**Files:**
- Create: `knowledge-server/chunker.py`
- Create: `knowledge-server/tests/test_chunker.py`

- [ ] **Step 1: 写失败测试**

```python
# knowledge-server/tests/test_chunker.py
import pytest
from pathlib import Path
import chunker
import config


def test_chunk_text_basic():
    """短文本应产生 1 个 chunk。"""
    chunks = chunker._chunk_text("Python 是一种编程语言。", source="test.txt")
    assert len(chunks) == 1
    assert chunks[0]["text"] == "Python 是一种编程语言。"
    assert chunks[0]["metadata"]["source"] == "test.txt"


def test_chunk_text_splits_long_text(monkeypatch):
    """超过 CHUNK_SIZE 的文本应拆分为多个 chunk。"""
    monkeypatch.setattr(config, "CHUNK_SIZE", 10)
    monkeypatch.setattr(config, "CHUNK_OVERLAP", 2)
    text = "A" * 25
    chunks = chunker._chunk_text(text, source="long.txt")
    assert len(chunks) > 1
    assert all(c["metadata"]["source"] == "long.txt" for c in chunks)


def test_chunk_ids_are_unique():
    text = "X" * 600
    chunks = chunker._chunk_text(text, source="dup.txt")
    ids = [c["id"] for c in chunks]
    assert len(ids) == len(set(ids))


def test_load_and_chunk_txt(tmp_path):
    txt_file = tmp_path / "sample.txt"
    txt_file.write_text("这是第一段内容。\n这是第二段内容。", encoding="utf-8")
    chunks = chunker.load_and_chunk(str(txt_file))
    assert len(chunks) >= 1
    assert chunks[0]["metadata"]["source"] == "sample.txt"
    full_text = " ".join(c["text"] for c in chunks)
    assert "第一段" in full_text


def test_load_and_chunk_unsupported_format(tmp_path):
    bad_file = tmp_path / "file.xyz"
    bad_file.write_text("content")
    with pytest.raises(ValueError, match="不支持的文件格式"):
        chunker.load_and_chunk(str(bad_file))
```

- [ ] **Step 2: 运行，确认失败**

```bash
C:/1AI/.pvenv/Scripts/python.exe -m pytest tests/test_chunker.py -v
```

预期：`ModuleNotFoundError: No module named 'chunker'`

- [ ] **Step 3: 实现 chunker.py**

```python
# knowledge-server/chunker.py
from pathlib import Path
import config


def _chunk_text(text: str, source: str) -> list[dict]:
    """将文本按 CHUNK_SIZE/OVERLAP 分块。"""
    chunks = []
    start = 0
    idx = 0
    while start < len(text):
        end = start + config.CHUNK_SIZE
        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append({
                "id": f"{source}#{idx}",
                "text": chunk_text,
                "metadata": {"source": source, "page": 0},
            })
            idx += 1
        start += config.CHUNK_SIZE - config.CHUNK_OVERLAP
    return chunks


def _load_txt(file_path: str) -> str:
    with open(file_path, encoding="utf-8") as f:
        return f.read()


def _load_pdf(file_path: str) -> str:
    from pypdf import PdfReader
    reader = PdfReader(file_path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _load_docx(file_path: str) -> str:
    from docx import Document
    doc = Document(file_path)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def load_and_chunk(file_path: str) -> list[dict]:
    """解析文档并分块。支持 .pdf / .docx / .txt。"""
    path = Path(file_path)
    suffix = path.suffix.lower()
    source = path.name

    if suffix == ".txt":
        text = _load_txt(file_path)
    elif suffix == ".pdf":
        text = _load_pdf(file_path)
    elif suffix == ".docx":
        text = _load_docx(file_path)
    else:
        raise ValueError(f"不支持的文件格式: {suffix}（仅支持 .pdf / .docx / .txt）")

    return _chunk_text(text, source)
```

- [ ] **Step 4: 运行，确认通过**

```bash
C:/1AI/.pvenv/Scripts/python.exe -m pytest tests/test_chunker.py -v
```

预期：5 个测试全部 PASS

- [ ] **Step 5: Commit**

```bash
git add knowledge-server/chunker.py knowledge-server/tests/test_chunker.py
git commit -m "feat: add document chunker for pdf/docx/txt"
```

---

### Task 5: retriever.py（TDD）

**Files:**
- Create: `knowledge-server/retriever.py`
- Create: `knowledge-server/tests/test_retriever.py`

- [ ] **Step 1: 写失败测试**

```python
# knowledge-server/tests/test_retriever.py
import pytest
import store
import retriever
import embedder
import config


@pytest.fixture(autouse=True)
def temp_chroma(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CHROMA_DIR", str(tmp_path / "chroma"))
    store._collection = None
    yield
    store._collection = None


def test_retriever_search_returns_results():
    """索引两条内容后，检索相关内容应返回正确来源。"""
    chunks = [
        {"id": "a#0", "text": "年假政策：员工每年享有10天带薪年假", "metadata": {"source": "hr.txt", "page": 0}},
        {"id": "b#0", "text": "Python 是一种编程语言", "metadata": {"source": "tech.txt", "page": 0}},
    ]
    embs = embedder.embed([c["text"] for c in chunks])
    store.upsert(chunks, embs)

    results = retriever.search("员工假期有多少天", top_k=1)
    assert len(results) == 1
    assert results[0]["source"] == "hr.txt"


def test_retriever_search_empty_returns_empty():
    results = retriever.search("任意查询", top_k=5)
    assert results == []


def test_retriever_top_k_limits_results():
    chunks = [
        {"id": f"doc#{i}", "text": f"内容 {i}", "metadata": {"source": "x.txt", "page": 0}}
        for i in range(10)
    ]
    embs = embedder.embed([c["text"] for c in chunks])
    store.upsert(chunks, embs)

    results = retriever.search("内容", top_k=3)
    assert len(results) == 3
```

- [ ] **Step 2: 运行，确认失败**

```bash
C:/1AI/.pvenv/Scripts/python.exe -m pytest tests/test_retriever.py -v
```

预期：`ModuleNotFoundError: No module named 'retriever'`

- [ ] **Step 3: 实现 retriever.py**

```python
# knowledge-server/retriever.py
import embedder
import store
import config


def search(query: str, top_k: int = config.TOP_K) -> list[dict]:
    """query → embed → ChromaDB 检索 → 返回 top-k chunks。"""
    embedding = embedder.embed([query])[0]
    return store.search(embedding, top_k)
```

- [ ] **Step 4: 运行，确认通过**

```bash
C:/1AI/.pvenv/Scripts/python.exe -m pytest tests/test_retriever.py -v
```

预期：3 个测试全部 PASS

- [ ] **Step 5: 运行全部测试，确认无回归**

```bash
C:/1AI/.pvenv/Scripts/python.exe -m pytest tests/ -v
```

预期：所有测试 PASS

- [ ] **Step 6: Commit**

```bash
git add knowledge-server/retriever.py knowledge-server/tests/test_retriever.py
git commit -m "feat: add retriever combining embedder and store"
```

---

### Task 6: ingest.py

**Files:**
- Create: `knowledge-server/ingest.py`

- [ ] **Step 1: 实现 ingest.py**

```python
# knowledge-server/ingest.py
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
            print(f"  ✓ {f.name}: {len(chunks)} 个 chunk")
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
```

- [ ] **Step 2: 放入测试文档并运行**

先放一个 TXT 测试文件：

```bash
echo "这是一份测试文档。内容包含公司年假政策：员工每年享有10天带薪年假，需提前3天申请。" > knowledge-server/docs_input/test.txt
```

然后运行索引：

```bash
cd knowledge-server
C:/1AI/.pvenv/Scripts/python.exe ingest.py
```

预期输出：
```
找到 1 个文档，开始解析...
  ✓ test.txt: 1 个 chunk
向量化 1 个 chunk（本地推理，首次较慢）...
写入 ChromaDB ...
[OK] 索引完成，共 1 个 chunk 写入 .../chroma_db
```

- [ ] **Step 3: 验证索引结果**

```bash
C:/1AI/.pvenv/Scripts/python.exe -c "
import sys; sys.path.insert(0, '.')
import store, config
col = store._get_collection()
print('chunk 数量:', col.count())
"
```

预期：`chunk 数量: 1`

- [ ] **Step 4: Commit**

```bash
git add knowledge-server/ingest.py knowledge-server/docs_input/.gitkeep
git commit -m "feat: add ingest pipeline for batch document indexing"
```

---

### Task 7: server.py + 冒烟测试

**Files:**
- Create: `knowledge-server/server.py`

- [ ] **Step 1: 实现 server.py**

```python
# knowledge-server/server.py
"""
Knowledge MCP Server

非结构化文档检索，通过 MCP 协议暴露给 Claude。

启动方式（SSE 模式）：
    C:/1AI/.pvenv/Scripts/python.exe server.py
    → 默认监听 http://localhost:8001/sse
"""
import json
import os
import sys

import anthropic
from mcp.server.fastmcp import FastMCP

import config
import retriever

mcp = FastMCP("knowledge")


@mcp.tool()
def search_documents(query: str, top_k: int = 5) -> str:
    """
    在本地知识库中语义检索相关文档片段，返回原始片段供 Claude 综合回答。
    当用户需要查找文档内容、了解某个主题时使用。

    Args:
        query:  检索关键词或问题。示例: "合同有效期条款" / "年假申请流程"
        top_k:  返回最相关片段数，默认 5，最大 20

    Returns:
        JSON 字符串，包含:
          query    原始查询词
          results  列表，每项有:
            text    文档片段原文
            source  来源文件名（如 "合同模板.pdf"）
            score   相似度（0~1，越高越相关）
    """
    try:
        results = retriever.search(query, min(top_k, 20))
        return json.dumps({"query": query, "results": results}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool()
def ask_document(question: str) -> str:
    """
    在知识库中检索相关片段，由 Claude 直接综合回答问题。
    当用户提出需要理解文档内容才能回答的问题时使用。

    Args:
        question: 自然语言问题。示例: "合同到期后如何续签？" / "年假政策是什么？"

    Returns:
        基于文档内容的答案字符串。知识库为空时提示先运行 ingest.py。
    """
    try:
        chunks = retriever.search(question, top_k=config.TOP_K)
        if not chunks:
            return "知识库中未找到相关内容，请先运行 python ingest.py 索引文档。"

        context = "\n\n".join(
            f"[{i+1}] 来源：{c['source']}\n{c['text']}"
            for i, c in enumerate(chunks)
        )
        prompt = (
            "根据以下文档片段回答问题，只使用片段中的信息，"
            "如片段中没有答案请明确说明。\n\n"
            f"{context}\n\n"
            f"问题：{question}"
        )

        client = anthropic.Anthropic(
            api_key=os.environ.get("ANTHROPIC_AUTH_TOKEN"),
            base_url=os.environ.get("ANTHROPIC_BASE_URL"),
        )
        response = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    except Exception as e:
        # 降级：返回原始片段，不抛出异常
        try:
            chunks = retriever.search(question, top_k=config.TOP_K)
            fallback = "\n\n".join(
                f"[{i+1}] {c['source']}: {c['text']}"
                for i, c in enumerate(chunks)
            )
            return f"生成失败（{e}），原始片段如下：\n\n{fallback}"
        except Exception:
            return f"服务错误：{e}"


if __name__ == "__main__":
    port = int(os.environ.get("KNOWLEDGE_SERVER_PORT", "8001"))
    mcp.run(transport="sse", port=port)
```

- [ ] **Step 2: 启动 server（后台）**

新开一个终端，运行：

```bash
cd knowledge-server
C:/1AI/.pvenv/Scripts/python.exe server.py
```

预期输出：类似 `Uvicorn running on http://0.0.0.0:8001`

- [ ] **Step 3: 冒烟测试 — 验证 search_documents**

```bash
C:/1AI/.pvenv/Scripts/python.exe -c "
import asyncio
from mcp import ClientSession
from mcp.client.sse import sse_client

async def test():
    async with sse_client('http://localhost:8001/sse') as (r, w):
        async with ClientSession(r, w) as session:
            await session.initialize()
            tools = await session.list_tools()
            print('工具列表:', [t.name for t in tools.tools])
            result = await session.call_tool('search_documents', {'query': '年假'})
            print('search_documents 结果:', result.content[0].text[:200])

asyncio.run(test())
"
```

预期：打印工具列表 `['search_documents', 'ask_document']` 和检索结果

- [ ] **Step 4: 冒烟测试 — 验证 ask_document**

```bash
C:/1AI/.pvenv/Scripts/python.exe -c "
import asyncio
from mcp import ClientSession
from mcp.client.sse import sse_client

async def test():
    async with sse_client('http://localhost:8001/sse') as (r, w):
        async with ClientSession(r, w) as session:
            await session.initialize()
            result = await session.call_tool('ask_document', {'question': '年假有多少天？'})
            print('ask_document 结果:', result.content[0].text)

asyncio.run(test())
"
```

预期：返回基于测试文档的答案"10天带薪年假"

- [ ] **Step 5: Commit**

```bash
git add knowledge-server/server.py
git commit -m "feat: add knowledge MCP server with search_documents and ask_document tools"
```

---

### Task 8: 更新 CLAUDE.md 和 Workbuddy 配置

**Files:**
- Modify: `CLAUDE.md`（目录结构部分）
- Reference: `C:/Users/li.yang3/.workbuddy/mcp.json`（手动更新）

- [ ] **Step 1: 更新 CLAUDE.md 目录结构**

在 CLAUDE.md 的目录结构中，`lakehouse-mcp-server/` 部分后面添加：

```
├── knowledge-server/
│   ├── server.py            ← MCP Server（search_documents / ask_document）
│   ├── ingest.py            ← 文档索引入口（python ingest.py 触发）
│   ├── retriever.py         ← 检索逻辑（embed + ChromaDB）
│   ├── chunker.py           ← PDF/Word/TXT 解析与分块
│   ├── embedder.py          ← sentence-transformers 向量化
│   ├── store.py             ← ChromaDB 读写
│   ├── config.py            ← 配置（路径、模型、分块参数）
│   ├── docs_input/          ← 待索引文档（不提交 git）
│   └── chroma_db/           ← 向量库（不提交 git）
```

- [ ] **Step 2: 手动更新 Workbuddy MCP 配置**

编辑 `C:/Users/li.yang3/.workbuddy/mcp.json`，添加 knowledge server：

```json
{
  "mcpServers": {
    "lakehouse": {
      "command": "C:/1AI/.pvenv/Scripts/python.exe",
      "args": ["C:/1AI/personal-md-database/yangli2026/work/20260519mcp/lakehouse-mcp-server/server.py"],
      "env": { "APP_ENV": "uat" }
    },
    "knowledge": {
      "command": "C:/1AI/.pvenv/Scripts/python.exe",
      "args": ["C:/1AI/personal-md-database/yangli2026/work/20260519mcp/knowledge-server/server.py"],
      "env": { "KNOWLEDGE_SERVER_PORT": "8001" }
    }
  }
}
```

- [ ] **Step 3: Final commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with knowledge-server structure"
```

---

## Part 2: Web App 界面

### Task 9: 项目结构 + 配置 + 基础 FastAPI 骨架

**Files:**
- Create: `knowledge-server/templates/` (目录)
- Create: `knowledge-server/static/` (目录)
- Create: `knowledge-server/static/style.css`
- Create: `knowledge-server/web_app.py`
- Modify: `knowledge-server/config.py`

- [ ] **Step 1: 创建目录**

```bash
cd C:/1AI/personal-md-database/yangli2026/work/20260519mcp/knowledge-server
mkdir -p templates static
```

- [ ] **Step 2: 修改 config.py，添加 WEB_PORT**

在 `config.py` 末尾追加：

```python
WEB_PORT = 8080   # Web 应用端口（环境变量 KNOWLEDGE_WEB_PORT 可覆盖）
```

- [ ] **Step 3: 创建 static/style.css**

```css
/* knowledge-server/static/style.css */
* { box-sizing: border-box; margin: 0; padding: 0; }

body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    line-height: 1.6;
    color: #333;
    max-width: 900px;
    margin: 0 auto;
    padding: 20px;
}

nav {
    display: flex;
    gap: 20px;
    padding: 12px 0;
    border-bottom: 2px solid #eee;
    margin-bottom: 24px;
}

nav a {
    text-decoration: none;
    color: #555;
    font-weight: 500;
    padding: 4px 8px;
    border-radius: 4px;
}

nav a:hover, nav a.active {
    color: #1a73e8;
    background: #e8f0fe;
}

h1 {
    font-size: 1.5rem;
    margin-bottom: 16px;
}

.form-group {
    display: flex;
    gap: 8px;
    margin-bottom: 16px;
}

input[type="text"], input[type="search"] {
    flex: 1;
    padding: 10px 14px;
    border: 1px solid #ddd;
    border-radius: 6px;
    font-size: 1rem;
}

button {
    padding: 10px 20px;
    background: #1a73e8;
    color: white;
    border: none;
    border-radius: 6px;
    font-size: 1rem;
    cursor: pointer;
}

button:hover { background: #1557b0; }
button:disabled { background: #ccc; cursor: not-allowed; }

.answer-box {
    background: #f8f9fa;
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    padding: 16px;
    min-height: 100px;
    white-space: pre-wrap;
    margin-bottom: 16px;
}

.sources {
    font-size: 0.9rem;
    color: #666;
}

.sources li { margin-bottom: 4px; }

table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 16px;
}

th, td {
    text-align: left;
    padding: 10px 12px;
    border-bottom: 1px solid #eee;
}

th { background: #f5f5f5; font-weight: 600; }

.score {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 0.85rem;
    font-weight: 500;
}

.score-high { background: #e6f4ea; color: #1e8e3e; }
.score-mid { background: #fef7e0; color: #b06000; }
.score-low { background: #fce8e6; color: #c5221f; }

.message {
    padding: 12px 16px;
    border-radius: 6px;
    margin-bottom: 16px;
}

.message-success { background: #e6f4ea; color: #1e8e3e; }
.message-error { background: #fce8e6; color: #c5221f; }

.file-list {
    margin-top: 16px;
    padding: 12px;
    background: #f8f9fa;
    border-radius: 6px;
}

.file-list li { margin: 4px 0; }

.chunk-text {
    max-width: 500px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
```

- [ ] **Step 4: 创建 web_app.py 骨架（仅首页路由）**

```python
# knowledge-server/web_app.py
"""
Knowledge Web App

浏览器访问本地知识库：问答、检索、上传文档。

启动：
    C:/1AI/.pvenv/Scripts/python.exe web_app.py
    -> http://localhost:8080
"""
import os
import sys
from pathlib import Path

# 确保能 import 同目录模块
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import config

app = FastAPI(title="Knowledge Web")
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@app.get("/")
async def ask_page(request: Request):
    return templates.TemplateResponse("ask.html", {"request": request})


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("KNOWLEDGE_WEB_PORT", config.WEB_PORT))
    uvicorn.run(app, host="0.0.0.0", port=port)
```

- [ ] **Step 5: 创建 templates/base.html**

```html
<!-- knowledge-server/templates/base.html -->
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Knowledge{% endblock %}</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <nav>
        <a href="/" {% if active == "ask" %}class="active"{% endif %}>问答</a>
        <a href="/search" {% if active == "search" %}class="active"{% endif %}>检索</a>
        <a href="/upload" {% if active == "upload" %}class="active"{% endif %}>上传</a>
    </nav>
    {% block content %}{% endblock %}
    {% block scripts %}{% endblock %}
</body>
</html>
```

- [ ] **Step 6: 创建 templates/ask.html（占位，仅显示标题）**

```html
<!-- knowledge-server/templates/ask.html -->
{% extends "base.html" %}
{% set active = "ask" %}
{% block title %}问答 - Knowledge{% endblock %}
{% block content %}
<h1>知识库问答</h1>
<p>页面搭建中...</p>
{% endblock %}
```

- [ ] **Step 7: 验证骨架能启动**

```bash
cd C:/1AI/personal-md-database/yangli2026/work/20260519mcp/knowledge-server
C:/1AI/.pvenv/Scripts/python.exe -c "
from web_app import app
from fastapi.testclient import TestClient
client = TestClient(app)
r = client.get('/')
print('status:', r.status_code)
print('has nav:', '<nav>' in r.text)
print('has title:', '知识库问答' in r.text)
"
```

预期输出：
```
status: 200
has nav: True
has title: True
```

- [ ] **Step 8: Commit**

```bash
git add knowledge-server/config.py knowledge-server/static/ knowledge-server/templates/ knowledge-server/web_app.py
git commit -m "feat: scaffold knowledge web app with FastAPI + Jinja2"
```

---

### Task 10: 检索页（服务端渲染，无 LLM 调用）

**Files:**
- Modify: `knowledge-server/web_app.py`
- Create: `knowledge-server/templates/search.html`

- [ ] **Step 1: 在 web_app.py 中添加检索路由**

在 `ask_page` 函数下方追加：

```python
import retriever


@app.get("/search")
async def search_page(request: Request, q: str = ""):
    results = []
    if q.strip():
        results = retriever.search(q.strip(), top_k=10)
    return templates.TemplateResponse("search.html", {
        "request": request,
        "query": q,
        "results": results,
    })
```

- [ ] **Step 2: 创建 templates/search.html**

```html
<!-- knowledge-server/templates/search.html -->
{% extends "base.html" %}
{% set active = "search" %}
{% block title %}检索 - Knowledge{% endblock %}
{% block content %}
<h1>语义检索</h1>
<form action="/search" method="get" class="form-group">
    <input type="search" name="q" value="{{ query }}" placeholder="输入关键词或问题..." autofocus>
    <button type="submit">检索</button>
</form>

{% if query and not results %}
<div class="message message-error">未找到相关内容，请尝试其他关键词或先上传文档。</div>
{% endif %}

{% if results %}
<table>
    <thead>
        <tr>
            <th>#</th>
            <th>来源</th>
            <th>相似度</th>
            <th>内容片段</th>
        </tr>
    </thead>
    <tbody>
        {% for item in results %}
        <tr>
            <td>{{ loop.index }}</td>
            <td>{{ item.source }}</td>
            <td>
                {% if item.score >= 0.7 %}
                <span class="score score-high">{{ "%.0f"|format(item.score * 100) }}%</span>
                {% elif item.score >= 0.4 %}
                <span class="score score-mid">{{ "%.0f"|format(item.score * 100) }}%</span>
                {% else %}
                <span class="score score-low">{{ "%.0f"|format(item.score * 100) }}%</span>
                {% endif %}
            </td>
            <td class="chunk-text" title="{{ item.text }}">{{ item.text[:120] }}</td>
        </tr>
        {% endfor %}
    </tbody>
</table>
{% endif %}
{% endblock %}
```

- [ ] **Step 3: 验证检索页**

```bash
cd C:/1AI/personal-md-database/yangli2026/work/20260519mcp/knowledge-server
C:/1AI/.pvenv/Scripts/python.exe -c "
from web_app import app
from fastapi.testclient import TestClient
client = TestClient(app)

# 空查询
r = client.get('/search')
print('empty status:', r.status_code)
print('has form:', '<form' in r.text)

# 有查询
r = client.get('/search?q=年假')
print('search status:', r.status_code)
print('has table:', '<table>' in r.text or '未找到' in r.text)
"
```

预期：两个请求都返回 200，有查询时展示表格或提示。

- [ ] **Step 4: Commit**

```bash
git add knowledge-server/web_app.py knowledge-server/templates/search.html
git commit -m "feat: add search page with semantic retrieval"
```

---

### Task 11: 上传页（文件上传 + 自动索引）

**Files:**
- Modify: `knowledge-server/web_app.py`
- Create: `knowledge-server/templates/upload.html`

- [ ] **Step 1: 在 web_app.py 中添加上传路由**

在文件顶部追加 import：

```python
from fastapi import UploadFile, File
from fastapi.responses import RedirectResponse
import chunker
import embedder
import store
```

在 `search_page` 函数下方追加：

```python
@app.get("/upload")
async def upload_page(request: Request, msg: str = "", error: str = ""):
    # 聚合已索引的文件列表
    indexed_files = []
    try:
        col = store._get_collection()
        if col.count() > 0:
            all_meta = col.get(include=["metadatas"])["metadatas"]
            file_chunks = {}
            for meta in all_meta:
                src = meta.get("source", "unknown")
                file_chunks[src] = file_chunks.get(src, 0) + 1
            indexed_files = [{"name": k, "chunks": v} for k, v in sorted(file_chunks.items())]
    except Exception:
        pass
    return templates.TemplateResponse("upload.html", {
        "request": request,
        "msg": msg,
        "error": error,
        "indexed_files": indexed_files,
    })


@app.post("/upload")
async def upload_files(request: Request, files: list[UploadFile] = File(...)):
    if not files or not files[0].filename:
        return RedirectResponse("/upload?error=请选择文件", status_code=303)

    results = []
    errors = []
    docs_dir = Path(config.DOCS_DIR)

    for file in files:
        suffix = Path(file.filename).suffix.lower()
        if suffix not in {".pdf", ".docx", ".txt"}:
            errors.append(f"{file.filename}: 不支持的格式（仅 .pdf/.docx/.txt）")
            continue

        # 保存文件
        dest = docs_dir / file.filename
        content = await file.read()
        dest.write_bytes(content)

        # 分块 + 向量化 + 入库
        try:
            chunks = chunker.load_and_chunk(str(dest))
            texts = [c["text"] for c in chunks]
            embeddings = embedder.embed(texts)
            store.upsert(chunks, embeddings)
            results.append(f"{file.filename}: {len(chunks)} 个片段已索引")
        except Exception as e:
            errors.append(f"{file.filename}: {e}")

    msg = "；".join(results) if results else ""
    error = "；".join(errors) if errors else ""
    return RedirectResponse(f"/upload?msg={msg}&error={error}", status_code=303)
```

- [ ] **Step 2: 创建 templates/upload.html**

```html
<!-- knowledge-server/templates/upload.html -->
{% extends "base.html" %}
{% set active = "upload" %}
{% block title %}上传 - Knowledge{% endblock %}
{% block content %}
<h1>上传文档</h1>

{% if msg %}
<div class="message message-success">{{ msg }}</div>
{% endif %}
{% if error %}
<div class="message message-error">{{ error }}</div>
{% endif %}

<form action="/upload" method="post" enctype="multipart/form-data" class="form-group">
    <input type="file" name="files" multiple accept=".pdf,.docx,.txt">
    <button type="submit">上传并索引</button>
</form>

{% if indexed_files %}
<div class="file-list">
    <h3>已索引文件（共 {{ indexed_files|length }} 个）</h3>
    <ul>
        {% for f in indexed_files %}
        <li>{{ f.name }} — {{ f.chunks }} 个片段</li>
        {% endfor %}
    </ul>
</div>
{% else %}
<p style="color:#666; margin-top:16px;">知识库为空，请上传文档。</p>
{% endif %}
{% endblock %}
```

- [ ] **Step 3: 验证上传功能**

```bash
cd C:/1AI/personal-md-database/yangli2026/work/20260519mcp/knowledge-server
C:/1AI/.pvenv/Scripts/python.exe -c "
from web_app import app
from fastapi.testclient import TestClient
client = TestClient(app)

# GET 上传页
r = client.get('/upload')
print('upload page status:', r.status_code)
print('has form:', 'enctype' in r.text)

# POST 上传一个 txt 文件
import io
r = client.post('/upload', files=[('files', ('hello.txt', io.BytesIO(b'Hello world test content for upload.'), 'text/plain'))])
print('post status:', r.status_code)  # 303 redirect
print('location has msg:', 'msg=' in r.headers.get('location', ''))
"
```

预期：GET 返回 200，POST 返回 303 并重定向到带 msg 参数的上传页。

- [ ] **Step 4: Commit**

```bash
git add knowledge-server/web_app.py knowledge-server/templates/upload.html
git commit -m "feat: add upload page with file indexing"
```

---

### Task 12: 问答页（SSE 流式输出）

**Files:**
- Modify: `knowledge-server/web_app.py`
- Modify: `knowledge-server/templates/ask.html`

- [ ] **Step 1: 在 web_app.py 中添加 SSE 流式端点**

在文件顶部追加 import：

```python
import json
import anthropic
from fastapi.responses import StreamingResponse
```

在 `ask_page` 函数下方追加：

```python
@app.get("/ask/stream")
async def ask_stream(q: str = ""):
    if not q.strip():
        return StreamingResponse(
            iter(["data: 请输入问题\n\n", "event: done\ndata: [DONE]\n\n"]),
            media_type="text/event-stream",
        )

    def generate():
        # 检索相关片段
        chunks = retriever.search(q.strip(), top_k=config.TOP_K)
        if not chunks:
            yield "data: 知识库中未找到相关内容，请先上传文档。\n\n"
            yield "event: done\ndata: [DONE]\n\n"
            return

        # 构造 RAG prompt
        context = "\n\n".join(
            f"[{i+1}] 来源：{c['source']}\n{c['text']}"
            for i, c in enumerate(chunks)
        )
        prompt = (
            "根据以下文档片段回答问题，只使用片段中的信息，"
            "如片段中没有答案请明确说明。\n\n"
            f"{context}\n\n"
            f"问题：{q.strip()}"
        )

        # 流式调用 Claude
        try:
            client = anthropic.Anthropic(
                api_key=os.environ.get("ANTHROPIC_AUTH_TOKEN"),
                base_url=os.environ.get("ANTHROPIC_BASE_URL"),
            )
            with client.messages.stream(
                model=config.CLAUDE_MODEL,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                for text in stream.text_stream:
                    # SSE 格式：每行以 data: 开头
                    yield f"data: {text}\n\n"
        except Exception as e:
            yield f"event: error\ndata: {str(e)}\n\n"

        # 发送引用来源
        sources = [{"source": c["source"], "score": c["score"]} for c in chunks]
        yield f"event: sources\ndata: {json.dumps(sources, ensure_ascii=False)}\n\n"
        yield "event: done\ndata: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

- [ ] **Step 2: 更新 templates/ask.html（完整版，含 EventSource JS）**

```html
<!-- knowledge-server/templates/ask.html -->
{% extends "base.html" %}
{% set active = "ask" %}
{% block title %}问答 - Knowledge{% endblock %}
{% block content %}
<h1>知识库问答</h1>
<div class="form-group">
    <input type="text" id="question" placeholder="输入你的问题..." autofocus>
    <button id="ask-btn" onclick="doAsk()">提问</button>
</div>
<div class="answer-box" id="answer">等待提问...</div>
<ul class="sources" id="sources" style="display:none;"></ul>
{% endblock %}

{% block scripts %}
<script>
function doAsk() {
    const q = document.getElementById('question').value.trim();
    if (!q) return;

    const answerEl = document.getElementById('answer');
    const sourcesEl = document.getElementById('sources');
    const btn = document.getElementById('ask-btn');

    answerEl.textContent = '';
    sourcesEl.innerHTML = '';
    sourcesEl.style.display = 'none';
    btn.disabled = true;

    const es = new EventSource('/ask/stream?q=' + encodeURIComponent(q));

    es.onmessage = function(e) {
        answerEl.textContent += e.data;
    };

    es.addEventListener('sources', function(e) {
        const sources = JSON.parse(e.data);
        if (sources.length > 0) {
            sourcesEl.style.display = 'block';
            sourcesEl.innerHTML = '<li><strong>引用来源：</strong></li>' +
                sources.map(s => '<li>' + s.source + ' (相似度: ' + Math.round(s.score * 100) + '%)</li>').join('');
        }
    });

    es.addEventListener('error', function(e) {
        answerEl.textContent += '\n\n[错误: ' + (e.data || '连接中断') + ']';
        es.close();
        btn.disabled = false;
    });

    es.addEventListener('done', function(e) {
        es.close();
        btn.disabled = false;
    });
}

// 回车键触发提问
document.getElementById('question').addEventListener('keydown', function(e) {
    if (e.key === 'Enter') doAsk();
});
</script>
{% endblock %}
```

- [ ] **Step 3: 验证 SSE 端点基本响应**

```bash
cd C:/1AI/personal-md-database/yangli2026/work/20260519mcp/knowledge-server
C:/1AI/.pvenv/Scripts/python.exe -c "
from web_app import app
from fastapi.testclient import TestClient
client = TestClient(app)

# 空查询
r = client.get('/ask/stream?q=')
print('empty query status:', r.status_code)
print('content-type:', r.headers.get('content-type', ''))
print('body preview:', r.text[:100])

# 问答页面渲染
r = client.get('/')
print('ask page status:', r.status_code)
print('has EventSource:', 'EventSource' in r.text)
"
```

预期：SSE 端点返回 200 + `text/event-stream`，问答页含 EventSource JS。

- [ ] **Step 4: Commit**

```bash
git add knowledge-server/web_app.py knowledge-server/templates/ask.html
git commit -m "feat: add ask page with SSE streaming from Claude"
```

---

### Task 13: 端到端验证 + 最终提交

**Files:**
- 无新增文件，验证现有实现

- [ ] **Step 1: 启动 web app 并手动验证**

```bash
cd C:/1AI/personal-md-database/yangli2026/work/20260519mcp/knowledge-server
C:/1AI/.pvenv/Scripts/python.exe web_app.py
```

在浏览器中访问 http://localhost:8080 ，验证三个页面：
1. 问答页：输入"年假政策是什么"，应看到流式输出答案
2. 检索页：输入"年假"，应看到结果表格
3. 上传页：应看到已索引文件列表（test.txt, 1706.03762v7.pdf, 财务...docx）

- [ ] **Step 2: 验证上传新文件**

在上传页选择一个新 .txt 文件上传，确认：
- 页面跳转后显示成功消息
- 已索引文件列表更新

- [ ] **Step 3: 确认 MCP Server 不受影响**

在另一个终端验证 MCP server 仍可独立运行：

```bash
cd C:/1AI/personal-md-database/yangli2026/work/20260519mcp/knowledge-server
C:/1AI/.pvenv/Scripts/python.exe -c "
import sys; sys.path.insert(0, '.')
import retriever
results = retriever.search('年假', top_k=1)
print('retriever ok:', len(results) > 0)
"
```

- [ ] **Step 4: Final commit（如有未提交的修复）**

```bash
git status
# 如有修改：
git add -A knowledge-server/
git commit -m "fix: polish knowledge web app"
```

---

## 快速参考

```bash
# 索引文档
cd knowledge-server
C:/1AI/.pvenv/Scripts/python.exe ingest.py

# 启动 MCP Server（端口 8001）
C:/1AI/.pvenv/Scripts/python.exe server.py

# 启动 Web App（端口 8080，可同时运行）
C:/1AI/.pvenv/Scripts/python.exe web_app.py

# 启动 lakehouse server（端口 8000，另开终端）
cd ../lakehouse-mcp-server
C:/1AI/.pvenv/Scripts/python.exe server.py

# 运行所有单元测试
cd knowledge-server
C:/1AI/.pvenv/Scripts/python.exe -m pytest tests/ -v
```
