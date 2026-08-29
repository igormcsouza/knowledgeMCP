import boto3
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from knowledge_mcp.config import BEARER_TOKEN_SECRET_ARN

_cached_token: str | None = None


def _get_expected_token() -> str | None:
    """Static bearer token from Secrets Manager, cached across warm
    invocations (PLAN.md 2.3). None (auth disabled) only when no ARN is
    configured, e.g. local dev."""
    global _cached_token
    if _cached_token is not None:
        return _cached_token
    if not BEARER_TOKEN_SECRET_ARN:
        return None
    client = boto3.client("secretsmanager")
    _cached_token = client.get_secret_value(SecretId=BEARER_TOKEN_SECRET_ARN)[
        "SecretString"
    ]
    return _cached_token


class BearerAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        expected = _get_expected_token()
        if expected is None:
            return await call_next(request)

        header = request.headers.get("authorization", "")
        if header != f"Bearer {expected}":
            return JSONResponse({"error": "unauthorized"}, status_code=401)

        return await call_next(request)
