"""FeatureScript helpers: response unwrapping (M1), find_entities codegen and
filtering (M3).

FeatureScript eval responses are deeply nested BTFSValue trees where every
node is {"btType": "...BTFSValueX", "message": {...fields...}}. unwrap_fs_value
collapses them into plain Python values:

- BTFSValueMap / map entries        -> dict
- BTFSValueArray                    -> list
- BTFSValueNumber/String/Boolean    -> number / str / bool
- BTFSValueWithUnits                -> number (OnShape internals are meters/
                                       radians; unit metadata is dropped)
- BTFSValueUndefined                -> None
- unknown node types                -> {"btType": ..., **unwrapped message}
"""

from __future__ import annotations

import math
from typing import Any

ENTITY_TYPES = ("VERTEX", "EDGE", "FACE", "BODY")

# Geometry info extraction per entity type. Lengths are divided by `meter` so
# everything comes back as plain numbers in meters; direction vectors are
# already unitless. `try silent` skips entities a given evaluator can't handle.
_GEOMETRY_PROBES = {
    "EDGE": """
        try silent {
            var c = evCurveDefinition(context, { "edge" : entities[i] });
            if (c is Circle) {
                info.geometryType = "CIRCLE";
                info.radius = c.radius / meter;
                info.origin = [c.coordSystem.origin[0] / meter, c.coordSystem.origin[1] / meter, c.coordSystem.origin[2] / meter];
                info.axis = [c.coordSystem.zAxis[0], c.coordSystem.zAxis[1], c.coordSystem.zAxis[2]];
            } else if (c is Line) {
                info.geometryType = "LINE";
                info.origin = [c.origin[0] / meter, c.origin[1] / meter, c.origin[2] / meter];
                info.axis = [c.direction[0], c.direction[1], c.direction[2]];
            } else {
                info.geometryType = "OTHER";
            }
        }
        try silent {
            var mid = evEdgeTangentLine(context, { "edge" : entities[i], "parameter" : 0.5 });
            info.midpoint = [mid.origin[0] / meter, mid.origin[1] / meter, mid.origin[2] / meter];
        }
""",
    "FACE": """
        try silent {
            var s = evSurfaceDefinition(context, { "face" : entities[i] });
            if (s is Plane) {
                info.geometryType = "PLANE";
                info.origin = [s.origin[0] / meter, s.origin[1] / meter, s.origin[2] / meter];
                info.axis = [s.normal[0], s.normal[1], s.normal[2]];
            } else if (s is Cylinder) {
                info.geometryType = "CYLINDER";
                info.radius = s.radius / meter;
                info.origin = [s.coordSystem.origin[0] / meter, s.coordSystem.origin[1] / meter, s.coordSystem.origin[2] / meter];
                info.axis = [s.coordSystem.zAxis[0], s.coordSystem.zAxis[1], s.coordSystem.zAxis[2]];
            } else if (s is Sphere) {
                info.geometryType = "SPHERE";
                info.radius = s.radius / meter;
                info.origin = [s.coordSystem.origin[0] / meter, s.coordSystem.origin[1] / meter, s.coordSystem.origin[2] / meter];
            } else if (s is Cone) {
                info.geometryType = "CONE";
                info.origin = [s.coordSystem.origin[0] / meter, s.coordSystem.origin[1] / meter, s.coordSystem.origin[2] / meter];
                info.axis = [s.coordSystem.zAxis[0], s.coordSystem.zAxis[1], s.coordSystem.zAxis[2]];
            } else {
                info.geometryType = "OTHER";
            }
        }
        try silent {
            var bb = evBox3d(context, { "topology" : entities[i] });
            info.center = [
                (bb.minCorner[0] + bb.maxCorner[0]) / 2 / meter,
                (bb.minCorner[1] + bb.maxCorner[1]) / 2 / meter,
                (bb.minCorner[2] + bb.maxCorner[2]) / 2 / meter];
        }
""",
    "VERTEX": """
        try silent {
            var p = evVertexPoint(context, { "vertex" : entities[i] });
            info.origin = [p[0] / meter, p[1] / meter, p[2] / meter];
        }
""",
    "BODY": "",
}


def build_find_entities_script(
    entity_type: str,
    created_by_feature_id: str | None = None,
    geometry_type: str | None = None,
) -> str:
    """FeatureScript that lists entities with transient ids + geometry info.
    All server-side filtering that costs nothing extra (creator, geometry
    kind); numeric filters run client-side in filter_entities."""
    entity_type = entity_type.upper()
    if entity_type not in ENTITY_TYPES:
        raise ValueError(f"entityType must be one of {ENTITY_TYPES}, got {entity_type!r}")
    if created_by_feature_id:
        base = f'qCreatedBy(makeId("{created_by_feature_id}"), EntityType.{entity_type})'
    else:
        base = f"qEverything(EntityType.{entity_type})"
    if geometry_type:
        base = f"qGeometry({base}, GeometryType.{geometry_type.upper()})"
    probe = _GEOMETRY_PROBES[entity_type]
    return (
        "function(context is Context, queries) {\n"
        f"    var entities = evaluateQuery(context, {base});\n"
        "    var ids = transientQueriesToStrings(entities);\n"
        "    var out = [];\n"
        "    for (var i = 0; i < size(entities); i += 1) {\n"
        '        var info = { "id" : ids[i] };\n'
        f"{probe}"
        "        out = append(out, info);\n"
        "    }\n"
        "    return out;\n"
        "}"
    )


def filter_entities(
    entities: list[dict[str, Any]],
    near_point_m: list[float] | None = None,
    radius_between_m: tuple[float, float] | None = None,
    max_results: int = 25,
) -> list[dict[str, Any]]:
    """Client-side numeric filtering of find_entities results (zero API cost).
    near_point sorts by distance from the entity's reference point."""
    results = entities
    if radius_between_m is not None:
        lo, hi = radius_between_m
        results = [
            e for e in results if e.get("radius") is not None and lo <= e["radius"] <= hi
        ]

    def ref_point(entity: dict[str, Any]) -> list[float] | None:
        return entity.get("midpoint") or entity.get("center") or entity.get("origin")

    if near_point_m is not None:
        def distance(entity: dict[str, Any]) -> float:
            point = ref_point(entity)
            if point is None:
                return math.inf
            return math.dist(point, near_point_m)

        results = sorted(results, key=distance)
    return results[:max_results]


def unwrap_fs_value(node: Any) -> Any:
    if node is None or isinstance(node, (str, int, float, bool)):
        return node
    if isinstance(node, list):
        return [unwrap_fs_value(item) for item in node]
    if not isinstance(node, dict):
        return node

    bt_type = node.get("btType", "")
    payload = node.get("message")
    if not isinstance(payload, dict):
        payload = {k: v for k, v in node.items() if k != "btType"}

    if "BTFSValueMap" in bt_type and "MapEntry" not in bt_type:
        entries = payload.get("value") or []
        result: dict[str, Any] = {}
        for entry in entries:
            entry_payload = entry.get("message", entry) if isinstance(entry, dict) else {}
            key = unwrap_fs_value(entry_payload.get("key"))
            value = unwrap_fs_value(entry_payload.get("value"))
            result[key if isinstance(key, str) else repr(key)] = value
        return result

    if "BTFSValueArray" in bt_type:
        return [unwrap_fs_value(item) for item in payload.get("value") or []]

    if "BTFSValueUndefined" in bt_type:
        return None

    if "BTFSValueWithUnits" in bt_type:
        return unwrap_fs_value(payload.get("value"))

    for marker in ("BTFSValueNumber", "BTFSValueString", "BTFSValueBoolean"):
        if marker in bt_type:
            return unwrap_fs_value(payload.get("value"))

    if "BTFSValue" in bt_type and "value" in payload:
        return unwrap_fs_value(payload["value"])

    # Unknown node (queries, transient ids, etc.): keep btType for context and
    # unwrap the fields we can.
    unwrapped = {key: unwrap_fs_value(value) for key, value in payload.items()}
    if bt_type:
        unwrapped["btType"] = bt_type
    return unwrapped
