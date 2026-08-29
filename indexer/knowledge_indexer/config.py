import os

GITHUB_REPO = os.environ.get("GITHUB_REPO", "igormcsouza/knowledge-base")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")
# Only files under these prefixes are indexed as knowledge articles — README,
# roadmap, tags.md, etc. at the repo root are not concepts to search over.
# docs/troubleshooting/ is separate from docs/knowledge/ in this repo but is
# exactly what recall_solution (PLAN.md 3.5) needs to search over.
DOCS_PREFIXES = tuple(
    os.environ.get("DOCS_PREFIXES", "docs/knowledge/,docs/troubleshooting/").split(",")
)
BEDROCK_REGION = os.environ.get("BEDROCK_REGION", "us-east-1")
EMBEDDING_MODEL_ID = os.environ.get(
    "EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v2:0"
)
ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")


def table_name(suffix: str) -> str:
    return f"knowledge-mcp-{ENVIRONMENT}-{suffix}"
