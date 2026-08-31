import os

import boto3
from github import Auth, Github

_cached_token: str | None = None
_cached_client: Github | None = None


def _get_token() -> str | None:
    """GitHub token from SSM Parameter Store, cached across warm invocations.

    Unauthenticated GitHub API access is capped at 60 req/hour and shared
    across every AWS Lambda customer on the same egress IP pool — a full
    index run of ~50 files exhausts that near-instantly and the indexer
    hangs until Lambda's own timeout. Authenticated access gets 5000/hour,
    dedicated to this token. Returns None (falls back to unauthenticated)
    only when no param name is configured, e.g. local/test runs.
    """
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
