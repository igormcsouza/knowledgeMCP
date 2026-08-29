from mangum import Mangum

from knowledge_mcp.app import mcp

handler = Mangum(mcp.streamable_http_app())
