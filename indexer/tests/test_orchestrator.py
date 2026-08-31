from unittest.mock import patch

from knowledge_indexer.github_fetcher import Article, TreeEntry
from knowledge_indexer.orchestrator import run_index


def _entry(path, sha):
    return TreeEntry(path=path, prefix="docs/knowledge/", sha=sha)


def _article(path, sha):
    return Article(path=path, title=path, content="body", category="cat", sha=sha)


@patch("knowledge_indexer.orchestrator.set_last_indexed_sha")
@patch("knowledge_indexer.orchestrator.touch_usage_metadata")
@patch("knowledge_indexer.orchestrator.write_article_chunks")
@patch("knowledge_indexer.orchestrator.delete_article_chunks")
@patch("knowledge_indexer.orchestrator.remove_usage_metadata")
@patch("knowledge_indexer.orchestrator.embed_texts", return_value=[[0.0]])
@patch("knowledge_indexer.orchestrator.chunk_article", return_value=[])
@patch("knowledge_indexer.orchestrator.fetch_article_content")
@patch("knowledge_indexer.orchestrator.get_indexed_file_shas")
@patch("knowledge_indexer.orchestrator.list_tree_entries")
@patch("knowledge_indexer.orchestrator.get_repo", return_value="repo")
def test_only_changed_entries_fetch_content(
    mock_get_repo,
    mock_list_tree_entries,
    mock_get_indexed_shas,
    mock_fetch_content,
    mock_chunk_article,
    mock_embed_texts,
    mock_remove_usage,
    mock_delete_chunks,
    mock_write_chunks,
    mock_touch_usage,
    mock_set_last_sha,
):
    mock_list_tree_entries.return_value = [
        _entry("a.md", "sha-a-new"),
        _entry("b.md", "sha-b-unchanged"),
    ]
    mock_get_indexed_shas.return_value = {
        "a.md": "sha-a-old",
        "b.md": "sha-b-unchanged",
    }
    mock_fetch_content.return_value = _article("a.md", "sha-a-new")

    result = run_index(head_sha="commit-1")

    mock_fetch_content.assert_called_once()
    assert mock_fetch_content.call_args[0][2].path == "a.md"
    assert result["reindexed"] == ["a.md"]
    assert result["skipped_unchanged"] == 1
    assert result["removed"] == []
    mock_set_last_sha.assert_called_once_with(
        "igormcsouza/knowledge-base", "commit-1"
    )


@patch("knowledge_indexer.orchestrator.set_last_indexed_sha")
@patch("knowledge_indexer.orchestrator.touch_usage_metadata")
@patch("knowledge_indexer.orchestrator.write_article_chunks")
@patch("knowledge_indexer.orchestrator.delete_article_chunks")
@patch("knowledge_indexer.orchestrator.remove_usage_metadata")
@patch("knowledge_indexer.orchestrator.embed_texts", return_value=[[0.0]])
@patch("knowledge_indexer.orchestrator.chunk_article", return_value=[])
@patch("knowledge_indexer.orchestrator.fetch_article_content")
@patch("knowledge_indexer.orchestrator.get_indexed_file_shas")
@patch("knowledge_indexer.orchestrator.list_tree_entries")
@patch("knowledge_indexer.orchestrator.get_repo", return_value="repo")
def test_deleted_article_is_removed(
    mock_get_repo,
    mock_list_tree_entries,
    mock_get_indexed_shas,
    mock_fetch_content,
    mock_chunk_article,
    mock_embed_texts,
    mock_remove_usage,
    mock_delete_chunks,
    mock_write_chunks,
    mock_touch_usage,
    mock_set_last_sha,
):
    mock_list_tree_entries.return_value = []
    mock_get_indexed_shas.return_value = {"gone.md": "sha-gone"}

    result = run_index()

    mock_fetch_content.assert_not_called()
    assert result["removed"] == ["gone.md"]
    mock_delete_chunks.assert_called_once_with("gone.md")
    mock_remove_usage.assert_called_once_with("gone.md")
