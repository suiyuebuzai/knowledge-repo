from sentence_transformers import SentenceTransformer
import config

_model = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(config.EMBED_MODEL, local_files_only=True)
    return _model


def embed(texts: list[str]) -> list[list[float]]:
    """批量向量化文本，返回 384 维 float 列表。"""
    model = _get_model()
    return model.encode(texts, normalize_embeddings=True).tolist()
