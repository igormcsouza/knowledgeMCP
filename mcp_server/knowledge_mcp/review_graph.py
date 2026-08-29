from collections import defaultdict
from typing import TypedDict

from langgraph.graph import END, StateGraph

from knowledge_mcp import dynamodb

# The one tool that reasons over several data sources rather than doing a
# single lookup (PLAN.md 3.7) — LangGraph is scoped to exactly this tool.

_STALE_DAYS_THRESHOLD = 30
_UNTOUCHED_DAYS_THRESHOLD = 90
_WEAK_WORD_COUNT_THRESHOLD = 150


class ReviewState(TypedDict, total=False):
    articles: dict[str, dict]  # article_path -> {title, category, word_count}
    usage_by_article: dict[str, dict]
    weak: list[str]
    stale: list[str]
    untouched: list[str]
    ranked: list[dict]


def _fetch_weak_concepts(state: ReviewState) -> ReviewState:
    chunks = dynamodb.scan_all_chunks()
    articles: dict[str, dict] = {}
    text_by_article: dict[str, list[str]] = defaultdict(list)
    for chunk in chunks:
        text_by_article[chunk.article_path].append(chunk.text)
        if chunk.article_path not in articles:
            articles[chunk.article_path] = {
                "title": chunk.title,
                "category": chunk.category,
            }

    weak = []
    for article_path, texts in text_by_article.items():
        word_count = len(" ".join(texts).split())
        articles[article_path]["word_count"] = word_count
        if word_count < _WEAK_WORD_COUNT_THRESHOLD:
            weak.append(article_path)

    return {**state, "articles": articles, "weak": weak}


def _fetch_stale_concepts(state: ReviewState) -> ReviewState:
    usage_by_article = {u["article_path"]: u for u in dynamodb.scan_usage_metadata()}
    stale = []
    for article_path in state["articles"]:
        usage = usage_by_article.get(article_path)
        age = dynamodb.days_since(usage.get("last_queried_date")) if usage else None
        # Never queried counts as maximally stale, not exempt.
        if age is None or age >= _STALE_DAYS_THRESHOLD:
            stale.append(article_path)

    return {**state, "usage_by_article": usage_by_article, "stale": stale}


def _fetch_untouched_concepts(state: ReviewState) -> ReviewState:
    untouched = []
    for article_path in state["articles"]:
        usage = state["usage_by_article"].get(article_path)
        age = dynamodb.days_since(usage.get("first_seen_date")) if usage else None
        if age is not None and age >= _UNTOUCHED_DAYS_THRESHOLD and int(
            (usage or {}).get("query_count", 0)
        ) == 0:
            untouched.append(article_path)

    return {**state, "untouched": untouched}


def _merge_and_rank(state: ReviewState) -> ReviewState:
    weak, stale, untouched = (
        set(state["weak"]),
        set(state["stale"]),
        set(state["untouched"]),
    )
    all_flagged = weak | stale | untouched

    ranked = []
    for article_path in all_flagged:
        info = state["articles"][article_path]
        # Priority: an article hitting all three signals needs review first.
        priority = (
            (article_path in weak)
            + (article_path in stale)
            + (article_path in untouched)
        )
        ranked.append(
            {
                "article_path": article_path,
                "title": info["title"],
                "category": info["category"],
                "priority": priority,
                "reasons": [
                    label
                    for label, flagged in (
                        ("weak_content", article_path in weak),
                        ("stale_not_queried", article_path in stale),
                        ("untouched_since_created", article_path in untouched),
                    )
                    if flagged
                ],
            }
        )

    ranked.sort(key=lambda r: r["priority"], reverse=True)
    return {**state, "ranked": ranked}


_graph = None


def _build_graph():
    global _graph
    if _graph is not None:
        return _graph

    builder = StateGraph(ReviewState)
    builder.add_node("fetch_weak_concepts", _fetch_weak_concepts)
    builder.add_node("fetch_stale_concepts", _fetch_stale_concepts)
    builder.add_node("fetch_untouched_concepts", _fetch_untouched_concepts)
    builder.add_node("merge_and_rank", _merge_and_rank)

    builder.set_entry_point("fetch_weak_concepts")
    builder.add_edge("fetch_weak_concepts", "fetch_stale_concepts")
    builder.add_edge("fetch_stale_concepts", "fetch_untouched_concepts")
    builder.add_edge("fetch_untouched_concepts", "merge_and_rank")
    builder.add_edge("merge_and_rank", END)

    _graph = builder.compile()
    return _graph


def suggest_review_queue(limit: int = 10) -> list[dict]:
    graph = _build_graph()
    initial_state: ReviewState = {
        "articles": {},
        "usage_by_article": {},
        "weak": [],
        "stale": [],
        "untouched": [],
        "ranked": [],
    }
    result: ReviewState = graph.invoke(initial_state)
    return result["ranked"][:limit]
