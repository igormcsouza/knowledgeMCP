from knowledge_indexer.chunker import chunk_article


def test_chunk_article_splits_by_header():
    content = (
        "# ACID\n\nIntro text.\n\n"
        "## Atomicity\n\nAll-or-nothing.\n\n"
        "## Consistency\n\nValid states only.\n"
    )
    chunks = chunk_article("docs/knowledge/databases/acid.md", content)

    sections = [c.section for c in chunks]
    assert any("Atomicity" in s for s in sections)
    assert any("Consistency" in s for s in sections)
    assert all(c.chunk_id.startswith("docs/knowledge/databases/acid.md#") for c in chunks)


def test_chunk_article_handles_no_headers():
    chunks = chunk_article("docs/knowledge/x.md", "Just a plain paragraph, no headers.")
    assert len(chunks) == 1
    assert chunks[0].text.strip() == "Just a plain paragraph, no headers."
