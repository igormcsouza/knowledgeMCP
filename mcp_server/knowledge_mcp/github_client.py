import os

import boto3
from github import Auth, Github

_cached_token: str | None = None
_cached_client: Github | None = None


def _get_token() -> str | None:
    """GitHub token from SSM Parameter Store, cached across warm invocations —
    see indexer/knowledge_indexer/github_client.py for why unauthenticated
    access isn't good enough."""
    global _cached_token
    if _cached_token is not None:
        return _cached_token

    param_name = os.environ.get("GITHUB_TOKEN_SECRET_PARAM")
    if not param_name:
        return None

    client = boto3.client("ssm")
    _cached_token = client.get_parameter(Name=param_name, WithDecryption=True)[
        "Parameter"
    ]["Value"]
    return _cached_token


def get_github_client() -> Github:
    global _cached_client
    if _cached_client is not None:
        return _cached_client

    token = _get_token()
    _cached_client = Github(auth=Auth.Token(token)) if token else Github()
    return _cached_client
