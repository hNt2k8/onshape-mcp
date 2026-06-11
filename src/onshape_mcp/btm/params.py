"""BTMParameter* helpers — the building blocks of feature JSON."""

from __future__ import annotations

from typing import Any


def quantity(parameter_id: str, expression: str) -> dict[str, Any]:
    return {
        "btType": "BTMParameterQuantity-147",
        "parameterId": parameter_id,
        "expression": expression,
    }


def integer_quantity(parameter_id: str, value: int) -> dict[str, Any]:
    return {
        "btType": "BTMParameterQuantity-147",
        "parameterId": parameter_id,
        "isInteger": True,
        "expression": str(int(value)),
    }


def string(parameter_id: str, value: str) -> dict[str, Any]:
    return {
        "btType": "BTMParameterString-149",
        "parameterId": parameter_id,
        "value": value,
    }


def feature_list(parameter_id: str, feature_ids: list[str]) -> dict[str, Any]:
    """FeatureList parameter (FEATURE patterns reference features this way)."""
    return {
        "btType": "BTMParameterFeatureList-1749",
        "parameterId": parameter_id,
        "featureIds": feature_ids,
    }


def enum(parameter_id: str, value: str, enum_name: str) -> dict[str, Any]:
    return {
        "btType": "BTMParameterEnum-145",
        "parameterId": parameter_id,
        "value": value,
        "enumName": enum_name,
    }


def boolean(parameter_id: str, value: bool) -> dict[str, Any]:
    return {
        "btType": "BTMParameterBoolean-144",
        "parameterId": parameter_id,
        "value": value,
    }


def query_list(parameter_id: str, queries: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "btType": "BTMParameterQueryList-148",
        "parameterId": parameter_id,
        "queries": queries,
    }


def query_string(query: str) -> dict[str, Any]:
    """Query expressed as a FeatureScript query string — zero API calls.
    e.g. 'query=qCreatedBy(makeId("Top"), EntityType.FACE);'"""
    return {"btType": "BTMIndividualQuery-138", "queryString": query}


def deterministic_query(ids: list[str]) -> dict[str, Any]:
    """Query by transient/deterministic ids (from find_entities / FS eval).
    Transient ids are invalidated by ANY document mutation — never cache."""
    return {"btType": "BTMIndividualQuery-138", "deterministicIds": ids}


def sketch_region_query(sketch_feature_id: str) -> dict[str, Any]:
    """All regions of a sketch, by featureId — no entity ids needed."""
    return {
        "btType": "BTMIndividualSketchRegionQuery-140",
        "featureId": sketch_feature_id,
    }


def default_plane_query(name: str) -> dict[str, Any]:
    """Default plane (Top/Front/Right) via queryString — zero API calls."""
    title = name.capitalize()  # TOP -> Top
    if title not in ("Top", "Front", "Right"):
        raise ValueError(f"default plane must be TOP, FRONT, or RIGHT, got {name!r}")
    return query_string(f'query=qCreatedBy(makeId("{title}"), EntityType.FACE);')


def bodies_created_by_query(feature_id: str) -> dict[str, Any]:
    """All BODIES a feature created — referenced by featureId, so it stays
    valid across later mutations (unlike transient ids)."""
    return query_string(
        f'query=qCreatedBy(makeId("{feature_id}"), EntityType.BODY);'
    )
