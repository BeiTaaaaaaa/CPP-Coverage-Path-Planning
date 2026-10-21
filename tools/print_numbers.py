"""Print every number the write-up quotes, straight from the result tables.

Useful after a full re-run: the derived figures must match the tables exactly,
the measured ones are wall-clock and drift, and this prints the current value of
both so refreshing the documents is mechanical rather than a hunt through CSVs.

Run:  python tools/print_numbers.py
"""

from __future__ import annotations

import pathlib

import pandas as pd

T = pathlib.Path(__file__).resolve().parents[1] / "results" / "tables"


def load(name: str) -> pd.DataFrame:
    path = T / f"{name}.csv"
    if not path.exists():
        raise SystemExit(f"missing {path}; run experiments/run_all.py first")
    return pd.read_csv(path)


def main() -> None:
    e1 = load("exp1_clipping")
    e2 = load("exp2_incremental")
    e3 = load("exp3_scaling")
    e4 = load("exp4_compare")
    e5 = load("exp5_turn_radius")
    a1 = load("exp_ablation_repair")
    a2 = load("exp_ablation_window")
    cp, f2 = e4[e4.system == "cppclip"], e4[e4.system == "fields2cover"]

    print(
        f"E1: {len(e1)} fields, {int(e1.n_scanlines.sum())} scanlines, "
        f"{int(e1.n_mismatched_scanlines.sum())} mismatched, max {e1.max_abs_error.max():.3e} m, "
        f"speed-up {e1.speedup.median():.2f}x "
        f"(min {e1.speedup.min():.2f}x, max {e1.speedup.max():.2f}x)"
    )
    print(
        f"E2: {len(e2)} events | invalidated median {100 * e2.affected_fraction.median():.1f}% "
        f"mean {100 * e2.affected_fraction.mean():.1f}% p90 {100 * e2.affected_fraction.quantile(0.9):.1f}%"
    )
    print(
        f"    churn added {e2.swaths_added.median():.0f} removed {e2.swaths_removed.median():.0f} "
        f"kept {e2.swaths_kept.median():.0f} | local repair {(e2.route_repair == 'local').mean():.0%} "
        f"| modes {e2['mode'].value_counts().to_dict()}"
    )
    print(
        f"    time median {1000 * e2.t_incremental_s.median():.1f} / "
        f"{1000 * e2.t_full_s.median():.1f} / {1000 * e2.t_full_fixed_s.median():.1f} ms "
        f"| totals {e2.t_incremental_s.sum():.1f} / {e2.t_full_s.sum():.1f} / "
        f"{e2.t_full_fixed_s.sum():.1f} s"
    )
    print(
        f"    speed-up {e2.speedup_vs_full.median():.2f}x vs full, "
        f"{e2.speedup_vs_fixed.median():.2f}x vs fixed"
    )
    print(
        f"    coverage {e2.coverage_inc.mean():.4f} / {e2.coverage_full.mean():.4f} / "
        f"{e2.coverage_fixed.mean():.4f} | non-working {e2.nw_inc.mean():.4f} / "
        f"{e2.nw_full.mean():.4f} / {e2.nw_fixed.mean():.4f}"
    )
    print(
        f"    path penalty median {100 * e2.path_penalty_vs_fixed.median():+.2f}% "
        f"mean {100 * e2.path_penalty_vs_fixed.mean():+.2f}% "
        f"p90 {100 * e2.path_penalty_vs_fixed.quantile(0.9):+.2f}%"
    )
    print("    coverage by change mode (the split the average hides):")
    for mode, group in e2.groupby("mode"):
        gap = 100 * (group.coverage_fixed.mean() - group.coverage_inc.mean())
        print(
            f"      {mode:<12} n={len(group):3d}  inc {group.coverage_inc.mean():.4f}  "
            f"fixed {group.coverage_fixed.mean():.4f}  gap {gap:+.3f} pp  "
            f"max {100 * (group.coverage_fixed - group.coverage_inc).max():+.3f} pp"
        )

    g = e3.groupby("scale").agg(
        area=("area_ha", "mean"), n=("n_scanlines", "mean"),
        af=("affected_fraction", "mean"), sp=("speedup_vs_full", "median"),
        spf=("speedup_vs_fixed", "median"), pen=("path_penalty", "mean"),
    )
    for s, r in g.iterrows():
        print(
            f"E3 x{s:g}: {r.area:.1f} ha, {r.n:.0f} scanlines, invalidated {100 * r.af:.1f}%, "
            f"{r.sp:.2f}x vs full ({r.spf:.2f}x vs fixed), penalty {100 * r.pen:+.1f}%"
        )

    print(
        f"E4 cppclip: coverage {cp.coverage.median():.4f}, length {cp.total_length.median():.0f} m, "
        f"non-working {100 * cp.non_working_ratio.median():.1f}%, "
        f"overlap {100 * cp.overlap.median():.2f}%, swaths {cp.n_swaths.median():.1f}, "
        f"time {cp.time_s.median():.3f} s"
    )
    print(
        f"E4 f2c    : coverage {f2.coverage.median():.4f}, length {f2.total_length.median():.0f} m, "
        f"non-working {100 * f2.non_working_ratio.median():.1f}%, "
        f"overlap {100 * f2.overlap.median():.2f}%, swaths {f2.n_swaths.median():.1f}, "
        f"time {f2.time_s.median():.3f} s"
    )
    ratio = (cp.set_index("field").total_length / f2.set_index("field").total_length).dropna()
    diff = (cp.set_index("field").coverage - f2.set_index("field").coverage).dropna()
    print(
        f"E4 ratio median {ratio.median():.3f} p10 {ratio.quantile(0.1):.3f} "
        f"p90 {ratio.quantile(0.9):.3f} | coverage diff {diff.median():+.4f} / {diff.mean():+.4f}"
    )

    for t, r in e5.groupby("turn_radius").agg(
        p=("path_length", "median"), tr=("transit_length", "median"),
        nw=("non_working_ratio", "median"), rt=("ratio_vs_straight", "median"),
    ).iterrows():
        print(
            f"E5 radius {t:g} m: transit {r.tr:.1f} m, path {r.p:.0f} m, "
            f"non-working {100 * r.nw:.1f}%, ratio {r.rt:.3f} "
            f"(understates by {100 * (r.rt - 1):.1f}%)"
        )

    print("\nAblation, global_repair_fraction (repair_window = 12):")
    print(
        a1[["global_fraction", "pct_global", "t_incremental_median_ms",
            "speedup_vs_fixed_median", "path_penalty_median", "path_penalty_p90"]]
        .to_string(index=False)
    )
    print("\nAblation, repair_window (global_repair_fraction = 0.5):")
    print(
        a2[["repair_window", "pct_global", "t_incremental_median_ms",
            "speedup_vs_fixed_median", "path_penalty_median", "path_penalty_p90"]]
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()
