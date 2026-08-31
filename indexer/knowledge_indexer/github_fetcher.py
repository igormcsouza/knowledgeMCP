from dataclasses import dataclass, field

import yaml
from knowledge_indexer.config import DOCS_PREFIXES, GITHUB_BRANCH, GITHUB_REPO
from knowledge_indexer.github_client import get_github_client


@dataclass
class Article:
    path: str  # e.g. "docs/knowledge/databases/acid.md"
    title: str
    content: str  # markdown body, frontmatter stripped
    category: str  # e.g. "databases" (immediate parent dir under its prefix)
    tags: list[str] = field(default_factory=list)
    sha: str = ""  # git blob sha, used to detect per-file changes


def _split_frontmatter(raw: str) -> tuple[dict, str]:
    """Split a leading '---\\n...\\n---' YAML block off the markdown body.

    Returns ({} , raw) unchanged if there's no frontmatter block.
    """
    if not raw.startswith("---\n"):
        return {}, raw
    end = raw.find("\n---", 4)
    if end == -1:
        return {}, raw
    frontmatter_text = raw[4:end]
    body = raw[end + 4 :].lstrip("\n")
    try:
        data = yaml.safe_load(frontmatter_text) or {}
    except yaml.YAMLError:
        data = {}
    return data, body


def _title_from_body(body: str, fallback: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return fallback


def _matching_prefix(path: str) -> str | None:
    return next((p for p in DOCS_PREFIXES if path.startswith(p)), None)


def _category_from_path(path: str, prefix: str) -> str:
    # docs/knowledge/databases/acid.md -> "databases"
    # docs/knowledge/devops-tools/aws/lambda.md -> "devops-tools/aws"
    # docs/troubleshooting/wifi-x.md -> "troubleshooting" (leaf file directly
    # under the prefix takes the prefix's own last directory as category).
    relative = path.removeprefix(prefix)
    parts = relative.split("/")[:-1]
    if parts:
        return "/".join(parts)
    return prefix.rstrip("/").rsplit("/", 1)[-1]


@dataclass
class TreeEntry:
    path: str
    prefix: str
    sha: str


def get_repo(repo_name: str = GITHUB_REPO):
    return get_github_client().get_repo(repo_name)


def list_tree_entries(repo, branch: str = GITHUB_BRANCH) -> list[TreeEntry]:
    """List every current article's path + git blob sha via a single tree
    call — no per-file content fetch. Lets the caller diff against already-
    indexed shas before paying for a get_contents call per changed file
    (the expensive part, and the one that counts against GitHub's API rate
    limit).

    Skips index.md files (per-category landing pages, not content) — see
    PLAN.md 1.1. Category/hierarchy comes from the directory structure since
    this repo's mkdocs.yml has no explicit `nav:` (Material auto-generates
    nav from docs/ layout, not from an awesome-pages ordering file).
    """
    tree = repo.get_git_tree(branch, recursive=True)

    entries = []
    for entry in tree.tree:
        if entry.type != "blob":
            continue
        prefix = _matching_prefix(entry.path)
        if prefix is None:
            continue
        if not entry.path.endswith(".md"):
            continue
        if entry.path.endswith("/index.md"):
            continue
        entries.append(TreeEntry(path=entry.path, prefix=prefix, sha=entry.sha))

    return entries


def fetch_article_content(
    repo, branch: str, entry: TreeEntry
) -> Article:
    """Fetch and parse one article's body. The one call per file that
    actually counts against GitHub's rate limit — only call this for
    entries whose sha changed since the last index run."""
    content_file = repo.get_contents(entry.path, ref=branch)
    raw = content_file.decoded_content.decode("utf-8")
    frontmatter, body = _split_frontmatter(raw)

    return Article(
        path=entry.path,
        title=_title_from_body(body, fallback=entry.path.split("/")[-1]),
        content=body,
        category=_category_from_path(entry.path, entry.prefix),
        tags=frontmatter.get("tags") or [],
        sha=entry.sha,
    )


def parse_nav_categories(mkdocs_yml_text: str) -> dict | None:
    """Return the mkdocs.yml `nav:` structure if one is explicitly defined.

    None means nav is auto-generated from the docs/ directory tree, which is
    the case for this repo — category comes from _category_from_path instead.
    """
    config = yaml.safe_load(mkdocs_yml_text) or {}
    return config.get("nav")
