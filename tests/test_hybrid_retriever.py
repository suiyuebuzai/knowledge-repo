"""混合检索（向量 + BM25 + RRF 融合）集成测试。"""
import pytest
import store
import retriever
import embedder
import bm25_store
import config


@pytest.fixture(autouse=True)
def temp_env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CHROMA_DIR", str(tmp_path / "chroma"))
    store._collection = None
    bm25_store.clear()
    yield
    store._collection = None
    bm25_store.clear()


def _ingest(chunks):
    """辅助：将 chunks 写入 ChromaDB + BM25。"""
    embs = embedder.embed([c["text"] for c in chunks])
    store.upsert(chunks, embs)


def test_keyword_hit_ranks_higher():
    """包含精确关键词的文档应通过 BM25 加权排到更前面。"""
    chunks = [
        {"id": "a#0", "text": "EMP001 张三是研发部工程师", "metadata": {"source": "hr.txt"}},
        {"id": "b#0", "text": "公司研发部门有很多优秀的工程师", "metadata": {"source": "intro.txt"}},
        {"id": "c#0", "text": "Python 是一种编程语言", "metadata": {"source": "tech.txt"}},
    ]
    _ingest(chunks)

    results = retriever.search("EMP001", top_k=3)
    assert len(results) >= 1
    assert results[0]["source"] == "hr.txt"


def test_search_returns_expected_format():
    """返回格式应包含 text, source, score。"""
    chunks = [
        {"id": "a#0", "text": "年假政策员工每年10天", "metadata": {"source": "hr.txt"}},
    ]
    _ingest(chunks)

    results = retriever.search("年假", top_k=1)
    assert len(results) == 1
    r = results[0]
    assert "text" in r
    assert "source" in r
    assert "score" in r
    assert 0 <= r["score"] <= 1


def test_bm25_empty_falls_back_to_vector():
    """BM25 索引为空时应退化为纯向量检索。"""
    # 直接写 ChromaDB 但不触发 bm25_store.add（绕过 store.upsert）
    chunks = [
        {"id": "a#0", "text": "合同有效期一年", "metadata": {"source": "contract.txt", "page": 0}},
    ]
    embs = embedder.embed([c["text"] for c in chunks])
    col = store._get_collection()
    col.upsert(
        ids=[c["id"] for c in chunks],
        documents=[c["text"] for c in chunks],
        metadatas=[c["metadata"] for c in chunks],
        embeddings=embs,
    )
    # BM25 为空，应退化为向量
    results = retriever.search("合同", top_k=1)
    assert len(results) == 1
    assert results[0]["source"] == "contract.txt"


def test_top_k_limits_fused_results():
    """融合后的结果数量不超过 top_k。"""
    chunks = [
        {"id": f"doc#{i}", "text": f"年假政策相关内容段落{i}号", "metadata": {"source": f"f{i}.txt"}}
        for i in range(10)
    ]
    _ingest(chunks)

    results = retriever.search("年假政策", top_k=3)
    assert len(results) == 3


def test_rrf_deduplicates():
    """同一文档在两路中都出现时，RRF 应合并而非重复。"""
    chunks = [
        {"id": "a#0", "text": "年假政策员工每年享有10天带薪年假", "metadata": {"source": "hr.txt"}},
        {"id": "b#0", "text": "Python 编程入门教程", "metadata": {"source": "tech.txt"}},
    ]
    _ingest(chunks)

    results = retriever.search("年假", top_k=5)
    # 不应有重复 text
    texts = [r["text"] for r in results]
    assert len(texts) == len(set(texts))
