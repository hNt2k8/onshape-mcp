"""MCP tools: documents and elements."""

from __future__ import annotations

from typing import Any, Callable

from mcp.server.fastmcp import FastMCP

from ..api import documents as api
from ..client import OnshapeClient


def register(mcp: FastMCP, get_client: Callable[[], OnshapeClient]) -> None:
    @mcp.tool()
    def list_documents(query: str = "", limit: int = 10) -> list[dict[str, Any]]:
        """List OnShape documents this account can access (most recent first).
        Optionally filter by a search query."""
        return api.list_documents(get_client(), query or None, limit)

    @mcp.tool()
    def create_document(
        name: str, description: str = "", parentId: str = ""
    ) -> dict[str, Any]:
        """Create a new private OnShape document. Returns documentId,
        workspaceId, and the default Part Studio's partStudioElementId —
        everything needed to start modeling. parentId is an OnShape FOLDER id;
        pass it to create the document inside that folder."""
        return api.create_document(
            get_client(), name, description or None, parentId or None
        )

    @mcp.tool()
    def list_elements(documentId: str, workspaceId: str) -> list[dict[str, Any]]:
        """List elements (tabs) in a document workspace: Part Studios,
        assemblies, blobs, etc."""
        return api.list_elements(get_client(), documentId, workspaceId)

    @mcp.tool()
    def create_part_studio(
        documentId: str, workspaceId: str, name: str
    ) -> dict[str, Any]:
        """Add a new empty Part Studio tab to a document."""
        return api.create_part_studio(get_client(), documentId, workspaceId, name)
