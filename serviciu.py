"""Laborator 4 SI - cod comun pentru serviciile MCP: cardul serverului și pornirea pe HTTP."""
from fastmcp import FastMCP
from starlette.responses import JSONResponse

CARD_SCHEMA = "https://static.modelcontextprotocol.io/schemas/v1/server-card.schema.json"
CARD_TYPE = "application/mcp-server-card+json"
PROTOCOL = "2026-07-28"


def server_card(mcp: FastMCP, port: int, description: str, title: str) -> dict:
    """Cardul serverului (SEP-2127): identitate și conexiune, FĂRĂ lista de instrumente."""
    return {
        "$schema": CARD_SCHEMA,
        "name": mcp.name,                      # format reverse-DNS: spațiu/nume
        "version": mcp.version,
        "title": title,
        "description": description,            # maximum 100 de caractere
        "remotes": [{
            "type": "streamable-http",
            "url": f"http://127.0.0.1:{port}/mcp",
            "supportedProtocolVersions": [PROTOCOL],
        }],
    }


def run_http(mcp: FastMCP, port: int, description: str, title: str):
    """Publică cardul la <url-mcp>/server-card și pornește serverul pe Streamable HTTP."""
    card = server_card(mcp, port, description, title)

    @mcp.custom_route("/mcp/server-card", methods=["GET"])
    async def _card(request):
        return JSONResponse(card, media_type=CARD_TYPE)

    print(f"{mcp.name} v{mcp.version}: http://127.0.0.1:{port}/mcp (card: .../mcp/server-card)")
    mcp.run(transport="http", host="127.0.0.1", port=port,
            host_origin_protection=True, show_banner=False)
