import hashlib
import hmac

from knowledge_indexer.webhook import (
    extract_head_sha,
    is_push_to_watched_branch,
    verify_signature,
)


def _sign(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_verify_signature_accepts_valid():
    body = b'{"ref": "refs/heads/main"}'
    secret = "topsecret"
    assert verify_signature(body, _sign(body, secret), secret)


def test_verify_signature_rejects_wrong_secret():
    body = b'{"ref": "refs/heads/main"}'
    assert not verify_signature(body, _sign(body, "wrong"), "topsecret")


def test_verify_signature_rejects_missing_header():
    assert not verify_signature(b"{}", None, "topsecret")


def test_is_push_to_watched_branch():
    assert is_push_to_watched_branch({"ref": "refs/heads/main"}, "main")
    assert not is_push_to_watched_branch({"ref": "refs/heads/feature"}, "main")


def test_extract_head_sha():
    assert extract_head_sha({"after": "abc123"}) == "abc123"
