import hashlib
import hmac
import json
import os

import boto3


def verify_signature(body: bytes, signature_header: str | None, secret: str) -> bool:
    """Validate GitHub's X-Hub-Signature-256 header (sha256=<hexdigest>)."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature_header)


def is_push_to_watched_branch(payload: dict, branch: str) -> bool:
    return payload.get("ref") == f"refs/heads/{branch}"


def extract_head_sha(payload: dict) -> str | None:
    return payload.get("after")


def parse_webhook_event(event: dict) -> tuple[dict, bytes, str | None]:
    """Extract (json payload, raw body bytes, signature header) from an
    API Gateway / Function URL Lambda proxy event."""
    body = event.get("body", "")
    if event.get("isBase64Encoded"):
        import base64

        raw = base64.b64decode(body)
    else:
        raw = body.encode() if isinstance(body, str) else body

    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    signature = headers.get("x-hub-signature-256")
    payload = json.loads(raw) if raw else {}
    return payload, raw, signature


_cached_webhook_secret: str | None = None


def get_webhook_secret() -> str | None:
    """Fetch the HMAC secret from SSM Parameter Store, cached across warm
    invocations. Returns None (skip verification) only when no param name is
    configured, e.g. local/test runs."""
    global _cached_webhook_secret
    if _cached_webhook_secret is not None:
        return _cached_webhook_secret

    param_name = os.environ.get("GITHUB_WEBHOOK_SECRET_PARAM")
    if not param_name:
        return None

    client = boto3.client("ssm")
    _cached_webhook_secret = client.get_parameter(Name=param_name, WithDecryption=True)[
        "Parameter"
    ]["Value"]
    return _cached_webhook_secret
