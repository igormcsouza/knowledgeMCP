import math
from dataclasses import dataclass
from datetime import date, datetime

import boto3

from knowledge_mcp.config import table_name

@dataclass
class ChunkRecord:
    article_path: str
    chunk_id: str
    title: str
    category: str
    section: str
    text: str
    tags: list[str]
    embedding: list[float]
    indexed_at: str


def _resource():
    # Not module-level: created lazily so tests can activate moto's mock_aws
    # context before the first real client is constructed.
    return boto3.resource("dynamodb")


def _content_table():
    return _resource().Table(table_name("content-index"))


def _usage_table():
    return _resource().Table(table_name("usage-tracking"))


def _to_chunk_record(item: dict) -> ChunkRecord:
    return ChunkRecord(
        article_path=item["article_path"],
        chunk_id=item["chunk_id"],
        title=item.get("title", ""),
        category=item.get("category", ""),
        section=item.get("section", ""),
        text=item.get("text", ""),
        tags=list(item.get("tags", [])),
        embedding=[float(v) for v in item.get("embedding", [])],
        indexed_at=item.get("indexed_at", ""),
    )


def scan_all_chunks() -> list[ChunkRecord]:
    """Brute-force cosine similarity needs every chunk in memory — fine at
    this KB's scale (PLAN.md 1.2); revisit only if this gets slow."""
    table = _content_table()
    records: list[ChunkRecord] = []
    kwargs: dict = {}
    while True:
        response = table.scan(**kwargs)
        records.extend(_to_chunk_record(item) for item in response.get("Items", []))
        if "LastEvaluatedKey" not in response:
            break
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return records


def get_article_chunks(article_path: str) -> list[ChunkRecord]:
    table = _content_table()
    response = table.query(
        KeyConditionExpression="article_path = :p",
        ExpressionAttributeValues={":p": article_path},
    )
    records = [_to_chunk_record(item) for item in response.get("Items", [])]
    records.sort(key=lambda r: int(r.chunk_id.rsplit("#", 1)[-1]))
    return records


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def get_usage_metadata(article_path: str) -> dict | None:
    return _usage_table().get_item(Key={"article_path": article_path}).get("Item")


def scan_usage_metadata() -> list[dict]:
    table = _usage_table()
    items: list[dict] = []
    kwargs: dict = {}
    while True:
        response = table.scan(**kwargs)
        items.extend(response.get("Items", []))
        if "LastEvaluatedKey" not in response:
            break
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return items


def record_query_feedback(article_path: str, was_helpful: bool) -> None:
    """Writes back to usage tracking (PLAN.md 3.8), closing the loop so
    find_weak_concepts / suggest_review_queue improve over time."""
    table = _usage_table()
    today = date.today().isoformat()
    table.update_item(
        Key={"article_path": article_path},
        UpdateExpression=(
            "SET last_queried_date = :today, "
            "query_count = if_not_exists(query_count, :zero) + :one, "
            "helpful_count = if_not_exists(helpful_count, :zero) + :helpful_inc, "
            "unhelpful_count = if_not_exists(unhelpful_count, :zero) + :unhelpful_inc"
        ),
        ExpressionAttributeValues={
            ":today": today,
            ":zero": 0,
            ":one": 1,
            ":helpful_inc": 1 if was_helpful else 0,
            ":unhelpful_inc": 0 if was_helpful else 1,
        },
    )


def record_query_hit(article_path: str) -> None:
    """Bumps query_count/last_queried_date on plain lookups (search_concept,
    recall_solution, etc.) even without explicit feedback."""
    table = _usage_table()
    today = date.today().isoformat()
    table.update_item(
        Key={"article_path": article_path},
        UpdateExpression=(
            "SET last_queried_date = :today, "
            "query_count = if_not_exists(query_count, :zero) + :one"
        ),
        ExpressionAttributeValues={":today": today, ":zero": 0, ":one": 1},
    )


def days_since(date_str: str | None) -> int | None:
    if not date_str:
        return None
    parsed = datetime.strptime(date_str, "%Y-%m-%d").date()
    return (date.today() - parsed).days
