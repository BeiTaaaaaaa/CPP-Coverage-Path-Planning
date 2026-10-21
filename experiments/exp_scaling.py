"""Experiment 3 -- where does incrementality actually pay?

The incremental planner avoids two things: re-clipping scanlines, and re-solving
the stroke order.  Their relative weight changes with field size:

* A fixed-size obstacle spans roughly a fixed *number* of scanlines, so the
  affected fraction falls as the field grows -- the clipping saving scales with
  the field.
* The routing saving scales with the *routing* cost, which grows faster than
  linearly in the number of strokes.

On the small Fields2Benchmark fields (median 2.1 ha, a few dozen strokes) the two
effects are comparable, which makes the headline speed-up look modest.  This
experiment scales one real field up by a range of factors and measures the
affected fraction, the per-stage times, and the end-to-end speed-up, so the
scaling behaviour is visible instead of being inferred from one median.

Run:  python experiments/exp_scaling.py [--scales 1 2 4 8] [--changes 4]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import print_environment, save_table  # noqa: E402

import numpy as np  # noqa: E402
from shapely import affinity  # noqa: E402

from cppclip import geometry as G  # noqa: E402
from cppclip.fields import Field  # noqa: E402
from cppclip.incremental import IncrementalPlanner  # noqa: E402
from cppclip.io_fields import load_benchmark  # noqa: E402
from cppclip.metrics import evaluate  # noqa: E402
from cppclip.planner import PlanParams, plan  # noqa: E402
from cppclip.sweep import ScanlineClipper  # noqa: E402

PARAMS = dict(swath_width=6.0, headland_width=6.0, min_swath_length=1.5, n_angle_candidates=24)
OBSTACLE_SIZE = 20.0  # metres, held fixed on purpose


def scaled_field(base: Field, factor: float) -> Field:
    boundary = G.normalise(affinity.scale(base.boundary, factor, factor, origin=(0.0, 0.0)))
    return Field(name=f"{base.name}-x{factor:g}", boundary=boundary, meta=dict(base.meta))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scales", type=float, nargs="+", default=[1.0, 2.0, 4.0, 8.0, 16.0])
    ap.add_argument("--changes", type=int, default=4)
    ap.add_argument("--source-fields", type=int, default=3)
    args = ap.parse_args()

    print("Experiment 3: how the incremental advantage scales with field size")
    print_environment()
    print()

    sources = load_benchmark(min_area_ha=1.0, max_area_ha=4.0)[: args.source_fields]
    print(f"source fields: {[f.name for f in sources]}")
    print(f"scales: {args.scales}   obstacle size: {OBSTACLE_SIZE} m (fixed)\n")

    rows = []
    for base in sources:
        for factor in args.scales:
            field = scaled_field(base, factor)
            params = PlanParams(**PARAMS)
            planner = IncrementalPlanner(field, params)
            n_total = planner.clipper.n_scanlines
            if n_total < 4:
                continue

            # A fixed physical obstacle, placed centrally so it is unambiguous.
            minx, miny, maxx, maxy = G.bounds_of(field.boundary)
            cx, cy = 0.5 * (minx + maxx), 0.5 * (miny + maxy)
            half = OBSTACLE_SIZE / 2.0
            from shapely.geometry import box

            obstacle = G.normalise(
                box(cx - half, cy - half, cx + half, cy + half).intersection(
                    G.erode(field.boundary, 12.0)
                )
            )
            if obstacle.is_empty:
                continue

            t0 = time.perf_counter()
            _h, report = planner.add_obstacle(obstacle)
            t_inc = time.perf_counter() - t0

            scene = field.with_obstacles([obstacle])
            t0 = time.perf_counter()
            inc_plan = planner.to_plan()
            t_inc_total = time.perf_counter() - t0 + t_inc
            m_inc = evaluate(scene, inc_plan)

            t0 = time.perf_counter()
            fixed_plan = plan(scene, PlanParams(angle=planner.angle, **PARAMS))
            t_fixed = time.perf_counter() - t0
            m_fixed = evaluate(scene, fixed_plan)

            t0 = time.perf_counter()
            full_plan = plan(scene, PlanParams(**PARAMS))
            t_full = time.perf_counter() - t0

            # Cost of the clip stage alone, for both.
            t0 = time.perf_counter()
            ScanlineClipper.from_geometry(scene.free, params.swath_width).all_intervals()
            t_clip_geo = time.perf_counter() - t0

            rows.append(
                {
                    "source": base.name,
                    "scale": factor,
                    "area_ha": field.area / 10_000.0,
                    "n_scanlines": n_total,
                    "n_affected": report.n_affected_scanlines,
                    "affected_fraction": report.work_fraction,
                    "mode": report.mode,
                    "route_repair": report.route_repair,
                    "t_incremental_s": t_inc_total,
                    "t_full_s": t_full,
                    "t_full_fixed_s": t_fixed,
                    "t_clip_geometry_s": t_clip_geo,
                    "speedup_vs_full": t_full / t_inc_total,
                    "speedup_vs_fixed": t_fixed / t_inc_total,
                    "coverage_inc": m_inc.coverage,
                    "coverage_fixed": m_fixed.coverage,
                    "path_inc": m_inc.path_length,
                    "path_fixed": m_fixed.path_length,
                    "path_penalty": (
                        m_inc.path_length / m_fixed.path_length - 1.0
                        if m_fixed.path_length
                        else float("nan")
                    ),
                }
            )
            print(f"  {base.name:<16} x{factor:<5g} area {field.area/1e4:7.2f} ha  "
                  f"scanlines {n_total:4d}  affected {report.work_fraction:6.1%}  "
                  f"t_inc {1000*t_inc_total:8.1f} ms  speedup(fixed) {t_fixed/t_inc_total:5.2f}x")

    if not rows:
        print("no rows produced")
        return

    df = save_table(rows, "exp3_scaling")

    print("\n--- affected fraction vs field size ---")
    by_scale = df.groupby("scale").agg(
        area_ha=("area_ha", "mean"),
        n_scanlines=("n_scanlines", "mean"),
        affected_fraction=("affected_fraction", "mean"),
        speedup_vs_fixed=("speedup_vs_fixed", "mean"),
        speedup_vs_full=("speedup_vs_full", "mean"),
        path_penalty=("path_penalty", "mean"),
    )
    print(by_scale.to_string(float_format=lambda v: f"{v:9.3f}"))


if __name__ == "__main__":
    main()
