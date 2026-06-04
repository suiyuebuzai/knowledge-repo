import pytest
import bm25_store
import store
import embedder
import config


@pytest.fixture(autouse=True)
def clean_bm25():
    bm25_store.clear()
    yield
    bm25_store.clear()


@pytest.fixture
def temp_chroma(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CHROMA_DIR", str(tmp_path / "chroma"))
    store._collection = None
    yield
    store._collection = None


def test_tokenize_chinese():
    """jieba 分词应切出中文词。"""
    tokens = bm25_store._tokenize("员工年假政策")
    assert len(tokens) > 1
    assert all(isinstance(t, str) for t in tokens)
    assert all(len(t) > 0 for t in tokens)


def test_tokenize_filters_punctuation():
    """标点符号应被过滤。"""
    tokens = bm25_store._tokenize("hello, world! 你好。")
    assert "," not in tokens
    assert "!" not in tokens
    assert "。" not in tokens


def test_search_returns_relevant_chunk():
    """BM25 应能按关键词匹配到正确文档。"""
    chunks = [
        {"id": "a#0", "text": "年假政策员工每年享有10天带薪年假", "metadata": {"source": "hr.txt"}},
        {"id": "b#0", "text": "Python 是一种编程语言", "metadata": {"source": "tech.txt"}},
    ]
    bm25_store.add(chunks)
    results = bm25_store.search("年假", top_k=1)
    assert len(results) == 1
    assert results[0]["source"] == "hr.txt"


def test_search_empty_returns_empty():
    """索引为空时应返回空列表。"""
    results = bm25_store.search("任意查询", top_k=5)
    assert results == []


def test_score_in_range():
    """score 应归一化到 [0, 1] 范围。"""
    chunks = [
        {"id": "a#0", "text": "测试内容包含关键词", "metadata": {"source": "x.txt"}},
        {"id": "b#0", "text": "另一段不同的文本", "metadata": {"source": "y.txt"}},
    ]
    bm25_store.add(chunks)
    results = bm25_store.search("测试关键词", top_k=2)
    for r in results:
        assert 0 <= r["score"] <= 1


def test_top_k_limits_results():
    """返回数量不应超过 top_k。"""
    chunks = [
        {"id": f"doc#{i}", "text": f"年假政策相关内容段落{i}", "metadata": {"source": "x.txt"}}
        for i in range(10)
    ]
    bm25_store.add(chunks)
    results = bm25_store.search("年假", top_k=3)
    assert len(results) == 3


def test_rebuild_from_chroma(temp_chroma):
    """rebuild_from_chroma 应能从 ChromaDB 恢复 BM25 索引。"""
    chunks = [
        {"id": "a#0", "text": "合同有效期为一年", "metadata": {"source": "contract.txt", "page": 0}},
    ]
    embs = embedder.embed([c["text"] for c in chunks])
    # 直接写 ChromaDB，不触发 bm25_store.add
    col = store._get_collection()
    col.upsert(
        ids=[c["id"] for c in chunks],
        documents=[c["text"] for c in chunks],
        metadatas=[c["metadata"] for c in chunks],
        embeddings=embs,
    )
    # BM25 索引此时为空
    assert bm25_store.search("合同", top_k=1) == []

    # 重建
    bm25_store.rebuild_from_chroma()
    results = bm25_store.search("合同", top_k=1)
    assert len(results) == 1
    assert results[0]["source"] == "contract.txt"
