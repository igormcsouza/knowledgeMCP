import logging

from knowledge_indexer.chunker import chunk_article
from knowledge_indexer.config import GITHUB_BRANCH, GITHUB_REPO
from knowledge_indexer.embeddings import embed_texts
from knowledge_indexer.github_fetcher import fetch_articles
from knowledge_indexer.storage import (
    delete_article_chunks,
    get_indexed_file_shas,
    remove_usage_metadata,
    set_last_indexed_sha,
    touch_usage_metadata,
    write_article_chunks,
)

logger = logging.getLogger(__name__)


def run_index(head_sha: str | None = None) -> dict:
    """Re-index every article whose git blob sha changed since last run.

    Runs the same way whether triggered by the webhook (PLAN.md 1.4, push
    event) or the daily EventBridge schedule — both call this with no
    filtering beyond the per-file sha diff, so a missed webhook is simply
    caught on the next scheduled pass with zero duplicate work for anything
    already current.
    """
    articles = fetch_articles(repo_name=GITHUB_REPO, branch=GITHUB_BRANCH)
    indexed_shas = get_indexed_file_shas()

    current_paths = {article.path for article in articles}
    stale_paths = set(indexed_shas) - current_paths

    reindexed, skipped = [], []
    for article in articles:
        if indexed_shas.get(article.path) == article.sha:
            skipped.append(article.path)
            continue

        chunks = chunk_article(article.path, article.content)
        embeddings = embed_texts([c.text for c in chunks])

        delete_article_chunks(article.path)
        write_article_chunks(
            article_path=article.path,
            file_sha=article.sha,
            category=article.category,
            title=article.title,
            tags=article.tags,
            chunks=chunks,
            embeddings=embeddings,
        )
        touch_usage_metadata(
            article.path,
            edit_count_increment=1 if article.path in indexed_shas else 0,
        )
        reindexed.append(article.path)

    for path in stale_paths:
        delete_article_chunks(path)
        remove_usage_metadata(path)

    if head_sha:
        set_last_indexed_sha(GITHUB_REPO, head_sha)

    result = {
        "reindexed": reindexed,
        "skipped_unchanged": len(skipped),
        "removed": list(stale_paths),
    }
    logger.info("Index run complete: %s", result)
    return result
