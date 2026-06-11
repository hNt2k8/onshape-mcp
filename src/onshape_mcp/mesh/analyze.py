"""STL reverse-engineering: extract rebuild-ready parameters from a mesh.

Everything is offline (zero API calls). Output units are INCHES, rounded for
compactness. The pipeline: unit guess -> watertight/bbox/volume -> symmetry
axis from principal inertia -> rotate axis to +Z -> cross-section loops with
least-squares circle fits -> cylinder clustering across z -> bore/bolt-circle
detection -> flat-face z levels.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import trimesh

IN = 25.4  # mm per inch (trimesh meshes are unitless; we track scale manually)


def detect_units(max_extent: float) -> dict[str, Any]:
    """Heuristic: parts under 10 model-units across are probably inches;
    10..1000 probably millimeters."""
    if max_extent < 10:
        return {"guess": "in", "confidence": "high" if max_extent > 0.1 else "low"}
    if max_extent <= 1000:
        return {"guess": "mm", "confidence": "high" if max_extent >= 20 else "medium"}
    return {"guess": "m", "confidence": "low"}


def _to_inches_scale(units: str) -> float:
    return {"in": 1.0, "mm": 1 / IN, "m": 1000 / IN}[units]


def _principal_axes(mesh: trimesh.Trimesh) -> tuple[np.ndarray, np.ndarray]:
    """(components[3], axes rows[3x3]) — inertia-based when watertight,
    vertex-covariance fallback otherwise."""
    if mesh.is_watertight and mesh.volume > 1e-12:
        return mesh.principal_inertia_components, mesh.principal_inertia_vectors
    centered = mesh.vertices - mesh.vertices.mean(axis=0)
    eigenvalues, eigenvectors = np.linalg.eigh(centered.T @ centered)
    return eigenvalues, eigenvectors.T


def _symmetry_axis(mesh: trimesh.Trimesh, tolerance: float = 0.02) -> np.ndarray | None:
    """Axisymmetric parts have two (nearly) equal principal moments; the
    symmetry axis is the eigenvector of the odd one out."""
    components, axes = _principal_axes(mesh)
    for odd in range(3):
        i, j = [k for k in range(3) if k != odd]
        pair_mean = (components[i] + components[j]) / 2
        if pair_mean > 0 and abs(components[i] - components[j]) / pair_mean < tolerance:
            return axes[odd]
    return None


def _fit_circle(points_2d: np.ndarray) -> tuple[float, float, float, float]:
    """Least-squares (Kasa) circle fit -> (cx, cy, r, rms)."""
    x, y = points_2d[:, 0], points_2d[:, 1]
    a_matrix = np.column_stack([2 * x, 2 * y, np.ones(len(x))])
    b_vector = x**2 + y**2
    (cx, cy, c), *_ = np.linalg.lstsq(a_matrix, b_vector, rcond=None)
    radius = math.sqrt(max(c + cx**2 + cy**2, 0.0))
    rms = float(np.std(np.hypot(x - cx, y - cy) - radius))
    return float(cx), float(cy), radius, rms


def _section_loops(
    mesh: trimesh.Trimesh, z: float, max_loops: int = 6
) -> list[dict[str, Any]]:
    section = mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
    if section is None:
        return []
    loops = []
    for polyline in section.discrete[:max_loops]:
        points = np.asarray(polyline)[:, :2]
        if len(points) < 8:
            continue
        cx, cy, radius, rms = _fit_circle(points)
        # circle if the fit residual is tiny vs the radius (and absolutely)
        if radius > 0 and rms < max(0.01 * radius, 0.002):
            loops.append(
                {
                    "type": "circle",
                    "center": [round(cx, 4), round(cy, 4)],
                    "radius": round(radius, 4),
                    "fit_rms": round(rms, 5),
                }
            )
        else:
            mins, maxs = points.min(axis=0), points.max(axis=0)
            loops.append(
                {
                    "type": "other",
                    "bbox": [round(float(v), 4) for v in (*mins, *maxs)],
                    "points": int(len(points)),
                }
            )
    return loops


def _cluster_cylinders(
    levels: list[dict[str, Any]],
    center_tol: float = 0.02,
    radius_tol: float = 0.03,
) -> list[dict[str, Any]]:
    """Group same-center same-radius circles across adjacent z levels."""
    clusters: list[dict[str, Any]] = []
    for level in levels:
        for loop in level["loops"]:
            if loop["type"] != "circle":
                continue
            for cluster in clusters:
                if (
                    math.dist(cluster["center"], loop["center"]) < center_tol
                    and abs(cluster["radius"] - loop["radius"])
                    < radius_tol * max(cluster["radius"], 0.05)
                ):
                    cluster["z_max"] = max(cluster["z_max"], level["z"])
                    cluster["z_min"] = min(cluster["z_min"], level["z"])
                    cluster["hits"] += 1
                    break
            else:
                clusters.append(
                    {
                        "center": list(loop["center"]),
                        "radius": loop["radius"],
                        "z_min": level["z"],
                        "z_max": level["z"],
                        "hits": 1,
                    }
                )
    return [c for c in clusters if c["hits"] >= 2]


def _dominant_axis_center(
    cylinders: list[dict[str, Any]],
) -> list[float] | None:
    """The x/y center most cylinders share (weighted by z extent) — the part's
    cylindrical axis, which need NOT be the mesh origin."""
    if not cylinders:
        return None
    best, best_weight = None, 0.0
    for candidate in cylinders:
        weight = sum(
            (c["z_max"] - c["z_min"]) + 0.01
            for c in cylinders
            if math.dist(c["center"], candidate["center"]) < 0.02
        )
        if weight > best_weight:
            best, best_weight = candidate["center"], weight
    return [round(v, 4) for v in best] if best else None


def _bolt_circles(
    cylinders: list[dict[str, Any]], centers: list[list[float]]
) -> list[dict[str, Any]]:
    """Equal-radius small cylinders at a common distance from any plausible
    center -> bolt circle (or arc). Reports hole positions for rebuilds."""
    results = []
    seen_groups: set[tuple] = set()
    for center in centers:
        off_axis = [
            c
            for c in cylinders
            if math.dist(c["center"], center) > 0.05 and c["radius"] < 1.0
        ]
        groups: list[list[dict[str, Any]]] = []
        for cylinder in off_axis:
            for group in groups:
                sample = group[0]
                same_radius = abs(cylinder["radius"] - sample["radius"]) < 0.1 * max(
                    sample["radius"], 0.02
                )
                same_distance = abs(
                    math.dist(cylinder["center"], center)
                    - math.dist(sample["center"], center)
                ) < 0.1 * max(math.dist(sample["center"], center), 0.02)
                if same_radius and same_distance:
                    group.append(cylinder)
                    break
            else:
                groups.append([cylinder])

        for group in groups:
            if len(group) < 3:
                continue
            key = tuple(
                sorted((round(c["center"][0], 3), round(c["center"][1], 3)) for c in group)
            )
            if key in seen_groups:
                continue
            seen_groups.add(key)
            angles = sorted(
                math.degrees(
                    math.atan2(c["center"][1] - center[1], c["center"][0] - center[0])
                )
                % 360
                for c in group
            )
            spacings = sorted(
                (angles[(i + 1) % len(angles)] - angles[i]) % 360
                for i in range(len(angles))
            )
            # regular if all gaps except possibly the closing one are equal
            common = spacings[len(spacings) // 2 - 1] if len(spacings) > 1 else spacings[0]
            regular = all(abs(s - common) < 5 for s in spacings[:-1])
            full_circle = abs(spacings[-1] - common) < 5
            results.append(
                {
                    "count": len(group),
                    "hole_radius": round(sum(c["radius"] for c in group) / len(group), 4),
                    "circle_center": [round(v, 4) for v in center],
                    "circle_radius": round(
                        sum(math.dist(c["center"], center) for c in group) / len(group), 4
                    ),
                    "regular_spacing": bool(regular),
                    "full_circle": bool(regular and full_circle),
                    "spacing_deg": round(common, 1),
                    "hole_centers": [
                        [round(v, 4) for v in c["center"]] for c in group
                    ],
                }
            )
    return results


def _flat_z_levels(
    mesh: trimesh.Trimesh, min_area_fraction: float = 0.008
) -> list[dict[str, Any]]:
    """z positions of large flat horizontal faces — direct rebuild targets."""
    normals = mesh.face_normals
    areas = mesh.area_faces
    horizontal = np.abs(normals[:, 2]) > 0.99
    if not horizontal.any():
        return []
    z_values = mesh.triangles_center[horizontal][:, 2]
    flat_areas = areas[horizontal]
    order = np.argsort(z_values)
    z_sorted, area_sorted = z_values[order], flat_areas[order]
    levels = []
    cluster_start = 0
    for i in range(1, len(z_sorted) + 1):
        if i == len(z_sorted) or z_sorted[i] - z_sorted[i - 1] > 0.01:
            total = float(area_sorted[cluster_start:i].sum())
            if total > min_area_fraction * mesh.area:
                z_mean = float(
                    np.average(z_sorted[cluster_start:i], weights=area_sorted[cluster_start:i])
                )
                levels.append({"z": round(z_mean, 4), "area_in2": round(total, 3)})
            cluster_start = i
    return levels


def analyze(
    file_path: str, units: str = "auto", z_levels: int = 12
) -> dict[str, Any]:
    mesh = trimesh.load(file_path, force="mesh")
    raw_extent = float(mesh.extents.max())
    unit_info = detect_units(raw_extent)
    used_units = unit_info["guess"] if units == "auto" else units
    mesh.apply_scale(_to_inches_scale(used_units))

    result: dict[str, Any] = {
        "filePath": file_path,
        "units": {
            "used": used_units,
            "detected": unit_info,
            "note": "all output dimensions in inches",
        },
        "watertight": bool(mesh.is_watertight),
        "triangles": int(len(mesh.faces)),
        "bbox_in": [round(v, 4) for v in mesh.extents],
        "volume_in3": round(float(mesh.volume), 4) if mesh.is_watertight else None,
        "surface_area_in2": round(float(mesh.area), 3),
    }

    axis = _symmetry_axis(mesh)
    result["axisymmetric"] = axis is not None
    if axis is not None:
        rotation = trimesh.geometry.align_vectors(axis, [0, 0, 1])
        mesh.apply_transform(rotation)
        # center x/y on the symmetry axis (centroid), keep z absolute
        centroid = mesh.centroid
        mesh.apply_translation([-centroid[0], -centroid[1], 0])
        result["note"] = "mesh rotated so symmetry axis = +Z, centered in x/y"

    z_min, z_max = float(mesh.bounds[0][2]), float(mesh.bounds[1][2])
    result["z_range_in"] = [round(z_min, 4), round(z_max, 4)]

    epsilon = (z_max - z_min) * 0.01
    levels = []
    for z in np.linspace(z_min + epsilon, z_max - epsilon, z_levels):
        loops = _section_loops(mesh, float(z))
        if loops:
            levels.append({"z": round(float(z), 4), "loops": loops})
    result["sections"] = levels

    cylinders = _cluster_cylinders(levels)
    axis_center = _dominant_axis_center(cylinders)
    result["cylinder_axis_center"] = axis_center
    near_axis = (
        [c for c in cylinders if math.dist(c["center"], axis_center) <= 0.05]
        if axis_center
        else []
    )
    outer = max(near_axis, key=lambda c: c["radius"], default=None)
    result["cylinders"] = [
        {
            "center": [round(v, 4) for v in c["center"]],
            "radius": c["radius"],
            "z_range": [round(c["z_min"], 4), round(c["z_max"], 4)],
        }
        for c in sorted(cylinders, key=lambda c: -c["radius"])[:10]
    ]
    if outer is not None:
        result["outer_diameter_in"] = round(2 * outer["radius"], 4)
        result["bores"] = [
            {
                "radius": c["radius"],
                "z_range": [round(c["z_min"], 4), round(c["z_max"], 4)],
            }
            for c in near_axis
            if c is not outer
        ]
    bolt_centers: list[list[float]] = [[0.0, 0.0]]
    if axis_center and math.hypot(*axis_center) > 0.02:
        bolt_centers.append(axis_center)
    result["bolt_circles"] = _bolt_circles(cylinders, bolt_centers)
    result["flat_z_levels_in"] = _flat_z_levels(mesh)
    return result
