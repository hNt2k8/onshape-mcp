"""Sketch entity builders. ALL coordinates here are in METERS (OnShape
native); unit conversion happens in the tool layer before calling these.

Entity dict shapes verified against the official feature-access docs and the
M1 live smoke test (BTMSketchCurve-4 circle -> featureStatus OK).
"""

from __future__ import annotations

import math
from typing import Any

from . import params


def line(
    x1: float, y1: float, x2: float, y2: float, entity_id: str
) -> dict[str, Any]:
    length = math.hypot(x2 - x1, y2 - y1)
    if length == 0:
        raise ValueError(f"zero-length line at ({x1}, {y1})")
    return {
        "btType": "BTMSketchCurveSegment-155",
        "entityId": entity_id,
        "startPointId": f"{entity_id}.start",
        "endPointId": f"{entity_id}.end",
        "startParam": 0.0,
        "endParam": length,
        "geometry": {
            "btType": "BTCurveGeometryLine-117",
            "pntX": x1,
            "pntY": y1,
            "dirX": (x2 - x1) / length,
            "dirY": (y2 - y1) / length,
        },
    }


def circle(
    x_center: float, y_center: float, radius: float, entity_id: str
) -> dict[str, Any]:
    if radius <= 0:
        raise ValueError(f"circle radius must be positive, got {radius}")
    return {
        "btType": "BTMSketchCurve-4",
        "entityId": entity_id,
        "centerId": f"{entity_id}.center",
        "geometry": {
            "btType": "BTCurveGeometryCircle-115",
            "radius": radius,
            "xCenter": x_center,
            "yCenter": y_center,
            "xDir": 1,
            "yDir": 0,
            "clockwise": False,
        },
    }


def arc(
    x_center: float,
    y_center: float,
    radius: float,
    start_angle_rad: float,
    end_angle_rad: float,
    entity_id: str,
) -> dict[str, Any]:
    """Circular arc; start/end params are angles in RADIANS measured from +X."""
    if radius <= 0:
        raise ValueError(f"arc radius must be positive, got {radius}")
    return {
        "btType": "BTMSketchCurveSegment-155",
        "entityId": entity_id,
        "startPointId": f"{entity_id}.start",
        "endPointId": f"{entity_id}.end",
        "startParam": start_angle_rad,
        "endParam": end_angle_rad,
        "geometry": {
            "btType": "BTCurveGeometryCircle-115",
            "radius": radius,
            "xCenter": x_center,
            "yCenter": y_center,
            "xDir": 1,
            "yDir": 0,
            "clockwise": False,
        },
    }


def rectangle(
    x1: float, y1: float, x2: float, y2: float, id_prefix: str
) -> list[dict[str, Any]]:
    """Axis-aligned rectangle with opposite corners (x1,y1)/(x2,y2) -> 4 lines."""
    corners = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
    return polygon(corners, id_prefix)


def polygon(
    points: list[tuple[float, float]], id_prefix: str
) -> list[dict[str, Any]]:
    """Closed polygon through the given vertices (auto-closes back to start)."""
    if len(points) < 3:
        raise ValueError("polygon needs at least 3 points")
    entities = []
    for i, (px, py) in enumerate(points):
        qx, qy = points[(i + 1) % len(points)]
        entities.append(line(px, py, qx, qy, f"{id_prefix}.{i}"))
    return entities


def sketch_feature(
    name: str,
    plane_query: dict[str, Any],
    entities: list[dict[str, Any]],
) -> dict[str, Any]:
    """BTMSketch-151 envelope. Unconstrained closed sketches extrude fine."""
    return {
        "btType": "BTMSketch-151",
        "featureType": "newSketch",
        "name": name,
        "parameters": [params.query_list("sketchPlane", [plane_query])],
        "entities": entities,
        "constraints": [],
    }
