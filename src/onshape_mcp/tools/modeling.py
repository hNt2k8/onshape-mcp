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
from ..units import angle_expression, length_expression, to_meters


def _plane_query(plane: dict[str, Any]) -> dict[str, Any]:
    if "default" in plane:
        return btm_params.default_plane_query(plane["default"])
    if "faceId" in plane:
        return btm_params.deterministic_query([plane["faceId"]])
    raise ValueError(
        'plane must be {"default": "TOP|FRONT|RIGHT"} or {"faceId": "<transient id>"}'
    )


def _ref_query(ref: str | dict[str, Any]) -> dict[str, Any]:
    """Axis/direction reference: a transient entity id string, or
    {"default": "TOP|FRONT|RIGHT"} for a default plane (direction = normal)."""
    if isinstance(ref, str):
        return btm_params.deterministic_query([ref])
    if isinstance(ref, dict) and "default" in ref:
        return btm_params.default_plane_query(ref["default"])
    raise ValueError(
        'reference must be a transient id string or {"default": "TOP|FRONT|RIGHT"}'
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
    def revolve(
        documentId: str,
        workspaceId: str,
        elementId: str,
        name: str,
        sketchFeatureId: str,
        axisId: str,
        operation: str = "NEW",
        angleDeg: float | str = 0,
        oppositeDirection: bool = False,
    ) -> dict[str, Any]:
        """Revolve ALL regions of a sketch about an axis. axisId is a
        transient id (from find_entities) of a LINE edge, CIRCLE/ARC edge,
        or CYLINDER face. angleDeg 0 (default) = full 360; otherwise degrees
        or an expression like "90 deg". operation: NEW|ADD|REMOVE|INTERSECT."""
        angle = None if not angleDeg else angle_expression(angleDeg)
        feature = btm_features.revolve(
            name,
            sketchFeatureId,
            _ref_query(axisId),
            operation,
            angle,
            oppositeDirection,
        )
        return api.add_feature(
            get_client(), documentId, workspaceId, elementId, feature
        )

    @mcp.tool()
    def fillet_or_chamfer(
        documentId: str,
        workspaceId: str,
        elementId: str,
        kind: str,
        entityIds: list[str],
        radiusOrWidth: float | str,
        units: str = "in",
        name: str = "",
    ) -> dict[str, Any]:
        """Fillet (constant radius) or chamfer (equal offsets) edges/faces.
        kind: "fillet" | "chamfer". entityIds are TRANSIENT ids from
        find_entities — get them fresh, right before this call. Faces apply
        to all their adjacent edges."""
        value = length_expression(radiusOrWidth, units)
        if kind == "fillet":
            feature = btm_features.fillet(name or "Fillet", entityIds, value)
        elif kind == "chamfer":
            feature = btm_features.chamfer(name or "Chamfer", entityIds, value)
        else:
            raise ValueError(f'kind must be "fillet" or "chamfer", got {kind!r}')
        return api.add_feature(
            get_client(), documentId, workspaceId, elementId, feature
        )

    @mcp.tool()
    def pattern(
        documentId: str,
        workspaceId: str,
        elementId: str,
        kind: str,
        entityType: str,
        seedFeatureIds: list[str],
        axisOrDirectionId: str | dict[str, Any],
        count: int,
        spacingOrAngle: float | str = 0,
        units: str = "in",
        operation: str = "NEW",
        name: str = "",
    ) -> dict[str, Any]:
        """Linear or circular pattern. kind: "linear" | "circular".
        entityType: "part" (patterns the BODIES the seed features created —
        stable featureId references) or "feature" (re-applies the features,
        e.g. an extrude-REMOVE hole). seedFeatureIds: featureIds of the seeds.
        axisOrDirectionId: transient id (circular: LINE edge or CYLINDER face;
        linear: LINE edge or planar face) or {"default": "TOP|FRONT|RIGHT"}.
        count INCLUDES the seed. spacingOrAngle: linear -> distance in `units`;
        circular -> total angle in degrees (0 = full 360, equally spaced)."""
        axis_query = _ref_query(axisOrDirectionId)
        if kind == "circular":
            angle = angle_expression(spacingOrAngle or 360)
            if entityType == "part":
                feature = btm_features.circular_pattern(
                    name or "Circular pattern",
                    [btm_params.bodies_created_by_query(fid) for fid in seedFeatureIds],
                    axis_query,
                    count,
                    angle,
                    operation=operation,
                )
            elif entityType == "feature":
                feature = btm_features.feature_circular_pattern(
                    name or "Circular pattern", seedFeatureIds, axis_query, count, angle
                )
            else:
                raise ValueError(f'entityType must be "part" or "feature", got {entityType!r}')
        elif kind == "linear":
            if not spacingOrAngle:
                raise ValueError("linear pattern requires spacingOrAngle (distance)")
            distance = length_expression(spacingOrAngle, units)
            if entityType == "part":
                feature = btm_features.linear_pattern(
                    name or "Linear pattern",
                    [btm_params.bodies_created_by_query(fid) for fid in seedFeatureIds],
                    axis_query,
                    count,
                    distance,
                    operation,
                )
            elif entityType == "feature":
                feature = btm_features.feature_linear_pattern(
                    name or "Linear pattern", seedFeatureIds, axis_query, count, distance
                )
            else:
                raise ValueError(f'entityType must be "part" or "feature", got {entityType!r}')
        else:
            raise ValueError(f'kind must be "linear" or "circular", got {kind!r}')
        return api.add_feature(
            get_client(), documentId, workspaceId, elementId, feature
        )

    @mcp.tool()
    def boolean_parts(
        documentId: str,
        workspaceId: str,
        elementId: str,
        operation: str,
        toolFeatureIds: list[str],
        targetFeatureIds: list[str] | None = None,
        keepTools: bool = False,
        name: str = "",
    ) -> dict[str, Any]:
        """Boolean solid bodies. operation: UNION | SUBTRACTION | INTERSECTION.
        Bodies are referenced by the featureIds that created them (stable).
        targets only for SUBTRACTION (tools are subtracted from targets)."""
        feature = btm_features.boolean_bodies(
            name or "Boolean",
            operation,
            [btm_params.bodies_created_by_query(fid) for fid in toolFeatureIds],
            [btm_params.bodies_created_by_query(fid) for fid in (targetFeatureIds or [])],
            keepTools,
        )
        return api.add_feature(
            get_client(), documentId, workspaceId, elementId, feature
        )

    @mcp.tool()
    def create_offset_plane(
        documentId: str,
        workspaceId: str,
        elementId: str,
        basePlane: dict[str, Any],
        distance: float | str,
        units: str = "in",
        oppositeDirection: bool = False,
        name: str = "",
    ) -> dict[str, Any]:
        """Construction plane offset from a base plane. basePlane:
        {"default": "TOP|FRONT|RIGHT"} or {"faceId": "<transient id>"}.
        Use find_entities afterwards to get the new plane's faceId for
        sketching on it."""
        feature = btm_features.offset_plane(
            name or "Offset plane",
            _plane_query(basePlane),
            length_expression(distance, units),
            oppositeDirection,
        )
        return api.add_feature(
            get_client(), documentId, workspaceId, elementId, feature
        )

    @mcp.tool()
    def set_variable(
        documentId: str,
        workspaceId: str,
        elementId: str,
        variableName: str,
        expression: str,
        variableType: str = "LENGTH",
    ) -> dict[str, Any]:
        """Define #<variableName> usable in later feature expressions in this
        Part Studio (e.g. expression "0.25 in", then depth "#wall_thk * 2").
        variableType: LENGTH | ANGLE | NUMBER | ANY."""
        feature = btm_features.assign_variable(variableName, variableType, expression)
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
