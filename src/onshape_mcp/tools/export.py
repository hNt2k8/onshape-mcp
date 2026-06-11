"""MCP tools: export and measurement."""

from __future__ import annotations

from typing import Any, Callable

from mcp.server.fastmcp import FastMCP

from ..api import export as api
from ..client import OnshapeClient


def register(mcp: FastMCP, get_client: Callable[[], OnshapeClient]) -> None:
    @mcp.tool()
    def export_stl(
        documentId: str,
        workspaceId: str,
        elementId: str,
        filePath: str,
        units: str = "in",
        partIds: list[str] | None = None,
        angleTolerance: float = api.DEFAULT_ANGLE_TOLERANCE,
        chordTolerance: float = 0,
    ) -> dict[str, Any]:
        """Export a Part Studio (or selected partIds) as binary STL.
        filePath must be an ABSOLUTE path. Defaults to fine tessellation
        (angle 0.04 rad, chord ≈ 0.06 mm) so mesh verification isn't limited
        by export quality. chordTolerance is in `units`; 0 = default."""
        return api.export_stl(
            get_client(),
            documentId,
            workspaceId,
            elementId,
            filePath,
            units,
            partIds,
            angleTolerance,
            chordTolerance or None,
        )

    @mcp.tool()
    def mass_properties(
        documentId: str,
        workspaceId: str,
        elementId: str,
        partId: str = "",
    ) -> dict[str, Any]:
        """Volume (m^3 and in^3), centroid, per part. Use to sanity-check
        geometry after modeling operations."""
        return api.mass_properties(
            get_client(), documentId, workspaceId, elementId, partId or None
        )

    @mcp.tool()
    def list_parts(
        documentId: str, workspaceId: str, elementId: str
    ) -> list[dict[str, Any]]:
        """List solid parts in a Part Studio (partId, name, bodyType)."""
        return api.list_parts(get_client(), documentId, workspaceId, elementId)
