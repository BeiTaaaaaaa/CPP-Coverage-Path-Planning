"""Ablation -- how aggressive should the local route repair be?

The incremental planner repairs the tour locally (cheapest insertion plus a
bounded 2-opt) and falls back to a global re-solve when the number of inserted
strokes exceeds ``global_fraction * tour_size``.  That threshold is a knob with
a real trade-off:

* too low  -> almost every change triggers the global optimiser and the
  incremental planner inherits none of its speed advantage;
* too high -> the tour drifts, because nothing in the local repair can undo an
  earlier bad insertion.

This script sweeps the knob on the same fields and change sequences, so the
default in :class:`~cppclip.incremental.IncrementalPlanner` is calibrated
against measurements rather than guessed.

Run:  python experiments/exp_ablation_repair.py [--fields 24] [--changes 5]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import print_environment, save_table  # noqa: E402

import numpy as np  # noqa: E402

from cppclip.io_fields import load_benchmark  # noqa: E402
from exp_incremental import run_field  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fields", type=int, default=24)
    ap.add_argument("--changes", type=int, default=5)
    ap.add_argument("--fractions", type=float, nargs="+", default=[0.0, 0.25, 0.5, 1.0, 10.0])
    ap.add_argument("--windows", type=int, nargs="+", default=[12])
    ap.add_argument("--tag", type=str, default="exp_ablation_repair",
                    help="table name, so successive calibrations do not overwrite each other")
    args = ap.parse_args()

    print("Ablation: local route repair threshold")
    print_environment()
    print()

    fields = load_benchmark(min_area_ha=1.0, max_area_ha=8.0)[: args.fields]
    print(f"fields: {len(fields)}, changes/field: {args.changes}\n")

    rows = []
    for frac in args.fractions:
        for window in args.windows:
            all_rows = []
            for k, field in enumerate(fields, 1):
                all_rows.extend(
                    run_field(field, args.changes, seed=1000 + k,
                              global_fraction=frac, repair_window=window)
                )
            if not all_rows:
                continue
            import pandas as pd

            df = pd.DataFrame.from_records(all_rows)
            row = {
                "global_fraction": frac,
                "repair_window": window,
                "n_events": len(df),
                "pct_global": float((df.route_repair == "global").mean()),
                "t_incremental_median_ms": 1000 * float(df.t_incremental_s.median()),
                "t_incremental_sum_s": float(df.t_incremental_s.sum()),
                "t_full_fixed_sum_s": float(df.t_full_fixed_s.sum()),
                "speedup_vs_fixed_median": float(df.speedup_vs_fixed.median()),
                "coverage_mean": float(df.coverage_inc.mean()),
                "nw_mean": float(df.nw_inc.mean()),
                "path_penalty_median": float(df.path_penalty_vs_fixed.median()),
                "path_penalty_p90": float(df.path_penalty_vs_fixed.quantile(0.9)),
                "path_penalty_max": float(df.path_penalty_vs_fixed.max()),
            }
            rows.append(row)
            print(f"  fraction={frac:<5} window={window:<3} "
                  f"global={row['pct_global']:.2f}  "
                  f"t_inc={row['t_incremental_median_ms']:.2f}ms  "
                  f"speedup={row['speedup_vs_fixed_median']:.2f}x  "
                  f"path_penalty med={row['path_penalty_median']:+.2%} "
                  f"p90={row['path_penalty_p90']:+.2%}")

    save_table(rows, args.tag)
    print("\nReading: 'pct_global' is how often the escape hatch fired. A setting is")
    print("only worth its speed if its path penalty stays small.")


if __name__ == "__main__":
    main()
