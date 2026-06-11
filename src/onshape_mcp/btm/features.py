"""Solid feature builders (BTMFeature-134 dicts).

Dimension values are expression strings ('1 in', '#wall_thk') — conversion
from numbers happens in the tool layer via units.length_expression.

Parameter ids/enums verified against the OnShape standard library source
(std >= 2856, Jan 2026: revolve uses fullRevolve/RevolveBoundingType, not the
legacy revolveType enum) and onshape-public docs.
"""

from __future__ import annotations

from typing import Any

from . import params

OPERATIONS = ("NEW", "ADD", "REMOVE", "INTERSECT")
END_BOUNDS = ("BLIND", "THROUGH_ALL", "SYMMETRIC")
BOOLEAN_OPERATIONS = ("UNION", "SUBTRACTION", "INTERSECTION")


def _feature(name: str, feature_type: str, parameters: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "btType": "BTMFeature-134",
        "featureType": feature_type,
        "name": name,
        "parameters": parameters,
    }


def _check_operation(operation: str) -> str:
    operation = operation.upper()
    if operation not in OPERATIONS:
        raise ValueError(f"operation must be one of {OPERATIONS}, got {operation!r}")
    return operation


def extrude(
    name: str,
    sketch_feature_id: str,
    operation: str = "NEW",
    end_bound: str = "BLIND",
    depth_expression: str | None = None,
    opposite_direction: bool = False,
) -> dict[str, Any]:
    operation = operation.upper()
    end_bound = end_bound.upper()
    if operation not in OPERATIONS:
        raise ValueError(f"operation must be one of {OPERATIONS}, got {operation!r}")
    if end_bound not in END_BOUNDS:
        raise ValueError(f"endBound must be one of {END_BOUNDS}, got {end_bound!r}")
    if end_bound in ("BLIND", "SYMMETRIC") and not depth_expression:
        raise ValueError(f"{end_bound} extrude requires a depth")

    parameters: list[dict[str, Any]] = [
        params.enum("bodyType", "SOLID", "ExtendedToolBodyType"),
        params.enum("operationType", operation, "NewBodyOperationType"),
        params.query_list(
            "entities", [params.sketch_region_query(sketch_feature_id)]
        ),
        params.enum("endBound", end_bound, "BoundingType"),
    ]
    if depth_expression and end_bound != "THROUGH_ALL":
        parameters.append(params.quantity("depth", depth_expression))
    if opposite_direction:
        parameters.append(params.boolean("oppositeDirection", True))

    return _feature(name, "extrude", parameters)


def revolve(
    name: str,
    sketch_feature_id: str,
    axis_query: dict[str, Any],
    operation: str = "NEW",
    angle_expression: str | None = None,
    opposite_direction: bool = False,
) -> dict[str, Any]:
    """Revolve all regions of a sketch about an axis (a LINE/CIRCLE/ARC edge
    or CYLINDER face query). angle_expression None -> full 360 revolve."""
    operation = _check_operation(operation)
    parameters = [
        params.enum("bodyType", "SOLID", "ExtendedToolBodyType"),
        params.enum("operationType", operation, "NewBodyOperationType"),
        params.query_list("entities", [params.sketch_region_query(sketch_feature_id)]),
        params.query_list("axis", [axis_query]),
    ]
    if angle_expression is None:
        parameters.append(params.boolean("fullRevolve", True))
    else:
        parameters.append(params.boolean("fullRevolve", False))
        parameters.append(params.enum("endBound", "BLIND", "RevolveBoundingType"))
        parameters.append(params.quantity("angle", angle_expression))
        if opposite_direction:
            parameters.append(params.boolean("oppositeDirection", True))
    if operation != "NEW":
        parameters.append(params.boolean("defaultScope", True))
    return _feature(name, "revolve", parameters)


def fillet(
    name: str,
    entity_ids: list[str],
    radius_expression: str,
    tangent_propagation: bool = True,
) -> dict[str, Any]:
    """Constant-radius edge fillet. entity_ids are transient edge/face ids
    (faces fillet all their adjacent edges). tangentPropagation defaults
    FALSE on the API (unlike the UI checkbox) — sent explicitly."""
    return _feature(name, "fillet", [
        params.query_list("entities", [params.deterministic_query(entity_ids)]),
        params.quantity("radius", radius_expression),
        params.boolean("tangentPropagation", tangent_propagation),
    ])


def chamfer(
    name: str,
    entity_ids: list[str],
    width_expression: str,
    tangent_propagation: bool = True,
) -> dict[str, Any]:
    """Equal-offsets chamfer. chamferType is REQUIRED by the API (no default)."""
    return _feature(name, "chamfer", [
        params.query_list("entities", [params.deterministic_query(entity_ids)]),
        params.enum("chamferType", "EQUAL_OFFSETS", "ChamferType"),
        params.quantity("width", width_expression),
        params.boolean("tangentPropagation", tangent_propagation),
    ])


def circular_pattern(
    name: str,
    entity_queries: list[dict[str, Any]],
    axis_query: dict[str, Any],
    instance_count: int,
    angle_expression: str = "360 deg",
    equal_space: bool = True,
    operation: str = "NEW",
) -> dict[str, Any]:
    """PART pattern around an axis. Note: parameterId is 'equalSpace' (not
    'equalSpacing') and its API default is false — sent explicitly."""
    parameters = [
        params.enum("patternType", "PART", "PatternType"),
        params.query_list("entities", entity_queries),
        params.query_list("axis", [axis_query]),
        params.quantity("angle", angle_expression),
        params.integer_quantity("instanceCount", instance_count),
        params.boolean("equalSpace", equal_space),
        params.enum("operationType", _check_operation(operation), "NewBodyOperationType"),
    ]
    if operation.upper() != "NEW":
        parameters.append(params.boolean("defaultScope", True))
    return _feature(name, "circularPattern", parameters)


def feature_circular_pattern(
    name: str,
    feature_ids: list[str],
    axis_query: dict[str, Any],
    instance_count: int,
    angle_expression: str = "360 deg",
    equal_space: bool = True,
) -> dict[str, Any]:
    """FEATURE pattern (re-applies features like extrude-remove holes)."""
    return _feature(name, "circularPattern", [
        params.enum("patternType", "FEATURE", "PatternType"),
        params.feature_list("instanceFunction", feature_ids),
        params.query_list("axis", [axis_query]),
        params.quantity("angle", angle_expression),
        params.integer_quantity("instanceCount", instance_count),
        params.boolean("equalSpace", equal_space),
    ])


def linear_pattern(
    name: str,
    entity_queries: list[dict[str, Any]],
    direction_query: dict[str, Any],
    instance_count: int,
    distance_expression: str,
    operation: str = "NEW",
) -> dict[str, Any]:
    """PART pattern along a direction (linear edge or planar face normal).
    instance_count INCLUDES the seed."""
    parameters = [
        params.enum("patternType", "PART", "PatternType"),
        params.query_list("entities", entity_queries),
        params.query_list("directionOne", [direction_query]),
        params.quantity("distance", distance_expression),
        params.integer_quantity("instanceCount", instance_count),
        params.enum("operationType", _check_operation(operation), "NewBodyOperationType"),
    ]
    if operation.upper() != "NEW":
        parameters.append(params.boolean("defaultScope", True))
    return _feature(name, "linearPattern", parameters)


def feature_linear_pattern(
    name: str,
    feature_ids: list[str],
    direction_query: dict[str, Any],
    instance_count: int,
    distance_expression: str,
) -> dict[str, Any]:
    return _feature(name, "linearPattern", [
        params.enum("patternType", "FEATURE", "PatternType"),
        params.feature_list("instanceFunction", feature_ids),
        params.query_list("directionOne", [direction_query]),
        params.quantity("distance", distance_expression),
        params.integer_quantity("instanceCount", instance_count),
    ])


def boolean_bodies(
    name: str,
    operation: str,
    tool_queries: list[dict[str, Any]],
    target_queries: list[dict[str, Any]] | None = None,
    keep_tools: bool = False,
) -> dict[str, Any]:
    """Boolean of solid bodies. targets are required (and only valid) for
    SUBTRACTION; UNION/INTERSECTION take all bodies via tools."""
    operation = operation.upper()
    if operation not in BOOLEAN_OPERATIONS:
        raise ValueError(
            f"operation must be one of {BOOLEAN_OPERATIONS}, got {operation!r}"
        )
    if operation == "SUBTRACTION" and not target_queries:
        raise ValueError("SUBTRACTION requires target bodies")
    parameters = [
        params.enum("operationType", operation, "BooleanOperationType"),
        params.query_list("tools", tool_queries),
    ]
    if operation == "SUBTRACTION":
        parameters.append(params.query_list("targets", target_queries or []))
    if keep_tools:
        parameters.append(params.boolean("keepTools", True))
    return _feature(name, "booleanBodies", parameters)


def offset_plane(
    name: str,
    base_plane_query: dict[str, Any],
    offset_expression: str,
    opposite_direction: bool = False,
) -> dict[str, Any]:
    parameters = [
        params.query_list("entities", [base_plane_query]),
        params.enum("cplaneType", "OFFSET", "CPlaneType"),
        params.quantity("offset", offset_expression),
    ]
    if opposite_direction:
        parameters.append(params.boolean("oppositeDirection", True))
    return _feature(name, "cPlane", parameters)


VARIABLE_VALUE_PARAM = {
    "LENGTH": "lengthValue",
    "ANGLE": "angleValue",
    "NUMBER": "numberValue",
    "ANY": "anyValue",
}


def assign_variable(
    variable_name: str, variable_type: str, expression: str
) -> dict[str, Any]:
    """assignVariable feature: defines #<variable_name> for later features
    in THIS part studio. variable_type: LENGTH | ANGLE | NUMBER | ANY."""
    variable_type = variable_type.upper()
    if variable_type not in VARIABLE_VALUE_PARAM:
        raise ValueError(
            f"variable_type must be one of {sorted(VARIABLE_VALUE_PARAM)}, "
            f"got {variable_type!r}"
        )
    return _feature(f"#{variable_name}", "assignVariable", [
        params.string("name", variable_name),
        params.enum("variableType", variable_type, "VariableType"),
        params.quantity(VARIABLE_VALUE_PARAM[variable_type], expression),
    ])
