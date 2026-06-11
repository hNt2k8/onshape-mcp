"""Export and measurement endpoints.

STL export: the sync endpoint returns 307 to a DIFFERENT host. API-key
signatures cover path+query, so the redirect must be followed with a FRESH
signed request for the Location URL — never with the original auth header
(that yields 401). The client never auto-follows redirects for this reason.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..client import OnshapeApiError, OnshapeClient
from ..units import EXPORT_UNIT, UNIT_TO_METERS, check_units

# Fine tessellation defaults (~OnShape "fine": chord ≈ 0.06 mm on inch export).
# Coarse tessellation alone can eat a 0.01" verification budget on a Ø3.5"
# cylinder, so exports always request fine quality unless overridden.
DEFAULT_ANGLE_TOLERANCE = 0.04  # radians
DEFAULT_CHORD_TOLERANCE_IN = 0.0024  # inches (≈ 0.06 mm)

MAX_REDIRECTS = 3


def download(client: OnshapeClient, path: str, params: dict[str, Any]) -> bytes:
    """GET with manual re-signed redirect following; returns raw body bytes."""
    response = client.request("GET", path, params=params, headers={"Accept": "*/*"})
    redirects = 0
    while response.status_code in (301, 302, 307, 308):
        if redirects >= MAX_REDIRECTS:
            raise OnshapeApiError(f"too many redirects for {path}")
        location = response.headers.get("Location")
        if not location:
            raise OnshapeApiError(f"redirect without Location for {path}")
        redirects += 1
        # Full URL passthrough -> client builds a fresh signature for the new
        # host/path/query.
        response = client.request("GET", location, headers={"Accept": "*/*"})
    if response.status_code >= 400:
        raise OnshapeApiError(
            f"GET {path} -> HTTP {response.status_code}",
            status=response.status_code,
            body=response.text,
        )
    return response.content


def export_stl(
    client: OnshapeClient,
    document_id: str,
    workspace_id: str,
    element_id: str,
    file_path: str,
    units: str = "in",
    part_ids: list[str] | None = None,
    angle_tolerance: float = DEFAULT_ANGLE_TOLERANCE,
    chord_tolerance: float | None = None,
) -> dict[str, Any]:
    """Export a Part Studio (or selected parts) as binary STL to file_path
    (ABSOLUTE path). chord_tolerance is in `units` (default ≈ 0.06 mm)."""
    check_units(units)
    if chord_tolerance is None:
        chord_tolerance = DEFAULT_CHORD_TOLERANCE_IN * 0.0254 / UNIT_TO_METERS[units]
    params: dict[str, Any] = {
        "mode": "binary",
        "units": EXPORT_UNIT[units],
        "scale": 1,
        "angleTolerance": angle_tolerance,
        "chordTolerance": chord_tolerance,
    }
    if part_ids:
        params["partIds"] = ",".join(part_ids)
    data = download(
        client,
        f"/partstudios/d/{document_id}/w/{workspace_id}/e/{element_id}/stl",
        params,
    )
    target = Path(file_path)
    if not target.is_absolute():
        raise OnshapeApiError(
            f"file_path must be ABSOLUTE (server cwd != project cwd): {file_path}"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return {"filePath": str(target), "bytes": len(data), "units": units}


def mass_properties(
    client: OnshapeClient,
    document_id: str,
    workspace_id: str,
    element_id: str,
    part_id: str | None = None,
) -> dict[str, Any]:
    """Volume/centroid/bbox per part. OnShape returns SI (m^3, m); inches are
    derived for convenience. Parts without assigned material have no mass."""
    params = {"partId": part_id} if part_id else None
    data = client.request_json(
        "GET",
        f"/partstudios/d/{document_id}/w/{workspace_id}/e/{element_id}/massproperties",
        params=params,
    )
    in3 = 0.0254**3
    results = {}
    for body_id, body in (data.get("bodies") or {}).items():
        volume = (body.get("volume") or [None])[0]
        centroid = (body.get("centroid") or [])[:3]
        results[body_id] = {
            "volume_m3": volume,
            "volume_in3": round(volume / in3, 6) if volume is not None else None,
            "centroid_m": centroid,
            "hasMass": body.get("hasMass"),
        }
    return results


def list_parts(
    client: OnshapeClient,
    document_id: str,
    workspace_id: str,
    element_id: str,
) -> list[dict[str, Any]]:
    data = client.request_json(
        "GET", f"/parts/d/{document_id}/w/{workspace_id}/e/{element_id}"
    )
    return [
        {
            "partId": p.get("partId"),
            "name": p.get("name"),
            "bodyType": p.get("bodyType"),
        }
        for p in data
    ]
