from mangum import Mangum

from knowledge_mcp.app import build_asgi_app

handler = Mangum(build_asgi_app())
