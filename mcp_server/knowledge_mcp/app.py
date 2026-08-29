from mcp.server.fastmcp import FastMCP

from knowledge_mcp.auth import BearerAuthMiddleware
from knowledge_mcp.tools import register_tools

# stateless_http=True: this Lambda is a request/response server, never holds
# session state between invocations (indexing happens in the separate
# indexer Lambda). streamable-http is the current transport; SSE-only is
# legacy (PLAN.md 2.1).
mcp = FastMCP("knowledge-base-mcp", stateless_http=True, json_response=True)

register_tools(mcp)


def build_asgi_app():
    app = mcp.streamable_http_app()
    app.add_middleware(BearerAuthMiddleware)
    return app
