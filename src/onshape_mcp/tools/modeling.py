"""MCP tools: feature access (raw escape hatch + feature listing)."""

from __future__ import annotations

from typing import Any, Callable

from mcp.server.fastmcp import FastMCP

from ..api import partstudio as api
from ..client import OnshapeClient


def register(mcp: FastMCP, get_client: Callable[[], OnshapeClient]) -> None:
    @mcp.tool()
    def get_features(
        documentId: str,
        workspaceId: str,
        elementId: str,
        featureId: str = "",
        verbose: bool = False,
    ) -> list[dict[str, Any]]:
        """List features in a Part Studio with their regen status
        (featureStatus: OK | WARNING | ERROR). verbose=True includes the full
        feature JSON — use it to mirror features built manually in the
        OnShape UI."""
        return api.get_features(
            get_client(),
            documentId,
            workspaceId,
            elementId,
            featureId or None,
            verbose,
        )

    @mcp.tool()
    def add_feature(
        documentId: str,
        workspaceId: str,
        elementId: str,
        feature: dict[str, Any],
    ) -> dict[str, Any]:
        """RAW escape hatch: post one feature definition (BTM JSON) to a Part
        Studio. Accepts a bare feature dict (e.g. BTMSketch-151, BTMFeature-134)
        or a full BTFeatureDefinitionCall-1406 envelope. Sketch coordinates are
        in METERS. Returns {featureId, name, featureStatus}; featureStatus
        ERROR means the feature was added but failed to regenerate."""
        return api.add_feature(
            get_client(), documentId, workspaceId, elementId, feature
        )

    @mcp.tool()
    def update_feature(
        documentId: str,
        workspaceId: str,
        elementId: str,
        featureId: str,
        feature: dict[str, Any],
    ) -> dict[str, Any]:
        """Replace an existing feature's definition (full feature JSON,
        including its featureId)."""
        return api.update_feature(
            get_client(), documentId, workspaceId, elementId, featureId, feature
        )

    @mcp.tool()
    def delete_feature(
        documentId: str, workspaceId: str, elementId: str, featureId: str
    ) -> dict[str, Any]:
        """Delete a feature from a Part Studio."""
        return api.delete_feature(
            get_client(), documentId, workspaceId, elementId, featureId
        )
