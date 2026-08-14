"""CAD file import (upload + translate) into an existing document workspace.

POST /blobelements/d/{did}/w/{wid} (uploadFileCreateElement) takes a
multipart/form-data body: the raw file plus form fields. All booleans go on
the wire as the strings "true"/"false".

With translate=true the response carries a `translationId`; the translation
runs asynchronously, so this mirrors the submit -> poll pattern used by the
STEP export in export.py. Every poll is a quota call, so the interval is
deliberately loose (seconds, not a tight loop).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ..client import OnshapeApiError, OnshapeClient

TRANSLATION_POLL_INTERVAL_S = 3.0
TRANSLATION_TIMEOUT_S = 900.0  # assembly imports are slower than a STEP export


def _form_bool(value: bool) -> str:
    return "true" if value else "false"


def import_cad(
    client: OnshapeClient,
    document_id: str,
    workspace_id: str,
    file_path: str,
    translate: bool = True,
    allow_faulty_parts: bool = True,
    split_assemblies_into_multiple_documents: bool = False,
    flatten_assemblies: bool = False,
    notify_user: bool = False,
    import_within_document: bool = True,
    store_in_document: bool = True,
    y_axis_is_up: bool = False,
    wait: bool = True,
    poll_interval_s: float = TRANSLATION_POLL_INTERVAL_S,
    timeout_s: float = TRANSLATION_TIMEOUT_S,
) -> dict[str, Any]:
    """Upload a local CAD file (e.g. a .zip of an Inventor assembly) into an
    existing document workspace and translate it to OnShape format.

    file_path must be ABSOLUTE (the server's cwd is not the project's).
    Returns the created blob element id, the translation id/state and — once
    DONE — the element ids the translation produced.
    """
    source = Path(file_path)
    if not source.is_absolute():
        raise OnshapeApiError(
            f"file_path must be ABSOLUTE (server cwd != project cwd): {file_path}"
        )
    if not source.is_file():
        raise OnshapeApiError(f"file not found: {file_path}")

    filename = source.name
    # Read into memory: a 429 retry rebuilds the request, and a consumed file
    # handle would then upload an empty body.
    payload = source.read_bytes()

    form: dict[str, Any] = {
        "encodedFilename": filename,
        "translate": _form_bool(translate),
        "allowFaultyParts": _form_bool(allow_faulty_parts),
        "splitAssembliesIntoMultipleDocuments": _form_bool(
            split_assemblies_into_multiple_documents
        ),
        "flattenAssemblies": _form_bool(flatten_assemblies),
        "notifyUser": _form_bool(notify_user),
        "importWithinDocument": _form_bool(import_within_document),
        "storeInDocument": _form_bool(store_in_document),
        "yAxisIsUp": _form_bool(y_axis_is_up),
    }

    info = client.request_json(
        "POST",
        f"/blobelements/d/{document_id}/w/{workspace_id}",
        files={"file": (filename, payload, "application/octet-stream")},
        data=form,
    )

    result: dict[str, Any] = {
        "elementId": info.get("id"),
        "name": info.get("name") or info.get("filename") or filename,
        "documentId": document_id,
        "workspaceId": workspace_id,
        "translationId": info.get("translationId"),
        "translationState": None,
        "resultElementIds": [],
    }

    translation_id = result["translationId"]
    if not translate or not translation_id or not wait:
        return result

    status = poll_translation(
        client, translation_id, poll_interval_s=poll_interval_s, timeout_s=timeout_s
    )
    result["translationState"] = status.get("requestState")
    result["resultElementIds"] = status.get("resultElementIds") or []
    if status.get("resultDocumentId"):
        result["resultDocumentId"] = status["resultDocumentId"]
    if status.get("resultWorkspaceId"):
        result["resultWorkspaceId"] = status["resultWorkspaceId"]
    return result


def poll_translation(
    client: OnshapeClient,
    translation_id: str,
    poll_interval_s: float = TRANSLATION_POLL_INTERVAL_S,
    timeout_s: float = TRANSLATION_TIMEOUT_S,
) -> dict[str, Any]:
    """Poll GET /translations/{tid} until DONE; raise on FAILED or timeout.

    requestState goes ACTIVE -> DONE (or FAILED). Same shape as the STEP-export
    poll loop, on a wall-clock deadline.
    """
    deadline = time.monotonic() + timeout_s
    while True:
        status = client.request_json("GET", f"/translations/{translation_id}")
        state = status.get("requestState")
        if state == "DONE":
            return status
        if state == "FAILED":
            raise OnshapeApiError(
                f"translation {translation_id} FAILED: {status.get('failureReason')}"
            )
        if time.monotonic() > deadline:
            raise OnshapeApiError(
                f"translation {translation_id} still {state} after {timeout_s:.0f}s"
            )
        time.sleep(poll_interval_s)
