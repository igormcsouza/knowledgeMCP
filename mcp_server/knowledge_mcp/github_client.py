import os

import boto3
from github import Auth, Github

_cached_token: str | None = None
_cached_client: Github | None = None


def _get_token() -> str | None:
    """GitHub token from Secrets Manager, cached across warm invocations —
    see indexer/knowledge_indexer/github_client.py for why unauthenticated
    access isn't good enough."""
    global _cached_token
    if _cached_token is not None:
        return _cached_token

    secret_arn = os.environ.get("GITHUB_TOKEN_SECRET_ARN")
    if not secret_arn:
        return None

    client = boto3.client("secretsmanager")
    _cached_token = client.get_secret_value(SecretId=secret_arn)["SecretString"]
    return _cached_token


def get_github_client() -> Github:
    global _cached_client
    if _cached_client is not None:
        return _cached_client

    token = _get_token()
    _cached_client = Github(auth=Auth.Token(token)) if token else Github()
    return _cached_client
