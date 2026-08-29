import boto3
from langchain_aws import BedrockEmbeddings

from knowledge_indexer.config import BEDROCK_REGION, EMBEDDING_MODEL_ID

_client = None


def _get_client() -> BedrockEmbeddings:
    global _client
    if _client is None:
        bedrock_runtime = boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)
        _client = BedrockEmbeddings(
            client=bedrock_runtime, model_id=EMBEDDING_MODEL_ID
        )
    return _client


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    return _get_client().embed_documents(texts)
