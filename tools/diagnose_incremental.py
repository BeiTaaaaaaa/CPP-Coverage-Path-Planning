"""Diagnose a divergence between incremental replanning and a from-scratch build.

The incremental planner is only allowed to re-clip the scanlines an obstacle
touches, and it asserts that this yields bit-identical intervals to rebuilding
the scene (``tests/test_incremental.py``).  When that assertion fires, this tool
shows *why*: for the first mismatching scanline it prints the intervals from both
sides, the crossings behind them, and the active edges, which is usually enough
to tell a missing merge from a stale bucket.

Run:  python tools/diagnose_incremental.py [kind] [seed]
      python tools/diagnose_incremental.py rectilinear 1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cppclip import fields as F  # noqa: E402
from cppclip import geometry as G  # noqa: E402
from cppclip.incremental import IncrementalPlanner  # noqa: E402
from cppclip.planner import PlanParams, inner_region  # noqa: E402
from cppclip.sweep import ScanlineClipper  # noqa: E402


def describe(label: str, clip: ScanlineClipper, i: int, y: float) -> None:
    print(f"    {label} intervals: {[(round(a, 6), round(b, 6)) for a, b in sorted(clip.intervals_at(i))]}")
    print(f"    {label} crossings: {np.round(clip.crossings_at(i), 6).tolist()}")
    for eid in clip._buckets[i]:
        e = clip._edges[eid]
        if not e.dead:
            print(
                f"      src={e.source} ({e.x0:.4f},{e.y0:.4f})->({e.x1:.4f},{e.y1:.4f})"
                f"  x@y={e.x_at(y):.6f}"
            )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", nargs="?", default="rectilinear",
                    help="synthetic field kind: rect, l, u, star, rectilinear")
    ap.add_argument("seed", nargs="?", type=int, default=1)
    ap.add_argument("--obstacles", type=int, default=8)
    args = ap.parse_args()

    base = F.make_field(args.kind, seed=args.seed, n_obstacles=0, target_area=20_000.0)
    params = PlanParams(swath_width=6.0, headland_width=6.0, min_swath_length=1.0,
                        n_angle_candidates=8, angle=0.0)

    # A fixed heading isolates the clipping from the heading search: with both
    # sides planning in the same frame, any difference is a clipping bug.
    planner = IncrementalPlanner(base, params)
    print(f"field {args.kind!r} seed {args.seed}")
    print(f"  boundary bbox  : {tuple(round(v, 3) for v in G.bounds_of(base.boundary))}")
    print(f"  base inner bbox: {tuple(round(v, 3) for v in G.bounds_of(planner._base_inner))}")
    print(f"  scanlines      : {planner.clipper.n_scanlines}   inset {planner.inset} m")

    inner = G.erode(base.boundary, 18.0)
    candidates = F.random_obstacles(inner, args.obstacles, seed=5, size_range=(5.0, 10.0))
    print(f"  obstacles      : {len(candidates)} placed\n")

    known: list = []
    for k, obs in enumerate(candidates):
        planner.add_obstacle(obs)
        known.append(obs)
        inner_geom, _ = inner_region(base.boundary, known, params.headland_width, params.swath_width)
        ref = ScanlineClipper.from_geometry(inner_geom, params.swath_width)

        for i in range(min(planner.clipper.n_scanlines, ref.n_scanlines)):
            got = sorted(planner.clipper.intervals_at(i))
            want = sorted(ref.intervals_at(i))
            same = len(got) == len(want) and all(
                abs(a0 - b0) <= 1e-7 and abs(a1 - b1) <= 1e-7 for (a0, a1), (b0, b1) in zip(got, want)
            )
            if not same:
                y = float(planner.clipper.ys[i])
                print(f"MISMATCH after obstacle {k}, scanline {i} (y = {y:.6f})")
                print(f"  incremental scanlines {planner.clipper.n_scanlines}, "
                      f"reference {ref.n_scanlines}")
                describe("incremental", planner.clipper, i, y)
                describe("reference  ", ref, i, y)
                print(f"  obstacle {k} bbox: {tuple(round(v, 3) for v in obs.bounds)}")
                print(f"  dilated local bbox: "
                      f"{tuple(round(v, 3) for v in G.bounds_of(planner._dilated_local(obs)))}")
                return

    print("all obstacles: incremental matches the from-scratch reference exactly")


if __name__ == "__main__":
    main()
