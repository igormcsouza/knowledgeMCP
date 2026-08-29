import os

BEDROCK_REGION = os.environ.get("BEDROCK_REGION", "us-east-1")
EMBEDDING_MODEL_ID = os.environ.get(
    "EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v2:0"
)
ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")
BEARER_TOKEN_SECRET_ARN = os.environ.get("BEARER_TOKEN_SECRET_ARN")


def table_name(suffix: str) -> str:
    return f"knowledge-mcp-{ENVIRONMENT}-{suffix}"
