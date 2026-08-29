from fastembed import TextEmbedding

from knowledge_mcp.config import EMBEDDING_MODEL_NAME

_model: TextEmbedding | None = None


def _get_model() -> TextEmbedding:
    # Local ONNX model, not Bedrock — see indexer/knowledge_indexer/embeddings.py
    # for why. Must stay in sync with the indexer's EMBEDDING_MODEL_NAME.
    global _model
    if _model is None:
        _model = TextEmbedding(model_name=EMBEDDING_MODEL_NAME, cache_dir="/tmp/fastembed_cache")
    return _model


def embed_query(text: str) -> list[float]:
    return next(iter(_get_model().embed([text]))).tolist()
