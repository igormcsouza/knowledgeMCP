import json
from unittest.mock import patch

from mcp.server.fastmcp import FastMCP

from knowledge_mcp.tools import register_tools


def _seed_article(table, path, title, category, text, embedding, tags=None, indexed_at="2026-08-01"):
    table.put_item(
        Item={
            "article_path": path,
            "chunk_id": f"{path}#0",
            "title": title,
            "category": category,
            "section": title,
            "text": text,
            "tags": tags or [],
            "embedding": [str(v) for v in embedding],
            "indexed_at": indexed_at,
        }
    )


async def _call(mcp, name, **kwargs):
    # Parse the TextContent's JSON body directly — this mcp version's
    # structured-content shape differs between list- and dict-returning
    # tools, but the rendered text content is consistent either way.
    response = await mcp.call_tool(name, kwargs)
    content = response[0] if isinstance(response, tuple) else response
    parsed = json.loads(content[0].text)
    if isinstance(parsed, dict) and list(parsed) == ["result"]:
        return parsed["result"]
    return parsed


def test_search_concept_ranks_by_similarity(dynamodb_tables):
    table = dynamodb_tables.Table("knowledge-mcp-test-content-index")
    _seed_article(table, "docs/knowledge/databases/acid.md", "ACID", "databases", "ACID text", [1.0, 0.0])
    _seed_article(table, "docs/knowledge/python/asyncio.md", "Asyncio", "python", "asyncio text", [0.0, 1.0])

    mcp = FastMCP("test")
    register_tools(mcp)

    with patch("knowledge_mcp.tools.embed_query", return_value=[1.0, 0.0]):
        import asyncio

        result = asyncio.run(_call(mcp, "search_concept", query="acid guarantees", top_k=1))

    top = result[0] if isinstance(result, list) else result
    assert "acid" in top["text"].lower()


def test_get_article_context_returns_full_text(dynamodb_tables):
    table = dynamodb_tables.Table("knowledge-mcp-test-content-index")
    _seed_article(table, "docs/knowledge/databases/acid.md", "ACID", "databases", "ACID full text", [1.0, 0.0])

    mcp = FastMCP("test")
    register_tools(mcp)

    import asyncio

    result = asyncio.run(_call(mcp, "get_article_context", article_path="docs/knowledge/databases/acid.md"))
    assert "ACID full text" in result["content"]


def test_log_query_feedback_writes_usage(dynamodb_tables):
    mcp = FastMCP("test")
    register_tools(mcp)

    import asyncio

    asyncio.run(
        _call(
            mcp,
            "log_query_feedback",
            concept_article_path="docs/knowledge/databases/acid.md",
            was_helpful=True,
        )
    )

    from knowledge_mcp import dynamodb as db

    usage = db.get_usage_metadata("docs/knowledge/databases/acid.md")
    assert usage["helpful_count"] == 1
