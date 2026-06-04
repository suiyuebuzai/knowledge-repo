# bm25_store.py
"""
BM25 关键词检索索引。

维护一个内存中的 BM25Okapi 索引，与 ChromaDB 向量索引并行，
用于混合检索中的关键词匹配路径。
"""
import re
import jieba
from rank_bm25 import BM25Plus

# 内存状态
_corpus_texts: list[str] = []
_corpus_sources: list[str] = []
_corpus_tokens: list[list[str]] = []
_bm25: BM25Plus | None = None


def _tokenize(text: str) -> list[str]:
    """jieba 中文分词 + 过滤标点和空字符。"""
    words = jieba.lcut(text)
    return [w for w in words if w.strip() and not re.match(r'^[\s\W]+$', w)]


def _rebuild() -> None:
    """根据当前语料重建 BM25 索引。"""
    global _bm25
    if not _corpus_tokens:
        _bm25 = None
        return
    _bm25 = BM25Plus(_corpus_tokens)


def add(chunks: list[dict]) -> None:
    """追加 chunks 到语料并重建索引。"""
    for c in chunks:
        _corpus_texts.append(c["text"])
        _corpus_sources.append(c.get("metadata", {}).get("source", ""))
        _corpus_tokens.append(_tokenize(c["text"]))
    _rebuild()


def rebuild_from_chroma() -> None:
    """从 ChromaDB 全量同步语料（启动时调用）。"""
    import store
    col = store._get_collection()
    if col.count() == 0:
        return
    data = col.get(include=["documents", "metadatas"])
    documents = data.get("documents", [])
    metadatas = data.get("metadatas", [])

    clear()
    for text, meta in zip(documents, metadatas):
        _corpus_texts.append(text)
        _corpus_sources.append(meta.get("source", ""))
        _corpus_tokens.append(_tokenize(text))
    _rebuild()


def search(query: str, top_k: int) -> list[dict]:
    """BM25 检索，返回 [{"text", "source", "score"}]。score 归一化到 [0,1]。"""
    if _bm25 is None or not _corpus_texts:
        return []

    tokens = _tokenize(query)
    if not tokens:
        return []

    scores = _bm25.get_scores(tokens)
    max_score = max(scores) if len(scores) > 0 else 0
    if max_score == 0:
        return []

    # 排序取 top_k
    indexed = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:top_k]
    results = []
    for idx, score in indexed:
        if score <= 0:
            break
        results.append({
            "text": _corpus_texts[idx],
            "source": _corpus_sources[idx],
            "score": round(score / max_score, 4),
        })
    return results


def clear() -> None:
    """清空所有状态（测试辅助）。"""
    global _bm25
    _corpus_texts.clear()
    _corpus_sources.clear()
    _corpus_tokens.clear()
    _bm25 = None
