#!/usr/bin/env python3
"""Thin CLI: uv run --no-editable python scripts/compare_stl.py <candidate.stl> <reference.stl> [refUnits]"""

import json
import sys

from onshape_mcp.mesh.compare import compare

if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(
            "usage: compare_stl.py <candidate.stl> <reference.stl> [auto|in|mm|m]"
        )
    ref_units = sys.argv[3] if len(sys.argv) > 3 else "auto"
    print(json.dumps(compare(sys.argv[1], sys.argv[2], ref_units), indent=2))
