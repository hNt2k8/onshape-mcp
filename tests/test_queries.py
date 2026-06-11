"""Offline tests for BTFSValue response unwrapping."""

from onshape_mcp.queries import unwrap_fs_value

FS = "com.belmonttech.serialize.fsvalue."


def num(value, units=None):
    if units:
        return {
            "btType": f"{FS}BTFSValueWithUnits",
            "message": {"value": value, "unitToPower": units},
        }
    return {"btType": f"{FS}BTFSValueNumber", "message": {"value": value}}


def string(value):
    return {"btType": f"{FS}BTFSValueString", "message": {"value": value}}


def test_primitives():
    assert unwrap_fs_value(num(1.5)) == 1.5
    assert unwrap_fs_value(string("Top")) == "Top"
    assert (
        unwrap_fs_value({"btType": f"{FS}BTFSValueBoolean", "message": {"value": True}})
        is True
    )
    assert unwrap_fs_value({"btType": f"{FS}BTFSValueUndefined", "message": {}}) is None


def test_with_units_returns_plain_number():
    node = num(0.0254, [{"key": "METER", "value": 1}])
    assert unwrap_fs_value(node) == 0.0254


def test_array_of_strings():
    node = {
        "btType": f"{FS}BTFSValueArray",
        "message": {"value": [string("JHD"), string("JHF")]},
    }
    assert unwrap_fs_value(node) == ["JHD", "JHF"]


def test_nested_map():
    node = {
        "btType": f"{FS}BTFSValueMap",
        "message": {
            "value": [
                {
                    "btType": f"{FS}BTFSValueMapEntry",
                    "message": {"key": string("radius"), "value": num(0.5)},
                },
                {
                    "btType": f"{FS}BTFSValueMapEntry",
                    "message": {
                        "key": string("origin"),
                        "value": {
                            "btType": f"{FS}BTFSValueArray",
                            "message": {"value": [num(0.0), num(1.0), num(2.0)]},
                        },
                    },
                },
            ]
        },
    }
    assert unwrap_fs_value(node) == {"radius": 0.5, "origin": [0.0, 1.0, 2.0]}


def test_unknown_node_keeps_bttype_and_fields():
    node = {
        "btType": f"{FS}BTFSValueOther",
        "message": {"weird": string("x")},
    }
    assert unwrap_fs_value(node) == {"weird": "x", "btType": f"{FS}BTFSValueOther"}


def test_plain_passthrough():
    assert unwrap_fs_value(None) is None
    assert unwrap_fs_value(3) == 3
    assert unwrap_fs_value([1, "a"]) == [1, "a"]


# Captured verbatim from the live API (M1 gate, 2026-06-11): unlike the REST
# docs' "message"-nested examples, real responses are FLAT — value/key sit
# directly on the node. The unwrapper must handle both shapes.
LIVE_FS_RESULT = {
    "btType": "com.belmonttech.serialize.fsvalue.BTFSValueMap",
    "typeTag": "",
    "value": [
        {
            "btType": "BTFSValueMapEntry-2077",
            "value": {
                "btType": "com.belmonttech.serialize.fsvalue.BTFSValueNumber",
                "typeTag": "",
                "value": 4.0,
            },
            "key": {
                "btType": "com.belmonttech.serialize.fsvalue.BTFSValueString",
                "typeTag": "",
                "value": "faceCount",
            },
        },
        {
            "btType": "BTFSValueMapEntry-2077",
            "value": {
                "btType": "com.belmonttech.serialize.fsvalue.BTFSValueArray",
                "typeTag": "",
                "value": [
                    {
                        "btType": "com.belmonttech.serialize.fsvalue.BTFSValueString",
                        "typeTag": "",
                        "value": "JCC",
                    },
                    {
                        "btType": "com.belmonttech.serialize.fsvalue.BTFSValueString",
                        "typeTag": "",
                        "value": "JDC",
                    },
                ],
            },
            "key": {
                "btType": "com.belmonttech.serialize.fsvalue.BTFSValueString",
                "typeTag": "",
                "value": "ids",
            },
        },
    ],
}


def test_live_captured_flat_shape():
    assert unwrap_fs_value(LIVE_FS_RESULT) == {
        "faceCount": 4.0,
        "ids": ["JCC", "JDC"],
    }
