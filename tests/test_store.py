import pytest
import store
import embedder


@pytest.fixture(autouse=True)
def temp_chroma(tmp_path, monkeypatch):
    """每个测试用独立的临时 ChromaDB，避免相互污染。"""
    import config
    monkeypatch.setattr(config, "CHROMA_DIR", str(tmp_path / "chroma"))
    store._collection = None
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
