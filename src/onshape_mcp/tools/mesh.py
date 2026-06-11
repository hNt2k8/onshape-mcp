"""MCP tools: offline mesh analysis/verification (zero API calls)."""

from __future__ import annotations

from typing import Any, Callable

from mcp.server.fastmcp import FastMCP

from ..client import OnshapeClient


def register(mcp: FastMCP, get_client: Callable[[], OnshapeClient]) -> None:
    @mcp.tool()
    def analyze_stl(
        filePath: str, units: str = "auto", zLevels: int = 12
    ) -> dict[str, Any]:
        """Reverse-engineer an STL into rebuild-ready parameters: units guess,
        bbox/volume, symmetry axis, cross-section circle fits per z level,
        cylinder/bore clustering, bolt-circle detection, flat z levels.
        All output dimensions in INCHES. filePath must be ABSOLUTE.
        units: auto|in|mm|m (override the heuristic if you know the source).
        Costs zero API calls."""
        from ..mesh.analyze import analyze

        return analyze(filePath, units, zLevels)

    @mcp.tool()
    def compare_stl(
        candidatePath: str,
        referencePath: str,
        referenceUnits: str = "auto",
        candidateUnits: str = "auto",
    ) -> dict[str, Any]:
        """Verify a rebuilt part against a reference mesh: robust alignment
        (flip candidates + ICP — handles near-symmetric parts), then volume/
        bbox/area ratios and two-way sampled surface deviation.
        pass = p95 deviation < 0.01 in. Worst-deviation locations hint at
        wrong or missing features. Absolute paths. Zero API calls."""
        from ..mesh.compare import compare

        return compare(candidatePath, referencePath, referenceUnits, candidateUnits)
