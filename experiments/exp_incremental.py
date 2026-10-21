"""Experiment 2 -- dynamic incremental replanning versus replanning from scratch.

This is the headline experiment.  A real field is planned, then obstacles appear
and disappear one at a time, as they would when a machine encounters a
waterlogged patch or a fallen branch.  Each change is handled two ways:

``incremental``
    :class:`~cppclip.incremental.IncrementalPlanner`: re-clip only the scanlines
    the obstacle's ``y`` span touches, refresh only those strokes, and repair the
    tour locally.
``full``
    Re-run the whole pipeline for the new scene, heading search included -- what
    a system without an edge table has to do.
``full_fixed_heading``
    The same global rebuild but with the heading frozen to the incremental
    planner's, so the comparison isolates the clipping and routing savings from
    the (large) cost of the heading search.

Measured per change: wall time, the fraction of the scanline grid that had to be
re-clipped, and the *quality* of the resulting plan (coverage, non-working
ratio, path length) so the speed-up can be reported against what it costs.

Run:  python experiments/exp_incremental.py [--fields 40] [--changes 6]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import environment, print_environment, save_table  # noqa: E402

import numpy as np  # noqa: E402

from cppclip import geometry as G  # noqa: E402
from cppclip.fields import random_obstacles  # noqa: E402
from cppclip.incremental import IncrementalPlanner  # noqa: E402
from cppclip.io_fields import load_benchmark  # noqa: E402
from cppclip.metrics import evaluate  # noqa: E402
from cppclip.planner import PlanParams, plan  # noqa: E402

PARAMS = dict(swath_width=6.0, headland_width=6.0, min_swath_length=1.5, n_angle_candidates=24)


def prepare_obstacles(field, count: int, seed: int):
    """A reproducible arrival sequence of disjoint in-field obstacles."""
    inner = G.erode(field.boundary, 22.0)
    if inner.is_empty or inner.area < 300.0:
        return []
    return random_obstacles(inner, count, seed=seed, size_range=(5.0, 11.0))


def run_field(field, n_changes: int, seed: int, global_fraction: float = 0.25,
              repair_window: int = 12) -> list[dict]:
    params = PlanParams(**PARAMS)
    obstacles = prepare_obstacles(field, n_changes, seed)
    if len(obstacles) < 2:
        return []

    planner = IncrementalPlanner(
        field, params, global_repair_fraction=global_fraction, repair_window=repair_window
    )
    known = []
    rows = []

    for k, obs in enumerate(obstacles):
        known.append(obs)
        scene = field.with_obstacles(known)

        # ---- incremental ------------------------------------------------
        t0 = time.perf_counter()
        _handle, report = planner.add_obstacle(obs)
        t_inc = time.perf_counter() - t0
        inc_plan = planner.to_plan()
        m_inc = evaluate(scene, inc_plan)

        # ---- full rebuild, heading search included ----------------------
        t0 = time.perf_counter()
        full_plan = plan(scene, params)
        t_full = time.perf_counter() - t0
        m_full = evaluate(scene, full_plan)

        # ---- full rebuild with the heading frozen -----------------------
        t0 = time.perf_counter()
        fixed_plan = plan(scene, PlanParams(angle=planner.angle, **PARAMS))
        t_fixed = time.perf_counter() - t0
        m_fixed = evaluate(scene, fixed_plan)

        rows.append(
            {
                "field": field.name,
                "country": field.meta.get("country"),
                "area_m2": field.area,
                "change_index": k,
                "mode": report.mode,
                "route_repair": report.route_repair,
                "n_scanlines_total": report.n_total_scanlines,
                "n_scanlines_affected": report.n_affected_scanlines,
                "affected_fraction": report.work_fraction,
                "swaths_added": report.swaths_added,
                "swaths_removed": report.swaths_removed,
                "swaths_kept": report.swaths_kept,
                "t_incremental_s": t_inc,
                "t_full_s": t_full,
                "t_full_fixed_s": t_fixed,
                "speedup_vs_full": t_full / t_inc if t_inc > 0 else float("nan"),
                "speedup_vs_fixed": t_fixed / t_inc if t_inc > 0 else float("nan"),
                "coverage_inc": m_inc.coverage,
                "coverage_full": m_full.coverage,
                "coverage_fixed": m_fixed.coverage,
                "nw_inc": m_inc.non_working_ratio,
                "nw_full": m_full.non_working_ratio,
                "nw_fixed": m_fixed.non_working_ratio,
                "path_inc": m_inc.path_length,
                "path_full": m_full.path_length,
                "path_fixed": m_fixed.path_length,
                "path_penalty_vs_fixed": (
                    m_inc.path_length / m_fixed.path_length - 1.0
                    if m_fixed.path_length > 0
                    else float("nan")
                ),
            }
        )

    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fields", type=int, default=40)
    ap.add_argument("--changes", type=int, default=6)
    ap.add_argument("--min-area-ha", type=float, default=1.0)
    ap.add_argument("--max-area-ha", type=float, default=8.0)
    ap.add_argument("--global-fraction", type=float, default=0.5,
                    help="insertion/tour ratio above which the tour is re-solved globally")
    ap.add_argument("--repair-window", type=int, default=4)
    ap.add_argument("--tag", type=str, default="exp2_incremental",
                    help="table name, so ablations do not overwrite each other")
    args = ap.parse_args()

    print("Experiment 2: incremental replanning vs full replanning")
    print_environment()
    print()

    fields = load_benchmark(min_area_ha=args.min_area_ha, max_area_ha=args.max_area_ha)
    fields = fields[: args.fields]
    print(f"fields: {len(fields)}  changes per field: {args.changes}\n")

    rows: list[dict] = []
    for k, field in enumerate(fields, 1):
        got = run_field(field, args.changes, seed=1000 + k,
                       global_fraction=args.global_fraction, repair_window=args.repair_window)
        rows.extend(got)
        if k % 10 == 0:
            print(f"  ... {k}/{len(fields)} fields, {len(rows)} change events")

    if not rows:
        print("no usable fields")
        return

    df = save_table(rows, args.tag)

    print(f"\nglobal_fraction={args.global_fraction}  repair_window={args.repair_window}")
    print(f"change events: {len(df)}")
    print("\n--- work avoided ---")
    print(f"affected scanline fraction: median {df.affected_fraction.median():.3f} "
          f"mean {df.affected_fraction.mean():.3f} p90 {df.affected_fraction.quantile(0.9):.3f}")
    print(f"stroke churn: added median {df.swaths_added.median():.0f}, "
          f"removed median {df.swaths_removed.median():.0f}, "
          f"kept median {df.swaths_kept.median():.0f}")
    print(f"route repair: {df.route_repair.value_counts().to_dict()}")
    print(f"modes       : {df['mode'].value_counts().to_dict()}")

    print("\n--- time ---")
    print(f"incremental   median {1000*df.t_incremental_s.median():8.2f} ms   "
          f"sum {df.t_incremental_s.sum():7.2f} s")
    print(f"full          median {1000*df.t_full_s.median():8.2f} ms   "
          f"sum {df.t_full_s.sum():7.2f} s")
    print(f"full(fixed h) median {1000*df.t_full_fixed_s.median():8.2f} ms   "
          f"sum {df.t_full_fixed_s.sum():7.2f} s")
    print(f"speedup vs full        median {df.speedup_vs_full.median():7.2f} x")
    print(f"speedup vs fixed-head  median {df.speedup_vs_fixed.median():7.2f} x")

    print("\n--- quality cost ---")
    print(f"coverage  inc {df.coverage_inc.mean():.4f}   full {df.coverage_full.mean():.4f}   "
          f"fixed {df.coverage_fixed.mean():.4f}")
    print(f"non-work  inc {df.nw_inc.mean():.4f}   full {df.nw_full.mean():.4f}   "
          f"fixed {df.nw_fixed.mean():.4f}")
    print(f"path ratio inc/fixed: median {df.path_penalty_vs_fixed.median():+.3%}  "
          f"mean {df.path_penalty_vs_fixed.mean():+.3%}  "
          f"p90 {df.path_penalty_vs_fixed.quantile(0.9):+.3%}")


if __name__ == "__main__":
    main()
