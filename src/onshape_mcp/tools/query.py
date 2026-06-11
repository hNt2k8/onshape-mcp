"""MCP tools: entity finding + FeatureScript evaluation (query escape hatch)."""

from __future__ import annotations

from typing import Any, Callable

from mcp.server.fastmcp import FastMCP

from ..api import partstudio as api
from ..client import OnshapeClient
from ..queries import build_find_entities_script, filter_entities
from ..units import to_meters


def register(mcp: FastMCP, get_client: Callable[[], OnshapeClient]) -> None:
    @mcp.tool()
    def find_entities(
        documentId: str,
        workspaceId: str,
        elementId: str,
        entityType: str,
        createdByFeatureId: str = "",
        geometryType: str = "",
        nearPoint: list[float] | None = None,
        radiusBetween: list[float] | None = None,
        units: str = "in",
        maxResults: int = 25,
    ) -> list[dict[str, Any]]:
        """Find entities (transient ids + geometry) for use in fillet/revolve/
        pattern/plane selections. entityType: VERTEX|EDGE|FACE|BODY.
        Optional filters: createdByFeatureId (entities a feature created),
        geometryType (EDGE: LINE|CIRCLE|ELLIPSE|OTHER_CURVE; FACE: PLANE|
        CYLINDER|CONE|SPHERE|TORUS), nearPoint [x,y,z] (sorts by distance),
        radiusBetween [min,max]. nearPoint/radiusBetween are in `units`
        (default inches); returned geometry is in METERS.

        WARNING: returned ids are transient — invalidated by ANY mutation.
        Re-run find_entities after every modeling call; never cache ids."""
        script = build_find_entities_script(
            entityType, createdByFeatureId or None, geometryType or None
        )
        outcome = api.eval_featurescript(
            get_client(), documentId, workspaceId, elementId, script
        )
        entities = outcome.get("result") or []
        if not isinstance(entities, list):
            return [{"error": "unexpected FeatureScript result", "raw": entities}]
        near_m = (
            [to_meters(value, units) for value in nearPoint] if nearPoint else None
        )
        radius_m = (
            (to_meters(radiusBetween[0], units), to_meters(radiusBetween[1], units))
            if radiusBetween
            else None
        )
        return filter_entities(entities, near_m, radius_m, maxResults)
    @mcp.tool()
    def get_variables(
        documentId: str, workspaceId: str, elementId: str
    ) -> list[dict[str, Any]]:
        """List all variables visible to a Part Studio (set_variable results
        and any referenced Variable Studios), with evaluated values."""
        return api.get_variables(get_client(), documentId, workspaceId, elementId)

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
