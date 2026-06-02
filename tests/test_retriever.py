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
