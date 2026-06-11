"""Offline tests for the api/ layer using httpx.MockTransport."""

import json

import httpx

from onshape_mcp.api import documents as docs_api
from onshape_mcp.api import partstudio as ps_api
from onshape_mcp.client import OnshapeClient
from onshape_mcp.config import Config


def make_client(handler, tmp_path):
    config = Config(access_key="a" * 24, secret_key="s" * 48)
    return OnshapeClient(
        config,
        call_log_path=tmp_path / "call_log",
        courtesy_delay_s=0.0,
        transport=httpx.MockTransport(handler),
    )


def test_create_document_resolves_default_part_studio(tmp_path):
    def handler(request):
        if request.method == "POST" and request.url.path == "/api/v10/documents":
            return httpx.Response(
                200,
                json={
                    "id": "doc1",
                    "name": "Test",
                    "defaultWorkspace": {"id": "ws1"},
                },
            )
        if request.url.path == "/api/v10/documents/d/doc1/w/ws1/elements":
            return httpx.Response(
                200,
                json=[
                    {"id": "el0", "name": "Assembly 1", "elementType": "ASSEMBLY"},
                    {"id": "el1", "name": "Part Studio 1", "elementType": "PARTSTUDIO"},
                ],
            )
        raise AssertionError(f"unexpected: {request.method} {request.url.path}")

    with make_client(handler, tmp_path) as client:
        result = docs_api.create_document(client, "Test")
    assert result == {
        "documentId": "doc1",
        "workspaceId": "ws1",
        "partStudioElementId": "el1",
        "name": "Test",
    }


def test_add_feature_wraps_bare_feature_in_envelope(tmp_path):
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "feature": {
                    "featureId": "f1",
                    "name": "Smoke Circle",
                    "featureType": "newSketch",
                },
                "featureState": {"featureStatus": "OK"},
            },
        )

    bare = {"btType": "BTMSketch-151", "featureType": "newSketch", "name": "Smoke Circle"}
    with make_client(handler, tmp_path) as client:
        result = ps_api.add_feature(client, "d1", "w1", "e1", bare)

    assert seen["body"]["btType"] == "BTFeatureDefinitionCall-1406"
    assert seen["body"]["feature"]["btType"] == "BTMSketch-151"
    assert result == {
        "featureId": "f1",
        "name": "Smoke Circle",
        "featureType": "newSketch",
        "featureStatus": "OK",
    }


def test_add_feature_passes_envelope_through(tmp_path):
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"feature": {}, "featureState": {}})

    envelope = {"btType": "BTFeatureDefinitionCall-1406", "feature": {"btType": "BTMSketch-151"}}
    with make_client(handler, tmp_path) as client:
        ps_api.add_feature(client, "d1", "w1", "e1", envelope)
    assert seen["body"] == envelope


def test_get_features_compact_and_verbose(tmp_path):
    feature_json = {
        "featureId": "f1",
        "name": "Sketch 1",
        "featureType": "newSketch",
        "parameters": [{"big": "blob"}],
    }

    def handler(request):
        return httpx.Response(
            200,
            json={
                "features": [feature_json],
                "featureStates": {"f1": {"featureStatus": "OK"}},
            },
        )

    with make_client(handler, tmp_path) as client:
        compact = ps_api.get_features(client, "d1", "w1", "e1")
        verbose = ps_api.get_features(client, "d1", "w1", "e1", verbose=True)

    assert compact == [
        {
            "featureId": "f1",
            "name": "Sketch 1",
            "featureType": "newSketch",
            "featureStatus": "OK",
        }
    ]
    assert verbose[0]["feature"] == feature_json


def test_eval_featurescript_unwraps_result(tmp_path):
    def handler(request):
        body = json.loads(request.content)
        # the live API requires queries to be a map, not an array
        assert "script" in body and body["queries"] == {}
        return httpx.Response(
            200,
            json={
                "result": {
                    "btType": "com.belmonttech.serialize.fsvalue.BTFSValueNumber",
                    "message": {"value": 42.0},
                },
            },
        )

    with make_client(handler, tmp_path) as client:
        result = ps_api.eval_featurescript(client, "d1", "w1", "e1", "function(...){}")
    assert result == {"result": 42.0}


def test_download_resigns_redirects_to_other_hosts(tmp_path):
    seen = []

    def handler(request):
        seen.append(
            (request.url.host, request.headers.get("authorization", ""))
        )
        if request.url.host == "cad.onshape.com":
            return httpx.Response(
                307, headers={"Location": "https://blob.example/signed/file?x=1"}
            )
        return httpx.Response(200, content=b"STLBYTES")

    from onshape_mcp.api import export as export_api

    with make_client(handler, tmp_path) as client:
        data = export_api.download(client, "/partstudios/d/1/w/2/e/3/stl", {"mode": "binary"})

    assert data == b"STLBYTES"
    assert [host for host, _ in seen] == ["cad.onshape.com", "blob.example"]
    # Both requests carried a FRESH HMAC signature (not a reused header).
    sigs = [auth for _, auth in seen]
    assert all(a.startswith("On ") for a in sigs)
    assert sigs[0] != sigs[1]


def test_download_gives_up_after_max_redirects(tmp_path):
    def handler(request):
        return httpx.Response(307, headers={"Location": "https://cad.onshape.com/loop"})

    from onshape_mcp.api import export as export_api
    from onshape_mcp.client import OnshapeApiError

    import pytest

    with make_client(handler, tmp_path) as client:
        with pytest.raises(OnshapeApiError, match="redirect"):
            export_api.download(client, "/loop", {})


def test_server_registers_all_m1_tools():
    import asyncio

    from onshape_mcp.server import mcp

    tools = {tool.name for tool in asyncio.run(mcp.list_tools())}
    assert tools >= {
        "list_documents",
        "create_document",
        "list_elements",
        "create_part_studio",
        "get_features",
        "add_feature",
        "update_feature",
        "delete_feature",
        "eval_featurescript",
        "create_sketch",
        "extrude",
        "revolve",
        "fillet_or_chamfer",
        "pattern",
        "boolean_parts",
        "create_offset_plane",
        "set_variable",
        "get_variables",
        "find_entities",
        "export_stl",
        "mass_properties",
        "list_parts",
    }
