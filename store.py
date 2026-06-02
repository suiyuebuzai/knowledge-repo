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
