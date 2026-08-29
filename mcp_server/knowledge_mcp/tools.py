from collections import defaultdict

from mcp.server.fastmcp import FastMCP

from knowledge_mcp import dynamodb
from knowledge_mcp.bedrock import embed_query
from knowledge_mcp.github import get_file_history
from knowledge_mcp.review_graph import suggest_review_queue as _suggest_review_queue

_TROUBLESHOOTING_CATEGORY = "troubleshooting"


def _top_chunks_by_similarity(query_embedding: list[float], k: int) -> list[tuple]:
    chunks = dynamodb.scan_all_chunks()
    scored = [
        (dynamodb.cosine_similarity(query_embedding, c.embedding), c) for c in chunks
    ]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return scored[:k]


def _chunk_summary(score: float, chunk) -> dict:
    return {
        "article_path": chunk.article_path,
        "title": chunk.title,
        "category": chunk.category,
        "section": chunk.section,
        "text": chunk.text,
        "score": round(score, 4),
    }


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    def search_concept(query: str, top_k: int = 5) -> list[dict]:
        """Semantic search across the knowledge base. Returns top-k chunks
        with article title/path/section (PLAN.md 3.1)."""
        embedding = embed_query(query)
        results = _top_chunks_by_similarity(embedding, top_k)
        for _, chunk in results:
            dynamodb.record_query_hit(chunk.article_path)
        return [_chunk_summary(score, chunk) for score, chunk in results]

    @mcp.tool()
    def find_weak_concepts(topic: str | None = None, limit: int = 10) -> list[dict]:
        """Surfaces articles/sections with low word count, few internal
        links, or low edit history — optionally filtered by topic
        (PLAN.md 3.2)."""
        chunks = dynamodb.scan_all_chunks()
        by_article: dict[str, list] = defaultdict(list)
        for chunk in chunks:
            by_article[chunk.article_path].append(chunk)

        usage_by_article = {u["article_path"]: u for u in dynamodb.scan_usage_metadata()}

        scored = []
        for article_path, article_chunks in by_article.items():
            first = article_chunks[0]
            if topic and topic.lower() not in first.category.lower() and not any(
                topic.lower() in t.lower() for t in first.tags
            ):
                continue

            full_text = "\n".join(c.text for c in article_chunks)
            word_count = len(full_text.split())
            internal_links = full_text.count("](")
            usage = usage_by_article.get(article_path, {})
            edit_count = int(usage.get("edit_count", 0))

            weakness_score = word_count + internal_links * 10 + edit_count * 5
            scored.append(
                {
                    "article_path": article_path,
                    "title": first.title,
                    "category": first.category,
                    "word_count": word_count,
                    "internal_links": internal_links,
                    "edit_count": edit_count,
                    "weakness_score": weakness_score,
                }
            )

        scored.sort(key=lambda a: a["weakness_score"])
        return scored[:limit]

    @mcp.tool()
    def get_article_context(article_path: str) -> dict:
        """Returns full article content, for grounding a follow-up
        explanation (PLAN.md 3.3)."""
        chunks = dynamodb.get_article_chunks(article_path)
        if not chunks:
            return {"error": f"no article found at {article_path}"}
        dynamodb.record_query_hit(article_path)
        return {
            "article_path": article_path,
            "title": chunks[0].title,
            "category": chunks[0].category,
            "tags": chunks[0].tags,
            "content": "\n\n".join(c.text for c in chunks),
        }

    @mcp.tool()
    def list_related_concepts(concept: str, top_k: int = 5) -> list[dict]:
        """Embedding-similarity lookup for adjacent articles not directly
        asked about (PLAN.md 3.4)."""
        embedding = embed_query(concept)
        scored = _top_chunks_by_similarity(embedding, top_k * 3)

        seen_articles: set[str] = set()
        related = []
        for score, chunk in scored:
            if chunk.article_path in seen_articles:
                continue
            seen_articles.add(chunk.article_path)
            related.append(_chunk_summary(score, chunk))
            if len(related) >= top_k:
                break
        return related

    @mcp.tool()
    def recall_solution(problem_description: str, top_k: int = 5) -> list[dict]:
        """Search tuned toward troubleshooting/fix-tagged content — the
        intent differs from concept lookup so results from the
        troubleshooting category are boosted (PLAN.md 3.5)."""
        embedding = embed_query(problem_description)
        chunks = dynamodb.scan_all_chunks()

        scored = []
        for chunk in chunks:
            score = dynamodb.cosine_similarity(embedding, chunk.embedding)
            if chunk.category == _TROUBLESHOOTING_CATEGORY or "fix" in chunk.tags:
                score *= 1.2
            scored.append((score, chunk))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        top = scored[:top_k]
        for _, chunk in top:
            dynamodb.record_query_hit(chunk.article_path)
        return [_chunk_summary(score, chunk) for score, chunk in top]

    @mcp.tool()
    def get_recently_added(days: int = 7) -> list[dict]:
        """Lists articles/sections added or edited in the last N days
        (PLAN.md 3.6)."""
        chunks = dynamodb.scan_all_chunks()
        seen: dict[str, dict] = {}
        for chunk in chunks:
            age = dynamodb.days_since(chunk.indexed_at)
            if age is None or age > days:
                continue
            if chunk.article_path not in seen:
                seen[chunk.article_path] = {
                    "article_path": chunk.article_path,
                    "title": chunk.title,
                    "category": chunk.category,
                    "indexed_at": chunk.indexed_at,
                }
        return sorted(seen.values(), key=lambda a: a["indexed_at"], reverse=True)

    @mcp.tool()
    def log_query_feedback(concept_article_path: str, was_helpful: bool) -> dict:
        """Writes back to the usage-tracking table, closing the loop so
        weak-concept detection improves over time (PLAN.md 3.8)."""
        dynamodb.record_query_feedback(concept_article_path, was_helpful)
        return {"status": "recorded", "article_path": concept_article_path}

    @mcp.tool()
    def get_article_history(article_path: str, limit: int = 20) -> list[dict]:
        """Returns git log for a file, showing how a concept/fix evolved
        over time (PLAN.md 3.9)."""
        return get_file_history(article_path, limit=limit)

    @mcp.tool()
    def suggest_review_queue(limit: int = 10) -> list[dict]:
        """Combines weak concepts + stale (not queried recently) + old-and-
        never-revisited content into a prioritized review list (PLAN.md
        3.7). The only tool backed by a LangGraph graph."""
        return _suggest_review_queue(limit=limit)
