"""How much does modelling turn curvature actually cost?

Straight transit connectors are the shortest line between two stroke ends, but a
machine with a turning radius cannot drive them.  This measures the difference
on real fields, which is also what makes the cppclip/Fields2Cover distance
comparison like-for-like: Fields2Cover plans Dubins turns, so cppclip must too
before the two numbers mean the same thing.

Run:  python experiments/exp_turn_radius.py [--fields 40]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import print_environment, save_table  # noqa: E402

import numpy as np  # noqa: E402

from cppclip.io_fields import load_benchmark  # noqa: E402
from cppclip.metrics import evaluate  # noqa: E402
from cppclip.planner import PlanParams, plan  # noqa: E402

BASE = dict(swath_width=6.0, headland_width=6.0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fields", type=int, default=40)
    ap.add_argument("--radii", type=float, nargs="+", default=[0.0, 1.0, 2.0, 4.0])
    args = ap.parse_args()

    print("Experiment 5: cost of kinematically feasible turns")
    print_environment()
    print()

    fields = load_benchmark(min_area_ha=1.0, max_area_ha=8.0)[: args.fields]
    print(f"fields {len(fields)}   radii {args.radii} m\n")

    rows = []
    for field in fields:
        base_total = None
        for radius in args.radii:
            p = plan(field, PlanParams(turn_radius=radius, **BASE))
            m = evaluate(field, p)
            if radius == 0.0:
                base_total = m.path_length
            rows.append(
                {
                    "field": field.name,
                    "country": field.meta.get("country"),
                    "area_m2": field.area,
                    "turn_radius": radius,
                    "n_strokes": m.n_strokes,
                    "transit_length": m.transit_length,
                    "path_length": m.path_length,
                    "non_working_ratio": m.non_working_ratio,
                    "coverage": m.coverage,
                    "plan_time_s": m.plan_time,
                    "ratio_vs_straight": m.path_length / base_total if base_total else float("nan"),
                }
            )

    df = save_table(rows, "exp5_turn_radius")

    print("--- median over fields ---")
    print(f"{'radius':>7} {'transit m':>11} {'path m':>10} {'non-work':>9} "
          f"{'coverage':>9} {'vs straight':>12}")
    for radius in args.radii:
        sub = df[df.turn_radius == radius]
        print(f"{radius:7.1f} {sub.transit_length.median():11.1f} "
              f"{sub.path_length.median():10.1f} {sub.non_working_ratio.median():9.3f} "
              f"{sub.coverage.median():9.4f} {sub.ratio_vs_straight.median():12.4f}")

    print("\nInterpretation: the ratio column is what a fair distance comparison")
    print("with a curvature-aware planner must use. Quoting the straight-connector")
    print("distance against Fields2Cover's Dubins distance is not like-for-like.")


if __name__ == "__main__":
    main()
