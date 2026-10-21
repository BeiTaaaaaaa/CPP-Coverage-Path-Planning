"""Run cppclip on the benchmark fields and export solutions in the shared format.

The Fields2Cover side consumes exactly the geometry this writes, so the two
systems cannot accidentally be compared on different field outlines.

Run:  python experiments/export_cppclip.py [--limit 60] [--width 6.0] [--headland 6.0]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import print_environment  # noqa: E402
from f2c_io import ensure_io_dirs, export_fields, write_solution  # noqa: E402

from cppclip.io_fields import load_benchmark  # noqa: E402
from cppclip.metrics import evaluate  # noqa: E402
from cppclip.planner import PlanParams, plan  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--width", type=float, default=6.0)
    ap.add_argument("--headland", type=float, default=6.0)
    ap.add_argument("--min-area-ha", type=float, default=0.8)
    ap.add_argument("--max-area-ha", type=float, default=10.0)
    ap.add_argument("--route", type=str, default="optimised")
    ap.add_argument("--angle-candidates", type=int, default=24)
    ap.add_argument("--turn-radius", type=float, default=0.0,
                    help="minimum turning radius; 0 joins strokes with straight legs")
    args = ap.parse_args()

    print("Export: cppclip solutions on Fields2Benchmark geometry")
    print_environment()
    print()

    fields = load_benchmark(
        min_area_ha=args.min_area_ha, max_area_ha=args.max_area_ha, limit=args.limit
    )
    print(f"fields: {len(fields)}  swath {args.width} m  headland {args.headland} m\n")

    dirs = ensure_io_dirs()
    export_fields(fields)

    params = PlanParams(
        swath_width=args.width,
        headland_width=args.headland,
        route=args.route,
        n_angle_candidates=args.angle_candidates,
        turn_radius=args.turn_radius,
    )

    summary = []
    for k, field in enumerate(fields, 1):
        plan_obj = plan(field, params)
        metrics = evaluate(field, plan_obj)

        swaths = [((s.p0[0], s.p0[1]), (s.p1[0], s.p1[1])) for s in plan_obj.strokes]
        write_solution(
            "cppclip",
            field.name,
            swaths=swaths,
            headland_loops=plan_obj.headland_loops,
            path=plan_obj.path,
            time_s=plan_obj.total_time,
            extra={
                "n_swaths": len(swaths),
                "coverage": metrics.coverage,
                "overlap": metrics.overlap,
                "spillage": metrics.spillage,
                # Authoritative split, from the planner.  Recovering it by
                # measuring the headland geometry would fold the joins between
                # separate loops into the working distance; a head-to-head run
                # against Fields2Cover caught exactly that.
                "working_length": metrics.working_length,
                "headland_length": metrics.headland_length,
                "transit_length": metrics.transit_length,
                # metrics.path_length already adds the headland loops, which
                # plan.path alone does not include.
                "total_length": metrics.path_length,
                "non_working_ratio": metrics.non_working_ratio,
                "angle_deg": metrics.angle_deg,
                "turn_radius": args.turn_radius,
                "area_m2": field.area,
                "country": field.meta.get("country"),
            },
        )
        summary.append(
            {
                "field": field.name,
                "coverage": metrics.coverage,
                "path_length": metrics.path_length,
                "non_working_ratio": metrics.non_working_ratio,
                "time_s": plan_obj.total_time,
            }
        )
        if k % 10 == 0:
            print(f"  ... {k}/{len(fields)}")

    (dirs["root"] / "cppclip_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    print(f"\nwrote {len(summary)} cppclip solutions to {dirs['cppclip']}")


if __name__ == "__main__":
    main()
