"""MCP tools: CAD file import."""

from __future__ import annotations

from typing import Any, Callable

from mcp.server.fastmcp import FastMCP

from ..api import imports as api
from ..client import OnshapeClient


def register(mcp: FastMCP, get_client: Callable[[], OnshapeClient]) -> None:
    @mcp.tool()
    def import_cad(
        documentId: str,
        workspaceId: str,
        filePath: str,
        translate: bool = True,
        allowFaultyParts: bool = True,
        splitAssembliesIntoMultipleDocuments: bool = False,
        flattenAssemblies: bool = False,
        notifyUser: bool = False,
    ) -> dict[str, Any]:
        """Upload a local CAD file into an existing document workspace and
        translate it to OnShape format. Use for foreign formats such as a .zip
        of an Autodesk Inventor assembly, STEP, IGES, SOLIDWORKS, etc.

        filePath must be an ABSOLUTE path. This uses OnShape's async
        translation API and costs several quota calls (upload + polls), so
        expect it to take a while for large assemblies. Returns the created
        blob elementId, the translationId, the final translationState, and
        resultElementIds (the elements the translation produced)."""
        return api.import_cad(
            get_client(),
            documentId,
            workspaceId,
            filePath,
            translate=translate,
            allow_faulty_parts=allowFaultyParts,
            split_assemblies_into_multiple_documents=(
                splitAssembliesIntoMultipleDocuments
            ),
            flatten_assemblies=flattenAssemblies,
            notify_user=notifyUser,
        )
