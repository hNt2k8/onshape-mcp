"""MCP tools: modeling (sketch/extrude builders + raw feature escape hatch)."""

from __future__ import annotations

import math
from typing import Any, Callable

from mcp.server.fastmcp import FastMCP

from ..api import partstudio as api
from ..btm import features as btm_features
from ..btm import params as btm_params
from ..btm import sketch as btm_sketch
from ..client import OnshapeClient
from ..units import length_expression, to_meters


def _plane_query(plane: dict[str, Any]) -> dict[str, Any]:
    if "default" in plane:
        return btm_params.default_plane_query(plane["default"])
    if "faceId" in plane:
        return btm_params.deterministic_query([plane["faceId"]])
    raise ValueError(
        'plane must be {"default": "TOP|FRONT|RIGHT"} or {"faceId": "<transient id>"}'
    )


def _build_entities(specs: list[dict[str, Any]], units: str) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []
    for i, spec in enumerate(specs, start=1):
        kind = spec.get("type")
        eid = f"e{i}"
        m = lambda key: to_meters(float(spec[key]), units)  # noqa: E731
        if kind == "line":
            entities.append(
                btm_sketch.line(m("x1"), m("y1"), m("x2"), m("y2"), eid)
            )
        elif kind == "circle":
            entities.append(btm_sketch.circle(m("xc"), m("yc"), m("r"), eid))
        elif kind == "arc":
            entities.append(
                btm_sketch.arc(
                    m("xc"),
                    m("yc"),
                    m("r"),
                    math.radians(float(spec["startAngleDeg"])),
                    math.radians(float(spec["endAngleDeg"])),
                    eid,
                )
            )
        elif kind == "rect":
            entities.extend(
                btm_sketch.rectangle(m("x1"), m("y1"), m("x2"), m("y2"), eid)
            )
        elif kind == "polygon":
            points = [
                (to_meters(float(px), units), to_meters(float(py), units))
                for px, py in spec["points"]
            ]
            entities.extend(btm_sketch.polygon(points, eid))
        else:
            raise ValueError(
                f"entity {i}: type must be line|circle|arc|rect|polygon, got {kind!r}"
            )
    return entities


def register(mcp: FastMCP, get_client: Callable[[], OnshapeClient]) -> None:
    @mcp.tool()
    def create_sketch(
        documentId: str,
        workspaceId: str,
        elementId: str,
        name: str,
        plane: dict[str, Any],
        entities: list[dict[str, Any]],
        units: str = "in",
    ) -> dict[str, Any]:
        """Create a sketch from simple 2D entities (coordinates in `units`,
        default inches). plane is {"default": "TOP|FRONT|RIGHT"} (zero extra
        API calls) or {"faceId": "<transient id from find_entities>"}.

        Entity specs:
          {"type": "line", "x1", "y1", "x2", "y2"}
          {"type": "circle", "xc", "yc", "r"}
          {"type": "arc", "xc", "yc", "r", "startAngleDeg", "endAngleDeg"}
          {"type": "rect", "x1", "y1", "x2", "y2"}   (opposite corners)
          {"type": "polygon", "points": [[x, y], ...]}  (auto-closed)

        Best practice: ONE closed profile per sketch, so extrude region
        selection is unambiguous."""
        feature = btm_sketch.sketch_feature(
            name, _plane_query(plane), _build_entities(entities, units)
        )
        return api.add_feature(
            get_client(), documentId, workspaceId, elementId, feature
        )

    @mcp.tool()
    def extrude(
        documentId: str,
        workspaceId: str,
        elementId: str,
        name: str,
        sketchFeatureId: str,
        operation: str = "NEW",
        endBound: str = "BLIND",
        depth: float | str = 0,
        units: str = "in",
        oppositeDirection: bool = False,
    ) -> dict[str, Any]:
        """Extrude ALL regions of a sketch (by its featureId — no entity ids
        needed). operation: NEW|ADD|REMOVE|INTERSECT (REMOVE subtracts from
        every solid in the studio). endBound: BLIND (needs depth) |
        THROUGH_ALL | SYMMETRIC. depth may be a number (in `units`) or an
        expression string like "1.53 in" or "#wall_thk"."""
        depth_expr = (
            length_expression(depth, units)
            if depth or isinstance(depth, str)
            else None
        )
        feature = btm_features.extrude(
            name,
            sketchFeatureId,
            operation,
            endBound,
            depth_expr,
            oppositeDirection,
        )
        return api.add_feature(
            get_client(), documentId, workspaceId, elementId, feature
        )
    @mcp.tool()
    def get_features(
        documentId: str,
        workspaceId: str,
        elementId: str,
        featureId: str = "",
        verbose: bool = False,
    ) -> list[dict[str, Any]]:
        """List features in a Part Studio with their regen status
        (featureStatus: OK | WARNING | ERROR). verbose=True includes the full
        feature JSON — use it to mirror features built manually in the
        OnShape UI."""
        return api.get_features(
            get_client(),
            documentId,
            workspaceId,
            elementId,
            featureId or None,
            verbose,
        )

    @mcp.tool()
    def add_feature(
        documentId: str,
        workspaceId: str,
        elementId: str,
        feature: dict[str, Any],
    ) -> dict[str, Any]:
        """RAW escape hatch: post one feature definition (BTM JSON) to a Part
        Studio. Accepts a bare feature dict (e.g. BTMSketch-151, BTMFeature-134)
        or a full BTFeatureDefinitionCall-1406 envelope. Sketch coordinates are
        in METERS. Returns {featureId, name, featureStatus}; featureStatus
        ERROR means the feature was added but failed to regenerate."""
        return api.add_feature(
            get_client(), documentId, workspaceId, elementId, feature
        )

    @mcp.tool()
    def update_feature(
        documentId: str,
        workspaceId: str,
        elementId: str,
        featureId: str,
        feature: dict[str, Any],
    ) -> dict[str, Any]:
        """Replace an existing feature's definition (full feature JSON,
        including its featureId)."""
        return api.update_feature(
            get_client(), documentId, workspaceId, elementId, featureId, feature
        )

    @mcp.tool()
    def delete_feature(
        documentId: str, workspaceId: str, elementId: str, featureId: str
    ) -> dict[str, Any]:
        """Delete a feature from a Part Studio."""
        return api.delete_feature(
            get_client(), documentId, workspaceId, elementId, featureId
        )
