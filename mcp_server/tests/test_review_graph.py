from datetime import date, timedelta

from knowledge_mcp import review_graph


def _iso(days_ago: int) -> str:
    return (date.today() - timedelta(days=days_ago)).isoformat()


def test_suggest_review_queue_flags_weak_and_stale(dynamodb_tables):
    content = dynamodb_tables.Table("knowledge-mcp-test-content-index")
    usage = dynamodb_tables.Table("knowledge-mcp-test-usage-tracking")

    content.put_item(
        Item={
            "article_path": "docs/knowledge/x/thin.md",
            "chunk_id": "docs/knowledge/x/thin.md#0",
            "title": "Thin Article",
            "category": "x",
            "section": "",
            "text": "Too short.",
            "tags": [],
            "embedding": ["0.1"],
            "indexed_at": _iso(0),
        }
    )
    usage.put_item(
        Item={
            "article_path": "docs/knowledge/x/thin.md",
            "first_seen_date": _iso(120),
            "last_queried_date": _iso(60),
            "query_count": 0,
        }
    )

    queue = review_graph.suggest_review_queue(limit=5)
    assert len(queue) == 1
    entry = queue[0]
    assert entry["article_path"] == "docs/knowledge/x/thin.md"
    assert "weak_content" in entry["reasons"]
    assert "stale_not_queried" in entry["reasons"]
    assert "untouched_since_created" in entry["reasons"]
    assert entry["priority"] == 3
