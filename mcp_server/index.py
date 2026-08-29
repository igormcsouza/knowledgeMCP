from mangum import Mangum

from knowledge_mcp.app import build_asgi_app


def handler(event, context):
    # Built per invocation, not cached at module scope — see build_asgi_app
    # for why the ASGI app (and its session manager) can't be reused across
    # warm Lambda invocations.
    return Mangum(build_asgi_app())(event, context)
