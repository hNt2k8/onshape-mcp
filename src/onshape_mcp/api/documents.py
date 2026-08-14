"""Document and element endpoints. All returns are compact dicts."""

from __future__ import annotations

from typing import Any

from ..client import OnshapeClient


def list_documents(
    client: OnshapeClient, query: str | None = None, limit: int = 10
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"limit": limit}
    if query:
        params["q"] = query
    data = client.request_json("GET", "/documents", params=params)
    return [
        {
            "documentId": d["id"],
            "name": d["name"],
            "defaultWorkspaceId": (d.get("defaultWorkspace") or {}).get("id"),
        }
        for d in data.get("items", [])
    ]


def create_document(
    client: OnshapeClient,
    name: str,
    description: str | None = None,
    parent_id: str | None = None,
) -> dict[str, Any]:
    """Create a private document. parent_id is an OnShape FOLDER id; when set,
    the document is created inside that folder instead of at the root."""
    body: dict[str, Any] = {"name": name, "isPublic": False}
    if description:
        body["description"] = description
    if parent_id:
        body["parentId"] = parent_id
    doc = client.request_json("POST", "/documents", json_body=body)
    document_id = doc["id"]
    workspace_id = doc["defaultWorkspace"]["id"]
    # Resolve the default Part Studio right away so modeling can start
    # without an extra round trip later.
    part_studio_id = None
    for element in list_elements(client, document_id, workspace_id):
        if element["elementType"] == "PARTSTUDIO":
            part_studio_id = element["elementId"]
            break
    return {
        "documentId": document_id,
        "workspaceId": workspace_id,
        "partStudioElementId": part_studio_id,
        "name": doc["name"],
    }


def list_elements(
    client: OnshapeClient, document_id: str, workspace_id: str
) -> list[dict[str, Any]]:
    data = client.request_json(
        "GET", f"/documents/d/{document_id}/w/{workspace_id}/elements"
    )
    return [
        {"elementId": e["id"], "name": e["name"], "elementType": e["elementType"]}
        for e in data
    ]


def create_part_studio(
    client: OnshapeClient, document_id: str, workspace_id: str, name: str
) -> dict[str, Any]:
    data = client.request_json(
        "POST",
        f"/partstudios/d/{document_id}/w/{workspace_id}",
        json_body={"name": name},
    )
    return {"elementId": data["id"], "name": data["name"]}
