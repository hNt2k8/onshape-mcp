"""Offline tests for OnshapeClient behavior using httpx.MockTransport."""

import httpx
import pytest

from onshape_mcp.client import OnshapeClient, QuotaExhaustedError
from onshape_mcp.config import Config


def make_client(handler, tmp_path, auth="hmac"):
    config = Config(access_key="a" * 24, secret_key="s" * 48, auth=auth)
    return OnshapeClient(
        config,
        call_log_path=tmp_path / "call_log",
        courtesy_delay_s=0.0,
        transport=httpx.MockTransport(handler),
    )


def test_signed_request_carries_auth_headers(tmp_path):
    seen = {}

    def handler(request):
        seen.update(request.headers)
        return httpx.Response(200, json={"ok": True})

    with make_client(handler, tmp_path) as client:
        result = client.request_json("GET", "/users/sessioninfo")
    assert result == {"ok": True}
    assert seen["authorization"].startswith("On ")
    assert ":HmacSHA256:" in seen["authorization"]
    assert seen["content-type"] == "application/json"
    assert "on-nonce" in seen
    assert "date" in seen


def test_basic_auth_mode(tmp_path):
    seen = {}

    def handler(request):
        seen.update(request.headers)
        return httpx.Response(200, json={})

    with make_client(handler, tmp_path, auth="basic") as client:
        client.request("GET", "/users/sessioninfo")
    assert seen["authorization"].startswith("Basic ")


def test_query_params_reach_the_wire(tmp_path):
    seen = {}

    def handler(request):
        seen["query"] = request.url.query.decode()
        return httpx.Response(200, json={})

    with make_client(handler, tmp_path) as client:
        client.request("GET", "/documents", params={"limit": 1})
    assert seen["query"] == "limit=1"


def test_429_retries_then_succeeds(tmp_path):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"ok": True})

    with make_client(handler, tmp_path) as client:
        response = client.request("GET", "/documents")
    assert response.status_code == 200
    assert calls["n"] == 3


def test_402_raises_quota_error(tmp_path):
    def handler(request):
        return httpx.Response(402, text="quota exceeded")

    with make_client(handler, tmp_path) as client:
        with pytest.raises(QuotaExhaustedError, match="quota"):
            client.request("GET", "/documents")


def test_redirects_not_followed(tmp_path):
    def handler(request):
        return httpx.Response(307, headers={"Location": "https://other.example/file"})

    with make_client(handler, tmp_path) as client:
        response = client.request("GET", "/partstudios/stl")
    assert response.status_code == 307
    assert response.headers["Location"] == "https://other.example/file"


def test_call_log_persists_and_quota_counts_2xx_3xx_only(tmp_path):
    statuses = iter([200, 307, 404])

    def handler(request):
        return httpx.Response(next(statuses))

    with make_client(handler, tmp_path) as client:
        for _ in range(3):
            client.request("GET", "/documents")
        assert client.quota_count == 2  # 200 + 307; the 404 doesn't count

    log_lines = (tmp_path / "call_log").read_text().strip().splitlines()
    assert len(log_lines) == 3

    # A fresh client re-loads the persisted quota count.
    def handler_ok(request):
        return httpx.Response(200)

    with make_client(handler_ok, tmp_path) as client2:
        assert client2.quota_count == 2


def test_caller_content_type_is_signed_not_clobbered(tmp_path):
    # A caller-supplied Content-Type must end up both on the wire AND inside
    # the signature — recompute the HMAC server-style from the received
    # request and check it matches the Authorization header.
    import base64
    import hashlib
    import hmac as hmac_mod

    seen = {}

    def handler(request):
        seen["content_type"] = request.headers["Content-Type"]
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
        seen["server_sig"] = base64.b64encode(
            hmac_mod.new(
                ("s" * 48).encode(), string_to_sign.lower().encode(), hashlib.sha256
            ).digest()
        ).decode()
        seen["sent_sig"] = request.headers["Authorization"].rsplit(":", 1)[1]
        return httpx.Response(200, json={})

    with make_client(handler, tmp_path) as client:
        client.request(
            "POST",
            "/blobelements",
            json_body={"x": 1},
            headers={"Content-Type": "multipart/form-data; boundary=xyz"},
        )
    assert seen["content_type"] == "multipart/form-data; boundary=xyz"
    assert seen["sent_sig"] == seen["server_sig"]


def test_quota_count_windows_to_last_365_days(tmp_path):
    from datetime import datetime, timedelta, timezone

    def stamp(days_ago):
        when = datetime.now(timezone.utc) - timedelta(days=days_ago)
        return when.strftime("%Y-%m-%dT%H:%M:%SZ")

    log = tmp_path / "call_log"
    log.write_text(
        f"{stamp(400)} GET /api/v10/documents 200\n"  # older than a year: excluded
        f"{stamp(10)} GET /api/v10/documents 200\n"  # recent: counted
        f"{stamp(10)} GET /api/v10/documents 404\n"  # 4xx: not quota
        "garbage line that should not crash parsing\n"
    )

    def handler(request):
        return httpx.Response(200)

    with make_client(handler, tmp_path) as client:
        assert client.quota_count == 1


def test_absolute_url_passthrough_for_redirect_resigning(tmp_path):
    seen = {}

    def handler(request):
        seen["host"] = request.url.host
        seen["auth"] = request.headers.get("authorization", "")
        return httpx.Response(200, json={})

    with make_client(handler, tmp_path) as client:
        client.request("GET", "https://other.example/api/v10/file?x=1")
    assert seen["host"] == "other.example"
    assert seen["auth"].startswith("On ")
