"""CLI entry point: serve (default, stdio MCP), setup (write creds), doctor.

Secrets are never echoed; setup reads them via getpass and doctor only
reports HTTP status codes.
"""

from __future__ import annotations

import argparse
import getpass
import os
import stat
import sys

from .config import (
    CONFIG_DIR,
    ENV_FILE,
    ConfigError,
    load_config,
)

ENV_TEMPLATE = """\
# OnShape API credentials for onshape-mcp.
# Create keys at https://dev-portal.onshape.com/keys
ONSHAPE_ACCESS_KEY={access_key}
ONSHAPE_SECRET_KEY={secret_key}

# Optional overrides (uncomment to use):
# ONSHAPE_BASE_URL=https://cad.onshape.com
# ONSHAPE_API_VERSION=v10
# ONSHAPE_AUTH=hmac
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="onshape-mcp",
        description="MCP server for OnShape CAD",
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("serve", help="run the MCP server on stdio (default)")
    sub.add_parser("setup", help=f"create {ENV_FILE} (never overwrites an existing file)")
    sub.add_parser("doctor", help="auth smoke test against the live OnShape API")

    args = parser.parse_args(argv)
    command = args.command or "serve"

    if command == "serve":
        return cmd_serve()
    if command == "setup":
        return cmd_setup()
    return cmd_doctor()


def cmd_serve() -> int:
    try:
        load_config()
    except ConfigError as e:
        print(f"[onshape-mcp] {e}", file=sys.stderr)
        return 1
    from .server import run

    run()
    return 0


def cmd_setup() -> int:
    if ENV_FILE.exists():
        print(f"{ENV_FILE} already exists — leaving it untouched.")
        missing = _missing_env_vars()
        if missing:
            print(
                f"WARNING: {', '.join(missing)} missing or empty in that file. "
                "Edit the file directly to fill them in (do not paste keys anywhere else)."
            )
            return 1
        print("Both ONSHAPE_ACCESS_KEY and ONSHAPE_SECRET_KEY are present.")
        print("Run `uv run onshape-mcp doctor` to validate them against the live API.")
        return 0

    print("Creating OnShape credentials file.")
    print("Get API keys from https://dev-portal.onshape.com/keys")
    access_key = getpass.getpass("Access key (input hidden): ").strip()
    secret_key = getpass.getpass("Secret key (input hidden): ").strip()
    if not access_key or not secret_key:
        print("Both keys are required; nothing written.", file=sys.stderr)
        return 1

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(CONFIG_DIR, stat.S_IRWXU)  # 700
    # Create with 600 perms before any content lands in the file.
    fd = os.open(ENV_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(ENV_TEMPLATE.format(access_key=access_key, secret_key=secret_key))
    print(f"Wrote {ENV_FILE} (chmod 600).")
    print("Run `uv run onshape-mcp doctor` to validate.")
    return 0


def _missing_env_vars() -> list[str]:
    from dotenv import dotenv_values

    vals = dotenv_values(ENV_FILE)
    return [
        name
        for name in ("ONSHAPE_ACCESS_KEY", "ONSHAPE_SECRET_KEY")
        if not vals.get(name)
    ]


def cmd_doctor() -> int:
    from .client import OnshapeClient

    try:
        config = load_config()
    except ConfigError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1

    print(f"API root: {config.api_root}")
    print(f"Configured auth mode for serve: {config.auth}")

    checks: list[tuple[str, str, int | None, str]] = []
    for auth in ("hmac", "basic"):
        with OnshapeClient(config.with_auth(auth)) as client:
            for path, params in (
                ("/users/sessioninfo", None),
                ("/documents", {"limit": 1}),
            ):
                label = f"{auth.upper():5s} GET {path}"
                try:
                    response = client.request("GET", path, params=params)
                    checks.append((label, "", response.status_code, ""))
                except Exception as e:  # noqa: BLE001 - doctor reports, never crashes
                    checks.append((label, "", None, str(e)))

    all_ok = True
    for label, _, status, error in checks:
        if status == 200:
            print(f"  PASS  {label} -> 200")
        else:
            all_ok = False
            detail = f"HTTP {status}" if status is not None else error
            print(f"  FAIL  {label} -> {detail}")

    if all_ok:
        print("doctor: all checks passed.")
        return 0
    print(
        "doctor: FAILED. If both HMAC and Basic return 401, the keys are the "
        "likely culprit; if only HMAC fails, suspect the signature code first.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
