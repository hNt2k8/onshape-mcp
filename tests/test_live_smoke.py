"""Live API smoke tests. OPT-IN ONLY: these spend real quota calls
(EDU ~2,500/year), so they require both valid credentials and
ONSHAPE_LIVE_TESTS=1. Plain `pytest` never touches the network."""

import os

import pytest

from onshape_mcp.config import ConfigError, load_config

pytestmark = pytest.mark.skipif(
    os.environ.get("ONSHAPE_LIVE_TESTS") != "1",
    reason="live tests spend annual API quota; set ONSHAPE_LIVE_TESTS=1 to run",
)


def _client():
    from onshape_mcp.client import OnshapeClient

    try:
        return OnshapeClient(load_config())
    except ConfigError:
        pytest.skip("no OnShape credentials configured")


def test_sessioninfo_and_documents_both_auth_modes():
    client = _client()
    for auth in ("hmac", "basic"):
        client.config = client.config.with_auth(auth)
        assert client.request("GET", "/users/sessioninfo").status_code == 200
        assert (
            client.request("GET", "/documents", params={"limit": 1}).status_code == 200
        )
