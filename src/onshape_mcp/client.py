"""HTTP client for the OnShape REST API.

- HMAC-SHA256 request signing (API keys) with Basic auth fallback.
- Redirects are NOT followed automatically: OnShape export endpoints 307 to a
  different host, and the signature must be recomputed for the new URL.
- 429 -> exponential backoff honoring Retry-After. 402 -> annual quota
  exhausted (hard error, no retry helps).
- Persistent call counter at ~/.config/onshape-mcp/call_log; only 2xx/3xx
  responses count toward OnShape's annual quota (EDU ~2,500/user/year).
- All diagnostics go to stderr (stdout belongs to the MCP stdio transport).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json as jsonlib
import re
import secrets
import sys
import time
from datetime import datetime, timedelta, timezone
from email.utils import formatdate
from pathlib import Path
from typing import Any

import httpx

from .config import CALL_LOG, Config

CONTENT_TYPE = "application/json"
MAX_429_RETRIES = 5
COURTESY_DELAY_S = 0.2
TIMEOUT_S = 60.0

_LOG_LINE = re.compile(r"^(\S+) \S+ \S+ (\d{3})$")


class OnshapeApiError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, body: str | None = None):
        self.status = status
        self.body = (body or "")[:2000]
        super().__init__(message if not self.body else f"{message}: {self.body}")


class QuotaExhaustedError(OnshapeApiError):
    """402 Payment Required: the annual API-call quota is exhausted."""


def build_hmac_headers(
    method: str,
    url: str,
    access_key: str,
    secret_key: str,
    *,
    date: str | None = None,
    nonce: str | None = None,
    content_type: str = CONTENT_TYPE,
) -> dict[str, str]:
    """Signed headers for one request.

    Signature string is lowercase(method\\nnonce\\ndate\\ncontent-type\\npath\\nquery\\n)
    HMAC-SHA256'd with the secret key. Content-Type is always part of the
    signature, so it is always sent — including on GETs. The server verifies
    against the percent-ENCODED path exactly as it appears on the wire, so the
    path must come from the raw URL bytes (httpx's .path property decodes
    %-escapes and would desync the signature).
    """
    parsed = httpx.URL(url)
    raw_target = parsed.raw_path.decode("ascii")  # encoded wire bytes, incl. query
    path, _, query = raw_target.partition("?")
    date = date or formatdate(usegmt=True)
    nonce = nonce or secrets.token_hex(16)
    string_to_sign = "\n".join([method, nonce, date, content_type, path, query]) + "\n"
    digest = hmac.new(
        secret_key.encode(), string_to_sign.lower().encode(), hashlib.sha256
    ).digest()
    signature = base64.b64encode(digest).decode()
    return {
        "Date": date,
        "On-Nonce": nonce,
        "Content-Type": content_type,
        "Authorization": f"On {access_key}:HmacSHA256:{signature}",
    }


def build_basic_headers(access_key: str, secret_key: str) -> dict[str, str]:
    token = base64.b64encode(f"{access_key}:{secret_key}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": CONTENT_TYPE}


class OnshapeClient:
    def __init__(
        self,
        config: Config,
        *,
        call_log_path: Path = CALL_LOG,
        courtesy_delay_s: float = COURTESY_DELAY_S,
        transport: httpx.BaseTransport | None = None,
    ):
        self.config = config
        self._call_log_path = call_log_path
        self._courtesy_delay_s = courtesy_delay_s
        self._http = httpx.Client(
            follow_redirects=False, timeout=TIMEOUT_S, transport=transport
        )
        self._quota_count = self._load_quota_count()
        self._last_call_at = 0.0

    # -- lifecycle -----------------------------------------------------------

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "OnshapeClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- public API ----------------------------------------------------------

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        files: Any = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Issue one signed request. `path` is relative to the API root
        (e.g. "/users/sessioninfo") or a full URL (used when re-signing a
        redirect Location). Returns the response without raising on HTTP
        error status, except 402 (quota) which always raises.

        `json_body` is serialized to a JSON string. For uploads, pass httpx
        `files=` / `data=` instead: httpx then builds a multipart body and its
        own Content-Type (with boundary), which _build_request signs verbatim.
        `files` values must be in-memory bytes, not open file objects — a 429
        retry rebuilds the request and would otherwise send an exhausted stream.
        """
        if json_body is not None and (files is not None or data is not None):
            raise ValueError("pass json_body OR files/data, not both")
        method = method.upper()
        url = self._url_for(path, params)
        body = jsonlib.dumps(json_body) if json_body is not None else None

        attempt = 0
        while True:
            self._throttle()
            request = self._build_request(method, url, body, headers, files, data)
            response = self._http.send(request)
            self._record_call(method, request.url, response.status_code)

            if response.status_code == 429 and attempt < MAX_429_RETRIES:
                delay = self._retry_delay(response, attempt)
                print(
                    f"[onshape-mcp] 429 rate-limited; retrying in {delay:.1f}s "
                    f"(attempt {attempt + 1}/{MAX_429_RETRIES})",
                    file=sys.stderr,
                )
                time.sleep(delay)
                attempt += 1
                continue

            if response.status_code == 402:
                raise QuotaExhaustedError(
                    "OnShape annual API quota exhausted (402 Payment Required). "
                    "No retry/backoff can fix this — check My Account -> Developer "
                    "in OnShape for usage, or wait for the quota year to reset.",
                    status=402,
                    body=response.text,
                )

            return response

    def request_json(self, method: str, path: str, **kwargs: Any) -> Any:
        """request() + raise OnshapeApiError on >=400 + parse JSON body."""
        response = self.request(method, path, **kwargs)
        if response.status_code >= 400:
            raise OnshapeApiError(
                f"{method.upper()} {path} -> HTTP {response.status_code}",
                status=response.status_code,
                body=response.text,
            )
        if not response.content:
            return None
        return response.json()

    @property
    def quota_count(self) -> int:
        """Quota-relevant (2xx/3xx) calls recorded in the persistent log."""
        return self._quota_count

    # -- internals -----------------------------------------------------------

    def _url_for(self, path: str, params: dict[str, Any] | None) -> str:
        if path.startswith(("http://", "https://")):
            url = httpx.URL(path)
        else:
            url = httpx.URL(self.config.api_root + path)
        if params:
            url = url.copy_merge_params(params)
        return str(url)

    def _build_request(
        self,
        method: str,
        url: str,
        body: str | None,
        extra_headers: dict[str, str] | None,
        files: Any = None,
        data: dict[str, Any] | None = None,
    ) -> httpx.Request:
        # Build the request and apply caller headers first, then sign the exact
        # URL and effective Content-Type httpx will send, so the signature
        # always matches the wire bytes (incl. redirect re-signs and non-JSON
        # uploads). Auth headers go last: the client owns Date / On-Nonce /
        # Authorization / Content-Type.
        build_kwargs: dict[str, Any] = {"headers": {"Accept": "application/json"}}
        if files is not None or data is not None:
            # httpx generates the multipart boundary here; it lands in the
            # request's Content-Type below and is what actually gets signed.
            build_kwargs["files"] = files
            build_kwargs["data"] = data or {}
        else:
            build_kwargs["content"] = body
        request = self._http.build_request(method, url, **build_kwargs)
        if extra_headers:
            request.headers.update(extra_headers)
        content_type = request.headers.get("Content-Type", CONTENT_TYPE)
        if self.config.auth == "basic":
            auth_headers = build_basic_headers(
                self.config.access_key, self.config.secret_key
            )
            auth_headers["Content-Type"] = content_type
        else:
            auth_headers = build_hmac_headers(
                method,
                str(request.url),
                self.config.access_key,
                self.config.secret_key,
                content_type=content_type,
            )
        request.headers.update(auth_headers)
        return request

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call_at
        if elapsed < self._courtesy_delay_s:
            time.sleep(self._courtesy_delay_s - elapsed)
        self._last_call_at = time.monotonic()

    @staticmethod
    def _retry_delay(response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                pass
        return float(2**attempt)

    def _load_quota_count(self) -> int:
        # OnShape's quota is annual, so only count the last 365 days. Lines are
        # "<iso-utc> <method> <target> <status>"; only 2xx/3xx count toward quota.
        cutoff = datetime.now(timezone.utc) - timedelta(days=365)
        count = 0
        try:
            with open(self._call_log_path, encoding="utf-8") as f:
                for line in f:
                    match = _LOG_LINE.match(line.strip())
                    if not match or match.group(2)[0] not in "23":
                        continue
                    try:
                        stamp = datetime.strptime(
                            match.group(1), "%Y-%m-%dT%H:%M:%SZ"
                        ).replace(tzinfo=timezone.utc)
                    except ValueError:
                        continue
                    if stamp >= cutoff:
                        count += 1
        except FileNotFoundError:
            return 0
        except (OSError, UnicodeDecodeError) as e:
            print(f"[onshape-mcp] call_log read failed: {e}", file=sys.stderr)
            return 0
        return count

    def _record_call(self, method: str, url: httpx.URL, status: int) -> None:
        if 200 <= status < 400:
            self._quota_count += 1
        # raw_path = encoded wire bytes incl. query; never contains whitespace,
        # so the one-line-per-call log format stays parseable.
        target = url.raw_path.decode("ascii")
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            self._call_log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._call_log_path, "a", encoding="utf-8") as f:
                f.write(f"{timestamp} {method} {target} {status}\n")
        except OSError as e:
            print(f"[onshape-mcp] call_log write failed: {e}", file=sys.stderr)
        print(
            f"[onshape-mcp] {method} {target} -> {status} | quota calls "
            f"(last 365d): {self._quota_count}",
            file=sys.stderr,
        )
