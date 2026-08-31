from github import Github

_cached_client: Github | None = None


def get_github_client() -> Github:
    """Unauthenticated GitHub client, cached across warm invocations.

    Capped at 60 req/hour, shared across every AWS Lambda customer on the
    same egress IP pool — acceptable here since the indexer only re-fetches
    files that changed since the last run (tracked via indexer_state_table),
    keeping per-run call volume low. Auth was dropped in favor of relying on
    the GitHub webhook signature alone (see PLAN.md 1.4).
    """
    global _cached_client
    if _cached_client is None:
        _cached_client = Github()
    return _cached_client
