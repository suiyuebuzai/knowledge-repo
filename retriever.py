import embedder
import store
import config


def search(query: str, top_k: int = config.TOP_K) -> list[dict]:
    """query → embed → ChromaDB 检索 → 返回 top-k chunks。"""
    embedding = embedder.embed([query])[0]
    return store.search(embedding, top_k)
