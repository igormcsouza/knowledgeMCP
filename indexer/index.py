import json
import logging
import os

from knowledge_indexer.config import GITHUB_BRANCH
from knowledge_indexer.orchestrator import run_index
from knowledge_indexer.webhook import (
    extract_head_sha,
    get_webhook_secret,
    is_push_to_watched_branch,
    parse_webhook_event,
    verify_signature,
)

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger("knowledge-indexer")


def handler(event, context):
    """Two trigger shapes land here (PLAN.md 1.4):

    - EventBridge scheduled rule: event has no "headers"/"body" — full scan.
    - GitHub webhook (Function URL push): API-Gateway-style proxy event with
      an HMAC signature to verify before trusting the payload.
    """
    if "headers" in event and "body" in event:
        return _handle_webhook(event)
    return _handle_scheduled_run()


def _handle_scheduled_run() -> dict:
    logger.info("Running scheduled full index")
    result = run_index()
    return {"statusCode": 200, "body": json.dumps(result)}


def _handle_webhook(event) -> dict:
    payload, raw_body, signature = parse_webhook_event(event)

    secret = get_webhook_secret()
    if secret and not verify_signature(raw_body, signature, secret):
        logger.warning("Webhook signature verification failed")
        return {"statusCode": 401, "body": "invalid signature"}

    if not is_push_to_watched_branch(payload, GITHUB_BRANCH):
        logger.info("Ignoring webhook push to non-watched ref: %s", payload.get("ref"))
        return {"statusCode": 200, "body": "ignored"}

    head_sha = extract_head_sha(payload)
    logger.info("Running webhook-triggered index for commit %s", head_sha)
    result = run_index(head_sha=head_sha)
    return {"statusCode": 200, "body": json.dumps(result)}
