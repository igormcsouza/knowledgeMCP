from knowledge_indexer.github_fetcher import (
    _category_from_path,
    _split_frontmatter,
    _title_from_body,
)


def test_split_frontmatter_extracts_tags():
    raw = "---\ntags:\n- databases\n- acid\n---\n\n# ACID\n\nBody text.\n"
    frontmatter, body = _split_frontmatter(raw)
    assert frontmatter["tags"] == ["databases", "acid"]
    assert body.startswith("# ACID")


def test_split_frontmatter_handles_missing_block():
    raw = "# No Frontmatter\n\nJust content.\n"
    frontmatter, body = _split_frontmatter(raw)
    assert frontmatter == {}
    assert body == raw


def test_title_from_body_finds_h1():
    assert _title_from_body("intro\n# My Title\nmore", fallback="x") == "My Title"


def test_title_from_body_falls_back_when_no_h1():
    assert _title_from_body("no headers here", fallback="fallback.md") == "fallback.md"


def test_category_from_nested_path():
    assert (
        _category_from_path(
            "docs/knowledge/devops-tools/aws/lambda.md", "docs/knowledge/"
        )
        == "devops-tools/aws"
    )


def test_category_from_shallow_path():
    assert (
        _category_from_path("docs/knowledge/databases/acid.md", "docs/knowledge/")
        == "databases"
    )


def test_category_from_troubleshooting_leaf():
    assert (
        _category_from_path("docs/troubleshooting/wifi-x.md", "docs/troubleshooting/")
        == "troubleshooting"
    )
