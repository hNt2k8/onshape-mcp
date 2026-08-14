"""Offline tests for CAD import (multipart upload + translation poll)."""

import base64
import hashlib
import hmac as hmac_mod

import httpx
import pytest

from onshape_mcp.api import imports as imports_api
from onshape_mcp.client import OnshapeApiError, OnshapeClient
from onshape_mcp.config import Config


def make_client(handler, tmp_path):
    config = Config(access_key="a" * 24, secret_key="s" * 48)
    return OnshapeClient(
        config,
        call_log_path=tmp_path / "call_log",
        courtesy_delay_s=0.0,
        transport=httpx.MockTransport(handler),
    )


def make_zip(tmp_path, content=b"PK\x03\x04fake-inventor-assembly"):
    path = tmp_path / "assembly.zip"
    path.write_bytes(content)
    return path


def test_import_cad_uploads_multipart_and_polls_to_done(tmp_path):
    zip_path = make_zip(tmp_path)
    state = {"upload": None, "polls": 0}

    def handler(request):
        path = request.url.path
        if request.method == "POST" and path == "/api/v10/blobelements/d/d1/w/w1":
            state["upload"] = {
                "content_type": request.headers["Content-Type"],
                "body": request.content,
            }
            return httpx.Response(
                200,
                json={
                    "id": "blob1",
                    "name": "assembly.zip",
                    "translationId": "t1",
                },
            )
        if path == "/api/v10/translations/t1":
            state["polls"] += 1
            if state["polls"] < 2:  # exercise the ACTIVE -> DONE poll loop
                return httpx.Response(200, json={"requestState": "ACTIVE"})
            return httpx.Response(
                200,
                json={
                    "requestState": "DONE",
                    "resultElementIds": ["e1", "e2"],
                    "resultDocumentId": "d1",
                    "resultWorkspaceId": "w1",
                },
            )
        raise AssertionError(f"unexpected: {request.method} {path}")

    with make_client(handler, tmp_path) as client:
        result = imports_api.import_cad(
            client, "d1", "w1", str(zip_path), poll_interval_s=0.0
        )

    assert result == {
        "elementId": "blob1",
        "name": "assembly.zip",
        "documentId": "d1",
        "workspaceId": "w1",
        "translationId": "t1",
        "translationState": "DONE",
        "resultElementIds": ["e1", "e2"],
        "resultDocumentId": "d1",
        "resultWorkspaceId": "w1",
    }
    assert state["polls"] == 2

    upload = state["upload"]
    assert upload["content_type"].startswith("multipart/form-data; boundary=")
    body = upload["body"]
    # The raw file bytes and the form fields both made it onto the wire.
    assert b"PK\x03\x04fake-inventor-assembly" in body
    assert b'name="file"; filename="assembly.zip"' in body
    assert b'name="encodedFilename"' in body
    # Booleans are sent as form strings, with the specified defaults.
    for field, value in [
        (b"translate", b"true"),
        (b"allowFaultyParts", b"true"),
        (b"splitAssembliesIntoMultipleDocuments", b"false"),
        (b"flattenAssemblies", b"false"),
        (b"notifyUser", b"false"),
    ]:
        marker = b'name="' + field + b'"\r\n\r\n' + value + b"\r\n"
        assert marker in body, f"missing form field {field!r}={value!r}"


def test_import_cad_signs_the_multipart_content_type(tmp_path):
    # The HMAC must cover the boundary-bearing Content-Type httpx generated,
    # not a hardcoded application/json. Recompute the signature server-style.
    zip_path = make_zip(tmp_path)
    seen = {}

    def handler(request):
        if request.method == "POST":
            string_to_sign = "\n".join(
                [
                    request.method,
                    request.headers["On-Nonce"],
                    request.headers["Date"],
                    request.headers["Content-Type"],
                    request.url.raw_path.decode().partition("?")[0],
                    request.url.query.decode(),
                ]
            ) + "\n"
            seen["content_type"] = request.headers["Content-Type"]
            seen["server_sig"] = base64.b64encode(
                hmac_mod.new(
                    ("s" * 48).encode(), string_to_sign.lower().encode(), hashlib.sha256
                ).digest()
            ).decode()
            seen["sent_sig"] = request.headers["Authorization"].rsplit(":", 1)[1]
            return httpx.Response(200, json={"id": "blob1"})
        raise AssertionError("no translation expected")

    with make_client(handler, tmp_path) as client:
        imports_api.import_cad(client, "d1", "w1", str(zip_path), translate=False)

    assert "boundary=" in seen["content_type"]
    assert seen["sent_sig"] == seen["server_sig"]


def test_import_cad_without_translate_skips_polling(tmp_path):
    zip_path = make_zip(tmp_path)

    def handler(request):
        assert request.method == "POST", "no poll should happen"
        return httpx.Response(200, json={"id": "blob1", "name": "assembly.zip"})

    with make_client(handler, tmp_path) as client:
        result = imports_api.import_cad(
            client, "d1", "w1", str(zip_path), translate=False
        )

    assert result["elementId"] == "blob1"
    assert result["translationId"] is None
    assert result["translationState"] is None
    assert result["resultElementIds"] == []


def test_import_cad_raises_on_failed_translation(tmp_path):
    zip_path = make_zip(tmp_path)

    def handler(request):
        if request.method == "POST":
            return httpx.Response(200, json={"id": "blob1", "translationId": "t1"})
        return httpx.Response(
            200, json={"requestState": "FAILED", "failureReason": "bad geometry"}
        )

    with make_client(handler, tmp_path) as client:
        with pytest.raises(OnshapeApiError, match="FAILED: bad geometry"):
            imports_api.import_cad(
                client, "d1", "w1", str(zip_path), poll_interval_s=0.0
            )


def test_import_cad_rejects_relative_and_missing_paths(tmp_path):
    def handler(request):
        raise AssertionError("no API call should be made")

    with make_client(handler, tmp_path) as client:
        with pytest.raises(OnshapeApiError, match="ABSOLUTE"):
            imports_api.import_cad(client, "d1", "w1", "assembly.zip")
        with pytest.raises(OnshapeApiError, match="file not found"):
            imports_api.import_cad(client, "d1", "w1", str(tmp_path / "nope.zip"))


def test_import_cad_survives_a_429_retry(tmp_path):
    # The retry rebuilds the request; the file must be re-sent in full, which
    # is why the payload is held in memory rather than as an open file handle.
    zip_path = make_zip(tmp_path)
    bodies = []

    def handler(request):
        if request.method == "POST":
            bodies.append(request.content)
            if len(bodies) == 1:
                return httpx.Response(429, headers={"Retry-After": "0"})
            return httpx.Response(200, json={"id": "blob1"})
        raise AssertionError("no translation expected")

    with make_client(handler, tmp_path) as client:
        result = imports_api.import_cad(
            client, "d1", "w1", str(zip_path), translate=False
        )

    assert result["elementId"] == "blob1"
    assert len(bodies) == 2
    assert all(b"PK\x03\x04fake-inventor-assembly" in body for body in bodies)


def test_request_rejects_json_body_with_files(tmp_path):
    def handler(request):
        raise AssertionError("no API call should be made")

    with make_client(handler, tmp_path) as client:
        with pytest.raises(ValueError, match="not both"):
            client.request(
                "POST", "/blobelements", json_body={"a": 1}, data={"b": "2"}
            )


def test_create_document_sends_parent_id_only_when_set(tmp_path):
    import json as jsonlib

    from onshape_mcp.api import documents as docs_api

    bodies = []

    def handler(request):
        if request.method == "POST" and request.url.path == "/api/v10/documents":
            bodies.append(jsonlib.loads(request.content))
            return httpx.Response(
                200,
                json={"id": "doc1", "name": "Test", "defaultWorkspace": {"id": "ws1"}},
            )
        return httpx.Response(
            200,
            json=[{"id": "el1", "name": "Part Studio 1", "elementType": "PARTSTUDIO"}],
        )

    with make_client(handler, tmp_path) as client:
        docs_api.create_document(client, "Test")
        docs_api.create_document(client, "Test", parent_id="folder123")

    assert "parentId" not in bodies[0]
    assert bodies[1]["parentId"] == "folder123"


def test_server_registers_import_cad():
    import asyncio

    from onshape_mcp.server import mcp

    tools = {tool.name for tool in asyncio.run(mcp.list_tools())}
    assert "import_cad" in tools
