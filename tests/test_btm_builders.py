"""Offline snapshot tests for BTM JSON builders.

The smoke-circle entity shape was accepted live (M1 gate, featureStatus OK);
these tests pin the builders to shapes known to work.
"""

import math

import pytest

from onshape_mcp.btm import features, params, sketch
from onshape_mcp.units import length_expression, to_meters


def test_circle_matches_live_accepted_smoke_circle():
    entity = sketch.circle(0.0, 0.0, 0.0254, "c1")
    assert entity == {
        "btType": "BTMSketchCurve-4",
        "entityId": "c1",
        "centerId": "c1.center",
        "geometry": {
            "btType": "BTCurveGeometryCircle-115",
            "radius": 0.0254,
            "xCenter": 0.0,
            "yCenter": 0.0,
            "xDir": 1,
            "yDir": 0,
            "clockwise": False,
        },
    }


def test_sketch_feature_envelope_matches_live_accepted_shape():
    feature = sketch.sketch_feature(
        "Smoke Circle",
        params.default_plane_query("TOP"),
        [sketch.circle(0.0, 0.0, 0.0254, "c1")],
    )
    assert feature["btType"] == "BTMSketch-151"
    assert feature["featureType"] == "newSketch"
    assert feature["constraints"] == []
    plane_param = feature["parameters"][0]
    assert plane_param["btType"] == "BTMParameterQueryList-148"
    assert plane_param["parameterId"] == "sketchPlane"
    assert plane_param["queries"] == [
        {
            "btType": "BTMIndividualQuery-138",
            "queryString": 'query=qCreatedBy(makeId("Top"), EntityType.FACE);',
        }
    ]


def test_default_plane_query_rejects_garbage():
    with pytest.raises(ValueError):
        params.default_plane_query("UPWARDS")


def test_line_unit_direction_and_length_param():
    entity = sketch.line(0.0, 0.0, 3.0, 4.0, "e1")
    geometry = entity["geometry"]
    assert math.isclose(geometry["dirX"], 0.6)
    assert math.isclose(geometry["dirY"], 0.8)
    assert entity["startParam"] == 0.0
    assert math.isclose(entity["endParam"], 5.0)
    assert entity["startPointId"] == "e1.start"
    assert entity["endPointId"] == "e1.end"


def test_rectangle_is_closed_loop_of_four_lines():
    lines = sketch.rectangle(0.0, 0.0, 0.0254, 0.0254, "r")
    assert len(lines) == 4
    # End of each segment is the start of the next (closed loop).
    for i, entity in enumerate(lines):
        geometry = entity["geometry"]
        end_x = geometry["pntX"] + geometry["dirX"] * entity["endParam"]
        end_y = geometry["pntY"] + geometry["dirY"] * entity["endParam"]
        next_geometry = lines[(i + 1) % 4]["geometry"]
        assert math.isclose(end_x, next_geometry["pntX"], abs_tol=1e-12)
        assert math.isclose(end_y, next_geometry["pntY"], abs_tol=1e-12)


def test_polygon_requires_three_points():
    with pytest.raises(ValueError):
        sketch.polygon([(0, 0), (1, 1)], "p")


def test_extrude_blind_snapshot():
    feature = features.extrude("Boss", "FsketchId", "NEW", "BLIND", "1 in")
    assert feature == {
        "btType": "BTMFeature-134",
        "featureType": "extrude",
        "name": "Boss",
        "parameters": [
            {
                "btType": "BTMParameterEnum-145",
                "parameterId": "bodyType",
                "value": "SOLID",
                "enumName": "ExtendedToolBodyType",
            },
            {
                "btType": "BTMParameterEnum-145",
                "parameterId": "operationType",
                "value": "NEW",
                "enumName": "NewBodyOperationType",
            },
            {
                "btType": "BTMParameterQueryList-148",
                "parameterId": "entities",
                "queries": [
                    {
                        "btType": "BTMIndividualSketchRegionQuery-140",
                        "featureId": "FsketchId",
                    }
                ],
            },
            {
                "btType": "BTMParameterEnum-145",
                "parameterId": "endBound",
                "value": "BLIND",
                "enumName": "BoundingType",
            },
            {
                "btType": "BTMParameterQuantity-147",
                "parameterId": "depth",
                "expression": "1 in",
            },
        ],
    }


def test_extrude_through_all_omits_depth():
    feature = features.extrude("Cut", "Fs", "REMOVE", "THROUGH_ALL")
    ids = [p["parameterId"] for p in feature["parameters"]]
    assert "depth" not in ids


def test_extrude_blind_requires_depth():
    with pytest.raises(ValueError, match="depth"):
        features.extrude("Boss", "Fs", "NEW", "BLIND")


def test_extrude_opposite_direction_flag():
    feature = features.extrude("Boss", "Fs", "NEW", "BLIND", "1 in", True)
    flags = {p["parameterId"]: p for p in feature["parameters"]}
    assert flags["oppositeDirection"]["value"] is True


def test_units_helpers():
    assert to_meters(1.0, "in") == 0.0254
    assert to_meters(1.0, "mm") == 0.001
    assert length_expression(1.53, "in") == "1.53 in"
    assert length_expression("#wall_thk", "in") == "#wall_thk"
    with pytest.raises(ValueError):
        to_meters(1.0, "furlong")


def _param_map(feature):
    return {p["parameterId"]: p for p in feature["parameters"]}


def test_revolve_full_uses_fullrevolve_not_legacy_enum():
    feature = features.revolve(
        "Rev", "Fsketch", params.deterministic_query(["JXX"])
    )
    assert feature["featureType"] == "revolve"
    p = _param_map(feature)
    # std >= 2856 spec: boolean fullRevolve, no legacy revolveType enum
    assert p["fullRevolve"]["value"] is True
    assert "revolveType" not in p
    assert "angle" not in p
    assert p["axis"]["queries"] == [
        {"btType": "BTMIndividualQuery-138", "deterministicIds": ["JXX"]}
    ]


def test_revolve_partial_angle():
    feature = features.revolve(
        "Rev", "Fs", params.deterministic_query(["JXX"]), "ADD", "90 deg"
    )
    p = _param_map(feature)
    assert p["fullRevolve"]["value"] is False
    assert p["angle"]["expression"] == "90 deg"
    assert p["endBound"] == {
        "btType": "BTMParameterEnum-145",
        "parameterId": "endBound",
        "value": "BLIND",
        "enumName": "RevolveBoundingType",
    }
    assert p["defaultScope"]["value"] is True  # non-NEW op merges with all


def test_fillet_snapshot():
    feature = features.fillet("Fillet", ["JAB", "JCD"], "0.1 in")
    assert feature["featureType"] == "fillet"
    p = _param_map(feature)
    assert p["entities"]["queries"][0]["deterministicIds"] == ["JAB", "JCD"]
    assert p["radius"]["expression"] == "0.1 in"
    # API default is false (unlike the UI checkbox) -> always sent explicitly
    assert p["tangentPropagation"]["value"] is True


def test_chamfer_requires_type_param():
    feature = features.chamfer("Chamfer", ["JAB"], "0.05 in")
    p = _param_map(feature)
    assert p["chamferType"]["value"] == "EQUAL_OFFSETS"
    assert p["chamferType"]["enumName"] == "ChamferType"
    assert p["width"]["expression"] == "0.05 in"


def test_circular_pattern_part_snapshot():
    feature = features.circular_pattern(
        "Pat",
        [params.bodies_created_by_query("Fseed")],
        params.deterministic_query(["JAXIS"]),
        4,
    )
    assert feature["featureType"] == "circularPattern"
    p = _param_map(feature)
    assert p["patternType"]["value"] == "PART"
    assert p["instanceCount"] == {
        "btType": "BTMParameterQuantity-147",
        "parameterId": "instanceCount",
        "isInteger": True,
        "expression": "4",
    }
    assert p["angle"]["expression"] == "360 deg"
    # exact id is equalSpace, NOT equalSpacing; API default false
    assert p["equalSpace"]["value"] is True
    assert 'qCreatedBy(makeId("Fseed"), EntityType.BODY)' in (
        p["entities"]["queries"][0]["queryString"]
    )


def test_feature_pattern_uses_feature_list():
    feature = features.feature_circular_pattern(
        "Pat", ["Fhole"], params.deterministic_query(["JAXIS"]), 4
    )
    p = _param_map(feature)
    assert p["patternType"]["value"] == "FEATURE"
    assert p["instanceFunction"] == {
        "btType": "BTMParameterFeatureList-1749",
        "parameterId": "instanceFunction",
        "featureIds": ["Fhole"],
    }


def test_linear_pattern_snapshot():
    feature = features.linear_pattern(
        "Pat",
        [params.bodies_created_by_query("Fseed")],
        params.default_plane_query("RIGHT"),
        3,
        "0.5 in",
    )
    p = _param_map(feature)
    assert p["directionOne"]["queries"][0]["queryString"].startswith(
        'query=qCreatedBy(makeId("Right")'
    )
    assert p["distance"]["expression"] == "0.5 in"
    assert p["instanceCount"]["expression"] == "3"


def test_boolean_subtraction_requires_targets():
    with pytest.raises(ValueError, match="target"):
        features.boolean_bodies("B", "SUBTRACTION", [params.bodies_created_by_query("F1")])
    feature = features.boolean_bodies(
        "B",
        "SUBTRACTION",
        [params.bodies_created_by_query("Ftool")],
        [params.bodies_created_by_query("Fbase")],
    )
    p = _param_map(feature)
    assert p["operationType"]["enumName"] == "BooleanOperationType"
    assert "targets" in p


def test_boolean_union_omits_targets():
    feature = features.boolean_bodies(
        "B", "UNION",
        [params.bodies_created_by_query("F1"), params.bodies_created_by_query("F2")],
    )
    assert "targets" not in _param_map(feature)


def test_offset_plane_snapshot():
    feature = features.offset_plane(
        "Plane", params.default_plane_query("TOP"), "0.236 in"
    )
    assert feature["featureType"] == "cPlane"
    p = _param_map(feature)
    assert p["cplaneType"]["value"] == "OFFSET"
    assert p["cplaneType"]["enumName"] == "CPlaneType"
    assert p["offset"]["expression"] == "0.236 in"


def test_assign_variable_snapshot():
    feature = features.assign_variable("wall_thk", "LENGTH", "0.25 in")
    assert feature["featureType"] == "assignVariable"
    assert feature["name"] == "#wall_thk"
    p = _param_map(feature)
    assert p["name"] == {
        "btType": "BTMParameterString-149",
        "parameterId": "name",
        "value": "wall_thk",
    }
    assert p["variableType"]["enumName"] == "VariableType"
    assert p["lengthValue"]["expression"] == "0.25 in"
    with pytest.raises(ValueError):
        features.assign_variable("x", "TEMPERATURE", "5")


def test_find_entities_script_contains_filters():
    from onshape_mcp.queries import build_find_entities_script, filter_entities

    script = build_find_entities_script("EDGE", "FsketchId", "CIRCLE")
    assert 'qCreatedBy(makeId("FsketchId"), EntityType.EDGE)' in script
    assert "GeometryType.CIRCLE" in script
    assert "evCurveDefinition" in script

    with pytest.raises(ValueError):
        build_find_entities_script("SOLID")

    entities = [
        {"id": "A", "radius": 0.5, "origin": [0, 0, 0]},
        {"id": "B", "radius": 0.1, "origin": [1, 0, 0]},
        {"id": "C", "origin": [2, 0, 0]},
    ]
    assert [e["id"] for e in filter_entities(entities, radius_between_m=(0.4, 0.6))] == ["A"]
    nearest = filter_entities(entities, near_point_m=[2.0, 0.0, 0.0])
    assert nearest[0]["id"] == "C"
