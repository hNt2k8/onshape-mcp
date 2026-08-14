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

## Usage cheatsheet (for the LLM driving the tools)

**Typical build flow**

```
create_document (parentId = folder id)   -> documentId, workspaceId, partStudioElementId
import_cad (ABSOLUTE path to .zip/STEP)  -> foreign CAD into an existing workspace [async, +quota]
set_variable (optional, e.g. wall_thk)   -> use "#wall_thk" in later expressions
create_sketch (plane {"default":"TOP"})  -> featureId            [one closed profile per sketch]
extrude (sketchFeatureId, NEW, depth)    -> base solid
create_sketch + extrude REMOVE THROUGH_ALL                       [holes: skip native hole feature]
find_entities (EDGE, radiusBetween)      -> transient ids for fillet/chamfer
fillet_or_chamfer (entityIds)            -> check featureStatus == OK after EVERY feature
pattern / revolve / boolean_parts as needed
export_stl (ABSOLUTE path)               -> compare_stl(candidate, reference)  [mesh: 3D-print, verify]
export_step (ABSOLUTE path)              -> editable STEP B-rep solid           [CAD/prototyping; async, +quota]
```

**Iron rules**

1. **Transient IDs go stale after ANY mutation.** Always call `find_entities`
   immediately before the tool call that consumes the ids. Feature IDs
   (from create_sketch/extrude/...) are stable — prefer them where accepted
   (extrude regions, pattern seeds, boolean bodies).
2. **Units**: tool params and outputs are inches by default (`units` param to
   change). Dimension strings pass through: `"1.53 in"`, `"25 mm"`,
   `"#wall_thk * 2"`. Angles are degrees. `eval_featurescript` raw results
   are METERS/radians.
3. **featureStatus** is the regen feedback loop: `OK` proceed; `ERROR` means
   the feature was added but failed — fix parameters via `update_feature` or
   `delete_feature` and retry. Check it after every modeling call.
4. **extrude REMOVE subtracts from ALL solids** in the studio (defaultScope).
   Keep one part per studio unless you intend that.
5. One closed profile per sketch keeps extrude region selection unambiguous.
6. File paths must be ABSOLUTE (the server's cwd is not the project's).
7. Be frugal: ~2,500 API calls/YEAR. Don't poll, don't re-list needlessly;
   analyze_stl/compare_stl cost zero calls.

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
