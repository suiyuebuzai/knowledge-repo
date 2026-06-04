import embedder
import store
import bm25_store
import config


def _rrf_fuse(
    vec_results: list[dict],
    bm25_results: list[dict],
    vec_weight: float,
    bm25_weight: float,
    k: int = 60,
) -> list[dict]:
    """Reciprocal Rank Fusion 融合两路结果。

    RRF score = weight / (k + rank)，按 text 去重后合并排序。
    """
    scored: dict[str, dict] = {}  # text → {"text", "source", "rrf_score"}

    for rank, item in enumerate(vec_results, start=1):
        key = item["text"]
        if key not in scored:
            scored[key] = {"text": item["text"], "source": item["source"], "rrf_score": 0.0}
        scored[key]["rrf_score"] += vec_weight / (k + rank)

    for rank, item in enumerate(bm25_results, start=1):
        key = item["text"]
        if key not in scored:
            scored[key] = {"text": item["text"], "source": item["source"], "rrf_score": 0.0}
        scored[key]["rrf_score"] += bm25_weight / (k + rank)

    # 按融合分数降序排列
    fused = sorted(scored.values(), key=lambda x: x["rrf_score"], reverse=True)
    return fused


def search(query: str, top_k: int = config.TOP_K) -> list[dict]:
    """混合检索：向量语义 + BM25 关键词，RRF 融合排序。"""
    candidate_k = config.HYBRID_CANDIDATE_K
    bm25_weight = config.BM25_WEIGHT
    vec_weight = 1 - bm25_weight

    # 向量路
    embedding = embedder.embed([query])[0]
    vec_results = store.search(embedding, candidate_k)

    # BM25 路
    bm25_results = bm25_store.search(query, candidate_k)

    # 若 BM25 索引为空，退化为纯向量检索
    if not bm25_results:
        return vec_results[:top_k]

    # RRF 融合
    fused = _rrf_fuse(vec_results, bm25_results, vec_weight, bm25_weight)

    # 归一化 score 到 [0, 1] 并取 top_k
    results = fused[:top_k]
    if results:
        max_rrf = results[0]["rrf_score"]
        for r in results:
            r["score"] = round(r["rrf_score"] / max_rrf, 4) if max_rrf > 0 else 0
            del r["rrf_score"]

    return results
