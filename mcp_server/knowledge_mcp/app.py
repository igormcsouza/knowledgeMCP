from mcp.server.fastmcp import FastMCP

from knowledge_mcp.tools import register_tools

# stateless_http=True: this Lambda is a request/response server, never holds
# session state between invocations (indexing happens in the separate
# indexer Lambda). streamable-http is the current transport; SSE-only is
# legacy (PLAN.md 2.1).
mcp = FastMCP("knowledge-base-mcp", stateless_http=True, json_response=True)

register_tools(mcp)


def build_asgi_app():
    # No auth middleware: the claude.ai web/desktop custom-connector UI only
    # supports OAuth, not a static bearer header, and this is a personal,
    # read-mostly KB behind an unguessable Function URL. See auth.py if
    # OAuth or bearer-header auth (e.g. Claude Code CLI) is added later.
    return mcp.streamable_http_app()
