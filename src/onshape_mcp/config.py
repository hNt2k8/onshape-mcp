"""Credential and endpoint configuration.

Precedence: process environment > ~/.config/onshape-mcp/.env > error with setup hint.
Secret values must never be printed, logged, or included in tool output.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path

from dotenv import dotenv_values

CONFIG_DIR = Path.home() / ".config" / "onshape-mcp"
ENV_FILE = CONFIG_DIR / ".env"
CALL_LOG = CONFIG_DIR / "call_log"

DEFAULT_BASE_URL = "https://cad.onshape.com"
DEFAULT_API_VERSION = "v10"
VALID_AUTH = ("hmac", "basic")

SETUP_HINT = (
    "OnShape credentials not found. Run `uv run onshape-mcp setup` to create "
    f"{ENV_FILE}, or set ONSHAPE_ACCESS_KEY / ONSHAPE_SECRET_KEY in the environment."
)


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Config:
    # repr=False keeps secrets out of repr()/str() only — dataclasses.asdict,
    # astuple, and vars() still expose them. Never serialize this object.
    access_key: str = field(repr=False)
    secret_key: str = field(repr=False)
    base_url: str = DEFAULT_BASE_URL
    api_version: str = DEFAULT_API_VERSION
    auth: str = "hmac"

    @property
    def api_root(self) -> str:
        return f"{self.base_url.rstrip('/')}/api/{self.api_version}"

    def with_auth(self, auth: str) -> "Config":
        if auth not in VALID_AUTH:
            raise ConfigError(f"ONSHAPE_AUTH must be one of {VALID_AUTH}, got {auth!r}")
        return replace(self, auth=auth)


def load_config(env_file: Path = ENV_FILE) -> Config:
    file_vals = dotenv_values(env_file) if env_file.exists() else {}

    def get(name: str, default: str | None = None) -> str | None:
        # Strip BEFORE the falsy checks: a whitespace-only env var (a common
        # CI/shell artifact) must fall through to the file like an empty one.
        val = (os.environ.get(name) or "").strip()
        if not val:
            val = (file_vals.get(name) or "").strip()
        return val or default

    access_key = get("ONSHAPE_ACCESS_KEY")
    secret_key = get("ONSHAPE_SECRET_KEY")
    if not access_key or not secret_key:
        raise ConfigError(SETUP_HINT)

    auth = (get("ONSHAPE_AUTH", "hmac") or "hmac").lower()
    if auth not in VALID_AUTH:
        raise ConfigError(f"ONSHAPE_AUTH must be one of {VALID_AUTH}, got {auth!r}")

    return Config(
        access_key=access_key,
        secret_key=secret_key,
        base_url=get("ONSHAPE_BASE_URL", DEFAULT_BASE_URL),
        api_version=get("ONSHAPE_API_VERSION", DEFAULT_API_VERSION),
        auth=auth,
    )
