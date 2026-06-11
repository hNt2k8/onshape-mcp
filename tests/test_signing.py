"""Offline tests for HMAC request signing (no network)."""

import base64
import hashlib
import hmac

from onshape_mcp.client import build_basic_headers, build_hmac_headers

ACCESS = "test_access_key"
SECRET = "test_secret_key"
URL = "https://cad.onshape.com/api/v10/documents?limit=1"
DATE = "Mon, 01 Jan 2024 00:00:00 GMT"
NONCE = "abcdefghijklmnop"

# Computed once from the documented formula:
# base64(HMAC-SHA256(secret, lowercase(method\nnonce\ndate\ncontent-type\npath\nquery\n)))
FROZEN_SIGNATURE = "Wa2PVllPjuQWVGGwGaIrt4OGTjmekFQbjvuF/7tYYvk="


def test_signature_matches_frozen_vector():
    headers = build_hmac_headers(
        "GET", URL, ACCESS, SECRET, date=DATE, nonce=NONCE
    )
    assert headers["Authorization"] == f"On {ACCESS}:HmacSHA256:{FROZEN_SIGNATURE}"
    assert headers["Date"] == DATE
    assert headers["On-Nonce"] == NONCE


def test_signature_matches_independent_reimplementation():
    headers = build_hmac_headers(
        "POST", URL, ACCESS, SECRET, date=DATE, nonce=NONCE
    )
    string_to_sign = (
        f"POST\n{NONCE}\n{DATE}\napplication/json\n/api/v10/documents\nlimit=1\n"
    ).lower()
    expected = base64.b64encode(
        hmac.new(SECRET.encode(), string_to_sign.encode(), hashlib.sha256).digest()
    ).decode()
    assert headers["Authorization"].endswith(f":{expected}")


def test_content_type_always_present_even_on_get():
    headers = build_hmac_headers("GET", URL, ACCESS, SECRET)
    assert headers["Content-Type"] == "application/json"


def test_default_nonce_is_long_alnum_and_unique():
    h1 = build_hmac_headers("GET", URL, ACCESS, SECRET)
    h2 = build_hmac_headers("GET", URL, ACCESS, SECRET)
    for h in (h1, h2):
        assert len(h["On-Nonce"]) >= 16
        assert h["On-Nonce"].isalnum()
    assert h1["On-Nonce"] != h2["On-Nonce"]


def test_empty_query_signs_empty_string():
    headers = build_hmac_headers(
        "GET",
        "https://cad.onshape.com/api/v10/users/sessioninfo",
        ACCESS,
        SECRET,
        date=DATE,
        nonce=NONCE,
    )
    string_to_sign = (
        f"GET\n{NONCE}\n{DATE}\napplication/json\n/api/v10/users/sessioninfo\n\n"
    ).lower()
    expected = base64.b64encode(
        hmac.new(SECRET.encode(), string_to_sign.encode(), hashlib.sha256).digest()
    ).decode()
    assert headers["Authorization"].endswith(f":{expected}")


def test_basic_auth_header():
    headers = build_basic_headers(ACCESS, SECRET)
    token = base64.b64encode(f"{ACCESS}:{SECRET}".encode()).decode()
    assert headers["Authorization"] == f"Basic {token}"
    assert headers["Content-Type"] == "application/json"


def test_signature_uses_percent_encoded_path():
    # The server verifies against the encoded path as it appears on the wire
    # (httpx's .path property would decode %2B -> '+', %2F -> '/', desyncing
    # the signature). Independent reimplementation via urlsplit, which
    # preserves percent-encoding.
    from urllib.parse import urlsplit

    url = "https://cad.onshape.com/api/v10/parts/d/1/w/2/e/3/partid/JHD%2BX?withMass=true"
    headers = build_hmac_headers("GET", url, ACCESS, SECRET, date=DATE, nonce=NONCE)
    parts = urlsplit(url)
    string_to_sign = (
        f"GET\n{NONCE}\n{DATE}\napplication/json\n{parts.path}\n{parts.query}\n"
    ).lower()
    assert "%2b" in string_to_sign  # encoded form survives into the signature
    expected = base64.b64encode(
        hmac.new(SECRET.encode(), string_to_sign.encode(), hashlib.sha256).digest()
    ).decode()
    assert headers["Authorization"].endswith(f":{expected}")


def test_custom_content_type_is_signed():
    content_type = "multipart/form-data; boundary=xyz"
    headers = build_hmac_headers(
        "POST", URL, ACCESS, SECRET, date=DATE, nonce=NONCE, content_type=content_type
    )
    assert headers["Content-Type"] == content_type
    string_to_sign = (
        f"POST\n{NONCE}\n{DATE}\n{content_type}\n/api/v10/documents\nlimit=1\n"
    ).lower()
    expected = base64.b64encode(
        hmac.new(SECRET.encode(), string_to_sign.encode(), hashlib.sha256).digest()
    ).decode()
    assert headers["Authorization"].endswith(f":{expected}")
