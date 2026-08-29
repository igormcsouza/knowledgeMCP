from mcp.server.fastmcp import FastMCP

# stateless_http=True: this Lambda is a request/response server, never holds
# session state between invocations (indexing happens in the separate
# indexer Lambda). streamable-http is the current transport; SSE-only is
# legacy (PLAN.md 2.1).
mcp = FastMCP("knowledge-base-mcp", stateless_http=True, json_response=True)
