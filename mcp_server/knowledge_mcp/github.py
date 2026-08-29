import os

from knowledge_mcp.github_client import get_github_client

GITHUB_REPO = os.environ.get("GITHUB_REPO", "igormcsouza/knowledge-base")


def get_file_history(article_path: str, limit: int = 20) -> list[dict]:
    """Git log for one file — how a concept/fix evolved over time
    (PLAN.md 3.9)."""
    client = get_github_client()
    repo = client.get_repo(GITHUB_REPO)
    commits = repo.get_commits(path=article_path)
    history = []
    for commit in commits[:limit]:
        history.append(
            {
                "sha": commit.sha[:7],
                "date": commit.commit.author.date.isoformat(),
                "message": commit.commit.message.splitlines()[0],
                "author": commit.commit.author.name,
                "url": commit.html_url,
            }
        )
    return history


def count_commits(article_path: str) -> int:
    """Used as the edit-count-depth proxy for weak-concept detection when
    the usage table's own edit_count hasn't accumulated history yet."""
    client = get_github_client()
    repo = client.get_repo(GITHUB_REPO)
    return repo.get_commits(path=article_path).totalCount
