"""MCP tools: FeatureScript evaluation (universal query escape hatch)."""

from __future__ import annotations

from typing import Any, Callable

from mcp.server.fastmcp import FastMCP

from ..api import partstudio as api
from ..client import OnshapeClient


def register(mcp: FastMCP, get_client: Callable[[], OnshapeClient]) -> None:
    @mcp.tool()
    def eval_featurescript(
        documentId: str,
        workspaceId: str,
        elementId: str,
        script: str,
    ) -> dict[str, Any]:
        """Evaluate a FeatureScript function against a Part Studio and return
        the parsed result. `script` must be a complete function, e.g.:

          function(context is Context, queries) {
              return transientQueriesToStrings(
                  evaluateQuery(context, qEverything(EntityType.FACE)));
          }

        Lengths are in METERS, angles in RADIANS. Transient IDs returned here
        are invalidated by ANY document mutation — re-query after every change.
        """
        return api.eval_featurescript(
            get_client(), documentId, workspaceId, elementId, script
        )
