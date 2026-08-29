from knowledge_mcp import dynamodb


def test_cosine_similarity_identical_vectors():
    assert dynamodb.cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0


def test_cosine_similarity_orthogonal_vectors():
    assert dynamodb.cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_cosine_similarity_zero_vector_is_safe():
    assert dynamodb.cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_days_since_none_for_missing_date():
    assert dynamodb.days_since(None) is None


def test_scan_all_chunks_roundtrip(dynamodb_tables):
    table = dynamodb_tables.Table("knowledge-mcp-test-content-index")
    table.put_item(
        Item={
            "article_path": "docs/knowledge/databases/acid.md",
            "chunk_id": "docs/knowledge/databases/acid.md#0",
            "title": "ACID",
            "category": "databases",
            "section": "ACID",
            "text": "ACID guarantees.",
            "tags": ["databases"],
            "embedding": ["0.1", "0.2"],
            "indexed_at": "2026-08-01",
        }
    )

    chunks = dynamodb.scan_all_chunks()
    assert len(chunks) == 1
    assert chunks[0].title == "ACID"
    assert chunks[0].embedding == [0.1, 0.2]


def test_record_query_feedback_increments_counts(dynamodb_tables):
    dynamodb.record_query_feedback("docs/knowledge/databases/acid.md", was_helpful=True)
    dynamodb.record_query_feedback("docs/knowledge/databases/acid.md", was_helpful=False)

    usage = dynamodb.get_usage_metadata("docs/knowledge/databases/acid.md")
    assert usage["query_count"] == 2
    assert usage["helpful_count"] == 1
    assert usage["unhelpful_count"] == 1
