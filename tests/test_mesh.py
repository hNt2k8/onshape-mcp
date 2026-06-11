"""Offline tests for mesh analysis/comparison on generated primitives."""

import numpy as np
import pytest
import trimesh

from onshape_mcp.mesh.analyze import analyze, detect_units
from onshape_mcp.mesh.compare import compare


def test_detect_units_heuristic():
    assert detect_units(3.5)["guess"] == "in"
    assert detect_units(88.9)["guess"] == "mm"
    assert detect_units(5000)["guess"] == "m"


@pytest.fixture(scope="module")
def annulus_stl(tmp_path_factory):
    """Ø2in disc, Ø0.5in bore, 0.5in tall — in INCH units."""
    mesh = trimesh.creation.annulus(r_min=0.25, r_max=1.0, height=0.5, sections=128)
    path = tmp_path_factory.mktemp("mesh") / "annulus.stl"
    mesh.export(path)
    return str(path)


def test_analyze_annulus(annulus_stl):
    result = analyze(annulus_stl)
    assert result["units"]["used"] == "in"
    assert result["watertight"] is True
    assert result["axisymmetric"] is True
    assert result["outer_diameter_in"] == pytest.approx(2.0, abs=0.01)
    assert result["bores"], "central bore should be detected"
    assert result["bores"][0]["radius"] == pytest.approx(0.25, abs=0.01)
    assert result["volume_in3"] == pytest.approx(
        3.14159 * (1.0**2 - 0.25**2) * 0.5, rel=0.01
    )
    # top and bottom flats
    flat_zs = sorted(level["z"] for level in result["flat_z_levels_in"])
    assert flat_zs == pytest.approx([-0.25, 0.25], abs=0.01)


def test_analyze_mm_scaling(tmp_path):
    mesh = trimesh.creation.cylinder(radius=25.4, height=25.4, sections=96)
    path = tmp_path / "cyl_mm.stl"
    mesh.export(path)
    result = analyze(str(path))
    assert result["units"]["used"] == "mm"
    assert result["outer_diameter_in"] == pytest.approx(2.0, abs=0.02)


def test_bolt_circle_detection(tmp_path):
    disc = trimesh.creation.cylinder(radius=1.5, height=0.25, sections=128)
    holes = [
        trimesh.creation.cylinder(
            radius=0.1,
            height=1.0,
            sections=48,
            transform=trimesh.transformations.translation_matrix(
                [np.cos(a) * 1.0, np.sin(a) * 1.0, 0]
            ),
        )
        for a in np.linspace(0, 2 * np.pi, 4, endpoint=False)
    ]
    mesh = disc.difference(trimesh.util.concatenate(holes))
    path = tmp_path / "bolts.stl"
    mesh.export(path)
    result = analyze(str(path))
    circles = result["bolt_circles"]
    assert circles, "bolt circle should be detected"
    assert circles[0]["count"] == 4
    assert circles[0]["hole_radius"] == pytest.approx(0.1, abs=0.02)
    assert circles[0]["circle_radius"] == pytest.approx(1.0, abs=0.05)
    assert circles[0]["regular_spacing"] is True


def test_compare_identical_passes(annulus_stl):
    result = compare(annulus_stl, annulus_stl, samples=1500)
    assert result["pass"] is True
    assert result["volume_ratio"] == pytest.approx(1.0, abs=0.001)
    assert result["p95_dev_in"] < 0.002


def test_compare_rotated_translated_copy_aligns(annulus_stl, tmp_path):
    mesh = trimesh.load(annulus_stl)
    transform = trimesh.transformations.rotation_matrix(0.6, [1, 1, 0])
    transform[:3, 3] = [3.0, -2.0, 1.0]
    mesh.apply_transform(transform)
    moved = tmp_path / "moved.stl"
    mesh.export(moved)
    result = compare(str(moved), annulus_stl, samples=1500)
    assert result["pass"] is True, result


def test_compare_wrong_size_fails(annulus_stl, tmp_path):
    mesh = trimesh.load(annulus_stl)
    mesh.apply_scale(1.15)
    big = tmp_path / "big.stl"
    mesh.export(big)
    result = compare(str(big), annulus_stl, candidate_units="in", samples=1500)
    assert result["pass"] is False
    assert result["volume_ratio"] > 1.4
