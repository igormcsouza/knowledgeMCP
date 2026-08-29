from fastembed import TextEmbedding

from knowledge_indexer.config import EMBEDDING_MODEL_NAME

_model: TextEmbedding | None = None


def _get_model() -> TextEmbedding:
    # Local ONNX model, not Bedrock: this account's Bedrock embedding
    # on-demand quota is 0 across every model and region pending an AWS
    # support ticket, so embeddings run in-process instead. Must stay in
    # sync with mcp_server's EMBEDDING_MODEL_NAME — cosine similarity is
    # meaningless across two different embedding spaces.
    global _model
    if _model is None:
        _model = TextEmbedding(model_name=EMBEDDING_MODEL_NAME, cache_dir="/tmp/fastembed_cache")
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    return [vector.tolist() for vector in _get_model().embed(texts)]
