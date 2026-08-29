import json

import boto3

from knowledge_mcp.config import BEDROCK_REGION, EMBEDDING_MODEL_ID

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)
    return _client


def embed_query(text: str) -> list[float]:
    """Direct invoke_model call, no LangChain wrapper — this is a single
    plain retrieval call (PLAN.md: "every other tool is a single retrieval
    call... no framework wrapper"). Only the indexer uses the LangChain
    embeddings wrapper.
    """
    response = _get_client().invoke_model(
        modelId=EMBEDDING_MODEL_ID,
        body=json.dumps({"inputText": text}),
        contentType="application/json",
        accept="application/json",
    )
    payload = json.loads(response["body"].read())
    return payload["embedding"]
