"""Mesh-vs-mesh verification: robust alignment + two-way surface deviation.

Alignment strategy (this matters: the end cap is near-axisymmetric with a
~180-degree near-symmetry, so naive PCA alignment WILL false-fail): centroid
centering, then a candidate set of rotations — identity, axis flips, and all
proper principal-axes alignments (4 sign combinations) — each quick-scored by
one-way deviation; the winner is refined with ICP against the reference mesh.

Measured deviation = candidate tessellation sag + reference sag + alignment
residual, so exports must use fine tessellation (the export tool defaults do).
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import trimesh

from .analyze import _principal_axes, _to_inches_scale, detect_units

QUICK_SAMPLES = 600
FINAL_SAMPLES = 5000
PASS_P95_IN = 0.01


def _load_in_inches(path: str, units: str) -> trimesh.Trimesh:
    mesh = trimesh.load(path, force="mesh")
    used = detect_units(float(mesh.extents.max()))["guess"] if units == "auto" else units
    mesh.apply_scale(_to_inches_scale(used))
    return mesh


def _deviations(points: np.ndarray, target: trimesh.Trimesh) -> np.ndarray:
    """Exact point-to-surface distances (triangle-accurate)."""
    _, distances, _ = trimesh.proximity.closest_point(target, points)
    return distances


def _candidate_rotations(
    candidate: trimesh.Trimesh, reference: trimesh.Trimesh
) -> list[np.ndarray]:
    rotations = [np.eye(3)]
    # 180-degree flips about each axis (covers same-frame modeling flips)
    for axis in range(3):
        flip = -np.eye(3)
        flip[axis, axis] = 1.0
        rotations.append(flip)
    # principal-axes alignments: R = ref_axes^T @ S @ cand_axes, proper only
    try:
        _, cand_axes = _principal_axes(candidate)
        _, ref_axes = _principal_axes(reference)
        for sx in (1, -1):
            for sy in (1, -1):
                for sz in (1, -1):
                    signs = np.diag([sx, sy, sz])
                    rotation = ref_axes.T @ signs @ cand_axes
                    if np.linalg.det(rotation) > 0:
                        rotations.append(rotation)
    except Exception:
        pass
    return rotations


def compare(
    candidate_path: str,
    reference_path: str,
    reference_units: str = "auto",
    candidate_units: str = "auto",
    samples: int = FINAL_SAMPLES,
) -> dict[str, Any]:
    candidate = _load_in_inches(candidate_path, candidate_units)
    reference = _load_in_inches(reference_path, reference_units)

    result: dict[str, Any] = {
        "volume_ratio": (
            round(float(candidate.volume / reference.volume), 4)
            if candidate.is_watertight and reference.is_watertight
            else None
        ),
        "bbox_ratio": round(
            float(np.mean(np.sort(candidate.extents) / np.sort(reference.extents))), 4
        ),
        "area_ratio": round(float(candidate.area / reference.area), 4),
    }

    # center both at centroid
    candidate.apply_translation(-candidate.centroid)
    reference.apply_translation(-reference.centroid)

    quick_points, _ = trimesh.sample.sample_surface(candidate, QUICK_SAMPLES)
    best_rotation, best_score = None, math.inf
    for rotation in _candidate_rotations(candidate, reference):
        rotated = quick_points @ rotation.T
        score = float(np.percentile(_deviations(rotated, reference), 95))
        if score < best_score:
            best_rotation, best_score = rotation, score

    transform = np.eye(4)
    transform[:3, :3] = best_rotation
    candidate.apply_transform(transform)

    # ICP refinement against the reference mesh
    icp_points, _ = trimesh.sample.sample_surface(candidate, QUICK_SAMPLES * 2)
    try:
        # rigid-only: scaling/reflection would mask real size/mirror errors
        matrix, _, _ = trimesh.registration.icp(
            icp_points, reference, max_iterations=30, scale=False, reflection=False
        )
        candidate.apply_transform(matrix)
    except Exception as error:  # alignment best-effort; metrics still honest
        result["icp_warning"] = str(error)[:200]

    # final two-way deviation
    cand_points, _ = trimesh.sample.sample_surface(candidate, samples)
    ref_points, _ = trimesh.sample.sample_surface(reference, samples)
    cand_to_ref = _deviations(cand_points, reference)
    ref_to_cand = _deviations(ref_points, candidate)
    both = np.concatenate([cand_to_ref, ref_to_cand])

    worst_indices = np.argsort(cand_to_ref)[-3:][::-1]
    result.update(
        {
            "p95_dev_in": round(float(np.percentile(both, 95)), 5),
            "max_dev_in": round(float(both.max()), 5),
            "mean_dev_in": round(float(both.mean()), 5),
            "pass": bool(np.percentile(both, 95) < PASS_P95_IN),
            "worst_locations_in": [
                {
                    "point": [round(v, 3) for v in cand_points[i]],
                    "deviation": round(float(cand_to_ref[i]), 5),
                }
                for i in worst_indices
            ],
            "note": (
                "deviation includes tessellation sag of both meshes plus "
                "alignment residual; worst locations hint at wrong/missing features"
            ),
        }
    )
    return result
