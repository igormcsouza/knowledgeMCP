from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from knowledge_mcp.tools import register_tools


def build_asgi_app():
    # A fresh FastMCP instance per call, not a module-level singleton: its
    # StreamableHTTPSessionManager is created lazily and Mangum runs the
    # ASGI lifespan (which calls session_manager.run()) on every Lambda
    # invocation, but that manager raises "can only be called once per
    # instance" on its second run. Rebuilding here means each invocation
    # gets its own manager, avoiding the crash entirely.
    #
    # stateless_http=True: this Lambda is a request/response server, never
    # holds session state between invocations (indexing happens in the
    # separate indexer Lambda). streamable-http is the current transport;
    # SSE-only is legacy (PLAN.md 2.1).
    mcp = FastMCP(
        "knowledge-base-mcp",
        stateless_http=True,
        json_response=True,
        # The MCP SDK's DNS-rebinding protection rejects any Host header
        # that isn't localhost by default (surfaces to clients as a 421).
        # Lambda Function URLs have no fixed, known-in-advance hostname to
        # allowlist and this endpoint is public/unauthenticated read access
        # anyway, so the protection buys nothing here — disable it.
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=False
        ),
    )
    register_tools(mcp)

    # No auth middleware: the claude.ai web/desktop custom-connector UI only
    # supports OAuth, not a static bearer header, and this is a personal,
    # read-mostly KB behind an unguessable Function URL. See git history for
    # a bearer-token middleware if OAuth or header auth is added later.
    return mcp.streamable_http_app()
