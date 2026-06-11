#!/usr/bin/env bash
# Register the onshape MCP server into the CURRENT project (project-scoped .mcp.json).
# Run from the CAD project folder where you want the server available.
set -euo pipefail

CAD_MCP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v claude >/dev/null 2>&1; then
  echo "error: 'claude' CLI not found on PATH" >&2
  exit 1
fi

# --no-editable: editable (.pth-based) installs silently break on this machine;
# see [tool.uv] comment in pyproject.toml.
claude mcp add --scope project onshape -- \
  uv run --quiet --no-editable --project "$CAD_MCP_DIR" onshape-mcp

echo "Registered 'onshape' MCP server (project scope) in $(pwd)/.mcp.json"
echo "Note: the first interactive Claude Code session will show 'Pending approval' — approve it."
