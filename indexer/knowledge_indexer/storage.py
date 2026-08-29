from datetime import date

import boto3

from knowledge_indexer.config import table_name


def _resource():
    return boto3.resource("dynamodb")


def get_last_indexed_sha(repo: str) -> str | None:
    table = _resource().Table(table_name("indexer-state"))
    item = table.get_item(Key={"repo": repo}).get("Item")
    return item.get("last_commit_sha") if item else None


def set_last_indexed_sha(repo: str, commit_sha: str) -> None:
    table = _resource().Table(table_name("indexer-state"))
    table.put_item(Item={"repo": repo, "last_commit_sha": commit_sha})


def get_indexed_file_shas() -> dict[str, str]:
    """article_path -> git blob sha for every article currently indexed.

    Used to skip re-embedding unchanged files even on a full (non-diffed)
    scan, e.g. the daily EventBridge fallback run.
    """
    table = _resource().Table(table_name("content-index"))
    shas: dict[str, str] = {}
    kwargs = {"ProjectionExpression": "article_path, file_sha"}
    while True:
        response = table.scan(**kwargs)
        for item in response.get("Items", []):
            shas[item["article_path"]] = item.get("file_sha", "")
        if "LastEvaluatedKey" not in response:
            break
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return shas


def delete_article_chunks(article_path: str) -> None:
    table = _resource().Table(table_name("content-index"))
    response = table.query(
        KeyConditionExpression="article_path = :p",
        ExpressionAttributeValues={":p": article_path},
        ProjectionExpression="article_path, chunk_id",
    )
    with table.batch_writer() as batch:
        for item in response.get("Items", []):
            batch.delete_item(
                Key={"article_path": item["article_path"], "chunk_id": item["chunk_id"]}
            )


def write_article_chunks(
    article_path: str,
    file_sha: str,
    category: str,
    title: str,
    tags: list[str],
    chunks: list,
    embeddings: list[list[float]],
) -> None:
    table = _resource().Table(table_name("content-index"))
    today = date.today().isoformat()
    with table.batch_writer() as batch:
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            batch.put_item(
                Item={
                    "article_path": article_path,
                    "chunk_id": chunk.chunk_id,
                    "file_sha": file_sha,
                    "category": category,
                    "title": title,
                    "tags": tags,
                    "section": chunk.section,
                    "text": chunk.text,
                    "embedding": [str(v) for v in embedding],
                    "indexed_at": today,
                }
            )


def touch_usage_metadata(article_path: str, edit_count_increment: int = 0) -> None:
    """Record first-seen date on a new article; bump edit_count on re-index."""
    table = _resource().Table(table_name("usage-tracking"))
    today = date.today().isoformat()
    table.update_item(
        Key={"article_path": article_path},
        UpdateExpression=(
            "SET first_seen_date = if_not_exists(first_seen_date, :today), "
            "query_count = if_not_exists(query_count, :zero), "
            "edit_count = if_not_exists(edit_count, :zero) + :inc"
        ),
        ExpressionAttributeValues={
            ":today": today,
            ":zero": 0,
            ":inc": edit_count_increment,
        },
    )


def remove_usage_metadata(article_path: str) -> None:
    table = _resource().Table(table_name("usage-tracking"))
    table.delete_item(Key={"article_path": article_path})
