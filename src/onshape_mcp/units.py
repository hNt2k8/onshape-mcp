"""Unit handling. OnShape's internal geometry is ALWAYS meters (and radians);
user-facing tool parameters default to inches."""

from __future__ import annotations

UNIT_TO_METERS = {"in": 0.0254, "mm": 0.001, "m": 1.0}

# OnShape dimension-expression / export-API unit names.
UNIT_LABEL = {"in": "in", "mm": "mm", "m": "m"}
EXPORT_UNIT = {"in": "inch", "mm": "millimeter", "m": "meter"}


class UnitError(ValueError):
    pass


def check_units(units: str) -> str:
    if units not in UNIT_TO_METERS:
        raise UnitError(f"units must be one of {sorted(UNIT_TO_METERS)}, got {units!r}")
    return units


def to_meters(value: float, units: str) -> float:
    return value * UNIT_TO_METERS[check_units(units)]


def length_expression(value: float | str, units: str) -> str:
    """Numbers become '<value> <unit>' dimension expressions; strings (already
    expressions like '1.53 in' or '#wall_thk') pass through untouched."""
    if isinstance(value, str):
        return value
    return f"{value} {UNIT_LABEL[check_units(units)]}"


def angle_expression(value: float | str) -> str:
    """Numbers are degrees; expression strings pass through untouched."""
    if isinstance(value, str):
        return value
    return f"{value} deg"
