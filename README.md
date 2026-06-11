# onshape-mcp

MCP server that drives OnShape CAD from Claude Code: parametric modeling
(sketches, extrudes, revolves, fillets, patterns), FeatureScript queries, and
STL export/verification — via the OnShape REST API.

## One-time setup

```bash
uv sync --no-editable
uv run --no-editable onshape-mcp setup    # writes ~/.config/onshape-mcp/.env (chmod 600); no-op if it exists
uv run --no-editable onshape-mcp doctor   # auth smoke test against the live API (4 calls)
```

> **Why `--no-editable` everywhere?** macOS asynchronously marks files under
> `.venv` with the `hidden` flag here, and Python ≥3.13.8 skips hidden `.pth`
> files — editable installs silently stop importing minutes after a sync.
> Non-editable installs don't use `.pth` and are immune.

API keys come from https://dev-portal.onshape.com/keys. Credentials live only
in `~/.config/onshape-mcp/.env` — never in project folders.

## Per-project registration

From the CAD project folder where you want the server available:

```bash
~/Documents/Antigravity/CAD-MCP/install.sh
```

or equivalently:

```bash
claude mcp add --scope project onshape -- \
  uv run --quiet --no-editable --project ~/Documents/Antigravity/CAD-MCP onshape-mcp
```

(`--project`, not `--directory`: the server resolves the CAD-MCP venv but keeps
the caller's cwd. File-path tool params should be absolute paths regardless.)
Project-scoped servers show "Pending approval" on the first interactive
session — approve when prompted.

## Quota warning

OnShape EDU/Free accounts have an annual API quota (~2,500 calls/user/year);
exhaustion returns 402 and no backoff fixes it. This server keeps a persistent
call counter at `~/.config/onshape-mcp/call_log` and logs a running total to
stderr. Monitor usage in OnShape under My Account → Developer.

## Development

```bash
uv run --no-editable pytest          # offline tests (no API calls, no credentials needed)
uv run --no-editable onshape-mcp doctor
```
