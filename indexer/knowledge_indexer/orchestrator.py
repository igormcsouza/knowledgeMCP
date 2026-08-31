import logging

from knowledge_indexer.chunker import chunk_article
from knowledge_indexer.config import GITHUB_BRANCH, GITHUB_REPO
from knowledge_indexer.embeddings import embed_texts
from knowledge_indexer.github_fetcher import (
    fetch_article_content,
    get_repo,
    list_tree_entries,
)
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

    The sha diff happens *before* fetching any article body: listing the
    tree costs one GitHub API call regardless of repo size, but fetching a
    file's content is a call per file — the part that counts against the
    (unauthenticated, shared-IP-pool) rate limit. Diffing first keeps a
    quiet day's run to a couple of calls instead of one per article.
    """
    logger.info("Listing article tree from %s@%s", GITHUB_REPO, GITHUB_BRANCH)
    repo = get_repo(GITHUB_REPO)
    entries = list_tree_entries(repo, branch=GITHUB_BRANCH)
    logger.info("Found %d articles", len(entries))

    indexed_shas = get_indexed_file_shas()

    current_paths = {entry.path for entry in entries}
    stale_paths = set(indexed_shas) - current_paths

    changed_entries, skipped = [], []
    for entry in entries:
        if indexed_shas.get(entry.path) == entry.sha:
            skipped.append(entry.path)
        else:
            changed_entries.append(entry)

    reindexed = []
    for i, entry in enumerate(changed_entries, start=1):
        logger.info("[%d/%d] Indexing %s", i, len(changed_entries), entry.path)
        article = fetch_article_content(repo, GITHUB_BRANCH, entry)
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
