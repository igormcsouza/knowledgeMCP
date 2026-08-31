from github import Github

_cached_client: Github | None = None


def get_github_client() -> Github:
    """Unauthenticated GitHub client, cached across warm invocations — see
    indexer/knowledge_indexer/github_client.py for why."""
    global _cached_client
    if _cached_client is None:
        _cached_client = Github()
    return _cached_client
