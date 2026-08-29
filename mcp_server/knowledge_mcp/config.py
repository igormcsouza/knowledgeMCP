import os

# Local fastembed/ONNX model, not Bedrock — see embeddings.py.
EMBEDDING_MODEL_NAME = os.environ.get(
    "EMBEDDING_MODEL_NAME", "BAAI/bge-small-en-v1.5"
)
ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")


def table_name(suffix: str) -> str:
    return f"knowledge-mcp-{ENVIRONMENT}-{suffix}"
