"""SOFA-free regression harness for the capsulorhexis simulator.

Runs three families of checks so that incremental refactors can be verified
without a SOFA runtime:

1. Mesh integrity  - every generated mesh has valid, in-range triangle indices,
                     no degenerate (repeated-index) faces, and finite vertices.
2. Numeric golden  - a stable checksum over vertex positions, so a change that
                     is meant to be behaviour-preserving can be proven so.
3. Controller math - the pure pose/grip/tear helpers.

Usage:
    python3 test_harness.py            # run checks, fail loudly on regressions
    python3 test_harness.py --update   # rewrite the golden baseline file
"""

import argparse
import hashlib
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from capsulorhexis_modules import geometry as G
from capsulorhexis_modules import math_utils as M
from capsulorhexis_modules import png_utils as P
from capsulorhexis_modules.controller import CapsulorhexisController as C

BASELINE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "baseline.json")
SEG = 64  # fixed segment count for reproducible, fast meshes


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _checksum(positions):
    """Stable checksum of a vertex list, robust to tiny float noise."""
    hasher = hashlib.sha256()
    for point in positions:
        for value in point:
            hasher.update(f"{value:.5f}".encode())
    return hasher.hexdigest()[:16]


def _check_mesh(name, positions, triangles, errors):
    n = len(positions)
    if n == 0:
        errors.append(f"{name}: no vertices")
        return
    for point in positions:
        if len(point) != 3 or not all(math.isfinite(c) for c in point):
            errors.append(f"{name}: bad vertex {point}")
            break
    bad_index = degenerate = 0
    for tri in triangles:
        if len(tri) != 3:
            errors.append(f"{name}: face with {len(tri)} indices")
            break
        if any(idx < 0 or idx >= n for idx in tri):
            bad_index += 1
        if len(set(tri)) != 3:
            degenerate += 1
    if bad_index:
        errors.append(f"{name}: {bad_index} out-of-range face(s)")
    if degenerate:
        errors.append(f"{name}: {degenerate} degenerate face(s)")


def _check_curve(name, positions, edges, errors):
    n = len(positions)
    if n == 0:
        errors.append(f"{name}: no vertices")
        return
    for edge in edges:
        if len(edge) != 2 or any(idx < 0 or idx >= n for idx in edge):
            errors.append(f"{name}: bad edge {edge}")
            break


# --------------------------------------------------------------------------- #
# mesh suite - (name, callable) -> (positions, triangles[, boundary])
# --------------------------------------------------------------------------- #
def _surface_meshes():
    s = SEG
    return {
        "annulus": G.generate_annulus(2.0, 5.0, 4, s),
        "disk": G.generate_disk(5.0, 5, s),
        "domed_disk": G.generate_domed_disk(4.0, 8, s),
        "sclera": G.generate_sclera(5.0, 11.0, 6, s),
        "iris": G.generate_iris(1.75, 6.0, 6, s),
        "capsule_annulus": G.generate_capsule_annulus(2.6, 5.0, 6, s),
        "capsule_annulus_center": G.generate_capsule_annulus(0.0, 5.0, 4, s),
        "flap_disk": G.generate_flap_disk(2.6, 6, s),
        "cornea": G.generate_cornea(8.0, 10, s),
        "cornea_shell": G.generate_cornea_shell(rings=8, segments=s),
        "anterior_chamber": G.generate_anterior_chamber_surface(rings=8, segments=s),
        "iris_sheet": G.generate_iris_sheet(1.75, 6.0, rings=6, segments=s),
        "sclera_shell": G.generate_sclera_shell(rings=8, segments=s),
        "ciliary_body": G.generate_ciliary_body(rings=4, segments=s),
        "ciliary_processes": G.generate_ciliary_processes(count=24),
        "lens_shell": G.generate_lens_shell(rings=10, segments=s),
        "vessel_ribbons": G.generate_vessel_ribbons(6.0, 11.0, branches=24),
        "forceps": G.generate_forceps(),
    }


def _curve_meshes():
    s = SEG
    return {
        "curve": G.generate_curve(2.6, s),
        "scleral_vessels": G.generate_scleral_vessels(6.0, 11.0, branches=24),
        "radial_strokes": G.generate_radial_strokes(2.0, 6.0, 60),
        "zonule_fibers": G.generate_zonule_fibers(count=48),
        "vitreous_outline": G.generate_vitreous_cavity_outline(segments=48),
        "ellipse_curve": G.generate_ellipse_curve(5.85, 5.3, s),
    }


# --------------------------------------------------------------------------- #
# controller math
# --------------------------------------------------------------------------- #
def _controller_math():
    base = [[-9.0, 0.2, 0.2], [-0.16, 0.0, 0.2], [-4.0, -0.3, 0.25]]
    settings = {}
    tip = C._estimate_tool_tip_reference(base, settings)
    posed = C.pose_tool_positions(
        base,
        target=[2.0, -2.0, 2.1],
        trocar_point=[5.0, -5.0, 6.0],
        tool_tip=tip,
        tool_roll=0.3,
        tool_grip=0.5,
        grip_start_x=-1.6,
        grip_end_x=-0.16,
    )
    grip = C._gripped_y_for_pose(-0.16, 1.0, 0.8, -1.6, -0.16)

    # tear-path helpers operate on instance attributes; build a bare instance.
    inst = object.__new__(C)
    inst.profile = {"simulation": {"tear_start_angle_degrees": -105.0, "tear_direction": 1.0}}
    inst._tear_edge_offsets = [0.1 * math.sin(i) for i in range(16)]
    inst._tear_edge_stress = [0.05 * i for i in range(16)]
    fracs = [inst._angle_fraction(a) for a in (0.0, 1.0, -1.0, 3.0)]
    deltas = [inst._signed_progress_delta(t, 0.5) for t in (0.1, 0.6, 0.95)]
    offset = inst._tear_offset_at_fraction(0.37)

    return {
        "tip": [round(v, 6) for v in tip],
        "posed_checksum": _checksum(posed),
        "grip": round(grip, 6),
        "fracs": [round(v, 6) for v in fracs],
        "deltas": [round(v, 6) for v in deltas],
        "offset": round(offset, 6),
    }


def _png_roundtrip(errors):
    path = "/tmp/_harness_test.png"
    P.write_png(path, 8, 8, lambda u, v: (u, v, 0.5, 1.0), channels=4)
    img = P.read_png_rgba(path)
    if img["width"] != 8 or img["height"] != 8:
        errors.append(f"png: size {img['width']}x{img['height']}")
    sample = P.sample_png(img, 7.0, 0.0)  # u=1,v=0 -> r~=1,g~=0
    if not (sample[0] > 0.9 and sample[1] < 0.1):
        errors.append(f"png: corner sample {sample}")
    os.remove(path)


# --------------------------------------------------------------------------- #
# run
# --------------------------------------------------------------------------- #
def collect():
    errors = []
    snapshot = {"surfaces": {}, "curves": {}}

    for name, result in _surface_meshes().items():
        positions, triangles = result[0], result[1]
        _check_mesh(name, positions, triangles, errors)
        snapshot["surfaces"][name] = {
            "verts": len(positions),
            "tris": len(triangles),
            "checksum": _checksum(positions),
        }

    for name, (positions, edges) in _curve_meshes().items():
        _check_curve(name, positions, edges, errors)
        snapshot["curves"][name] = {
            "verts": len(positions),
            "edges": len(edges),
            "checksum": _checksum(positions),
        }

    _png_roundtrip(errors)
    snapshot["controller_math"] = _controller_math()
    return snapshot, errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--update", action="store_true", help="rewrite golden baseline")
    args = parser.parse_args()

    snapshot, errors = collect()

    total_verts = sum(m["verts"] for m in snapshot["surfaces"].values())
    total_tris = sum(m["tris"] for m in snapshot["surfaces"].values())
    print(f"meshes: {len(snapshot['surfaces'])} surfaces, {len(snapshot['curves'])} curves")
    print(f"totals: {total_verts} surface vertices, {total_tris} surface triangles")

    if errors:
        print("\nINTEGRITY ERRORS:")
        for e in errors:
            print("  -", e)

    if args.update:
        with open(BASELINE_PATH, "w") as fh:
            json.dump(snapshot, fh, indent=2, sort_keys=True)
        print(f"\nbaseline written to {BASELINE_PATH}")
        return 0 if not errors else 1

    if not os.path.exists(BASELINE_PATH):
        print("\nno baseline yet; run with --update to create one")
        return 1

    with open(BASELINE_PATH) as fh:
        baseline = json.load(fh)

    diffs = []
    if baseline != snapshot:
        for section in ("surfaces", "curves", "controller_math"):
            b, s = baseline.get(section, {}), snapshot.get(section, {})
            for key in sorted(set(b) | set(s)):
                if b.get(key) != s.get(key):
                    diffs.append(f"{section}/{key}: {b.get(key)} -> {s.get(key)}")

    if diffs:
        print("\nDIFF VS BASELINE:")
        for d in diffs:
            print("  -", d)
    else:
        print("\nOK: matches baseline exactly")

    return 0 if (not errors and not diffs) else 1


if __name__ == "__main__":
    sys.exit(main())
