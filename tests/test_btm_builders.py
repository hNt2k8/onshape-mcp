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
