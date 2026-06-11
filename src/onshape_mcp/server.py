"""FastMCP application (stdio transport).

stdio rule: NEVER write to stdout — it is the MCP protocol channel and any
stray print corrupts framing. All logging/diagnostics go to stderr.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .client import OnshapeClient
from .config import load_config
from .tools import documents, modeling, query

mcp = FastMCP("onshape")

_client: OnshapeClient | None = None


def get_client() -> OnshapeClient:
    """One shared client per server process, created lazily so config errors
    surface inside tool results instead of killing the server at startup."""
    global _client
    if _client is None:
        _client = OnshapeClient(load_config())
    return _client


documents.register(mcp, get_client)
modeling.register(mcp, get_client)
query.register(mcp, get_client)


def run() -> None:
    mcp.run()
