"""Check that no headland loop drives through an obstacle or leaves the field.

This was a real defect worth a permanent check.  ``Plan`` used to expose the
headland as one flat point list, and two things went wrong with it:

* any consumer that treated the list as a polyline -- the viewer, and
  ``metrics.evaluate`` -- welded the loops together with straight segments the
  machine never drives.  On a field with sixteen obstacles those phantom joins
  ran to 343 m, straight through the obstacles they connected;
* a loop around one obstacle was built from that obstacle alone, so a neighbour
  inside its offset was driven through.  ``field_headland`` had the same problem
  with obstacles near the field edge.

Both are fixed by keeping the loops separate and cutting each to the region it
may occupy.  This tool asserts the result, on synthetic shapes and on real
fields, and reports the length that used to be spent inside obstacles.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".cache" / "matplotlib"))
sys.path.insert(0, str(ROOT / "src"))

from shapely.geometry import LineString  # noqa: E402

from cppclip import geometry as G  # noqa: E402
from cppclip.fields import make_field  # noqa: E402
from cppclip.planner import PlanParams, plan  # noqa: E402

TOL = 0.01  # metres; below this is float noise from the boolean ops


def audit(field, params) -> tuple[float, float, float]:  # noqa: ANN001
    """Return (total headland length, length inside obstacles, length outside field)."""
    p = plan(field, params)
    if not p.headland_loops:
        return 0.0, 0.0, 0.0

    obstacles = G.normalise(G.unary_union(field.obstacles)) if field.obstacles else None
    total = 0.0
    inside = 0.0
    outside = 0.0
    for loop in p.headland_loops:
        if len(loop) < 2:
            continue
        line = LineString(loop)
        total += float(line.length)
        if obstacles is not None and not obstacles.is_empty:
            inter = line.intersection(obstacles)
            if not inter.is_empty:
                inside += float(inter.length)
        out = line.difference(field.boundary.buffer(1e-9))
        if not out.is_empty:
            outside += float(out.length)
    return total, inside, outside


def main() -> None:
    params = PlanParams(swath_width=6.0, headland_width=6.0, n_angle_candidates=8)
    print("Headland loops must stay in free space and inside the field\n")
    bad = 0
    total_len = 0.0
    total_inside = 0.0

    print("synthetic fields:")
    for kind in ("rect", "l", "u", "star", "rectilinear"):
        for n in (0, 3, 8, 16, 24):
            field = make_field(kind, seed=4, n_obstacles=n, target_area=25_000.0)
            length, inside, outside = audit(field, params)
            total_len += length
            total_inside += inside
            flag = ""
            if inside > TOL or outside > TOL:
                flag = "   <-- FAILS"
                bad += 1
            print(f"  {kind:<12} obstacles {n:2d}  headland {length:8.1f} m  "
                  f"inside obstacles {inside:7.3f} m  outside field {outside:7.3f} m{flag}")

    print("\nreal fields (with synthetic obstacles injected):")
    from cppclip.io_fields import load_benchmark

    fields = load_benchmark(limit=60, with_obstacles=4, obstacle_seed=3)
    worst = 0.0
    for field in fields:
        length, inside, outside = audit(field, params)
        total_len += length
        total_inside += inside
        worst = max(worst, inside)
        if inside > TOL or outside > TOL:
            bad += 1
            print(f"  {field.name:<20} inside {inside:7.3f} m  outside {outside:7.3f} m  <-- FAILS")

    print(f"\n  audited {len(fields)} real fields, worst crossing {worst:.4f} m")
    print(f"\ntotal headland driven {total_len:,.0f} m, of which {total_inside:.4f} m "
          f"inside an obstacle")
    print("PASS" if bad == 0 else f"FAIL: {bad} field(s) still drive through an obstacle")


if __name__ == "__main__":
    main()
