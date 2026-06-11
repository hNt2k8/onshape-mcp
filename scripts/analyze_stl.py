#!/usr/bin/env python3
"""Thin CLI: uv run --no-editable python scripts/analyze_stl.py <file.stl> [units]"""

import json
import sys

from onshape_mcp.mesh.analyze import analyze

if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: analyze_stl.py <file.stl> [auto|in|mm|m]")
    units = sys.argv[2] if len(sys.argv) > 2 else "auto"
    print(json.dumps(analyze(sys.argv[1], units), indent=2))
