"""FastMCP application (stdio transport).

stdio rule: NEVER write to stdout — it is the MCP protocol channel and any
stray print corrupts framing. All logging/diagnostics go to stderr.

Tool groups are registered here as they land (M1+): documents, modeling,
query, export.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("onshape")


def run() -> None:
    mcp.run()
