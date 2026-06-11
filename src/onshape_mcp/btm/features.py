"""Solid feature builders (BTMFeature-134 dicts). M2: extrude. M3 adds
revolve, fillet/chamfer, patterns, boolean, planes, variables.

Dimension values are expression strings ('1 in', '#wall_thk') — conversion
from numbers happens in the tool layer via units.length_expression.
"""

from __future__ import annotations

from typing import Any

from . import params

OPERATIONS = ("NEW", "ADD", "REMOVE", "INTERSECT")
END_BOUNDS = ("BLIND", "THROUGH_ALL", "SYMMETRIC")


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

    return {
        "btType": "BTMFeature-134",
        "featureType": "extrude",
        "name": name,
        "parameters": parameters,
    }
