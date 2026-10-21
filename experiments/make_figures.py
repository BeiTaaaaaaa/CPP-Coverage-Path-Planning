"""Turn the experiment tables into the figures for the write-up.

Reads whatever is present in ``results/tables`` and writes PNGs to
``results/figures``.  Missing tables are skipped with a note rather than
crashing, so this can be run while experiments are still in flight.

Run:  python experiments/make_figures.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import FIGURES, TABLES, ensure_dirs, print_environment  # noqa: E402

os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parents[1] / ".cache" / "matplotlib"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402


def load(name: str):
    path = TABLES / f"{name}.csv"
    if not path.exists():
        print(f"  (skip) {name}: no table")
        return None
    return pd.read_csv(path)


def fig_scaling(df) -> None:
    if df is None:
        return
    by = df.groupby("scale").agg(
        area=("area_ha", "mean"),
        scanlines=("n_scanlines", "mean"),
        affected=("affected_fraction", "mean"),
        sp_fixed=("speedup_vs_fixed", "median"),
        sp_full=("speedup_vs_full", "median"),
        penalty=("path_penalty", "mean"),
    )
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.4), dpi=110)

    axes[0].plot(by.scanlines, 100 * by.affected, "o-", color="#b03a2e")
    axes[0].set_xlabel("scanlines in field")
    axes[0].set_ylabel("scanlines invalidated by one obstacle [%]")
    axes[0].set_title("Work avoided grows with field size")
    axes[0].grid(alpha=0.3)

    axes[1].plot(by.scanlines, by.sp_full, "s-", label="vs full replan", color="#1f6f8b")
    axes[1].plot(by.scanlines, by.sp_fixed, "o--", label="vs fixed-heading replan",
                 color="#0b6e4f")
    axes[1].set_xlabel("scanlines in field")
    axes[1].set_ylabel("speed-up [x]")
    axes[1].set_yscale("log")
    axes[1].set_title("Incremental replanning speed-up")
    axes[1].legend()
    axes[1].grid(alpha=0.3, which="both")

    axes[2].bar(range(len(by)), 100 * by.penalty, color="#7d5ba6")
    axes[2].set_xticks(range(len(by)))
    axes[2].set_xticklabels([f"{a:.0f} ha" for a in by.area], rotation=30, ha="right")
    axes[2].axhline(0, color="k", lw=0.8)
    axes[2].set_ylabel("path-length penalty [%]")
    axes[2].set_title("What the speed-up costs")
    axes[2].grid(alpha=0.3, axis="y")

    fig.tight_layout()
    out = FIGURES / "exp3_scaling.png"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {out}")


def fig_ablation(df_frac, df_win) -> None:
    if df_frac is None and df_win is None:
        return
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), dpi=110)

    if df_frac is not None:
        g = df_frac.groupby("global_fraction").agg(
            t=("t_incremental_median_ms", "mean"),
            sp=("speedup_vs_fixed_median", "mean"),
            pen=("path_penalty_median", "mean"),
            pct_global=("pct_global", "mean"),
        )
        ax = axes[0]
        ax.plot(g.index, g.sp, "o-", color="#1f6f8b")
        ax.set_xlabel("global_repair_fraction")
        ax.set_ylabel("speed-up vs fixed-heading replan [x]")
        ax.set_title("Tour re-solve threshold")
        ax2 = ax.twinx()
        ax2.plot(g.index, 100 * g.pen, "s--", color="#b03a2e")
        ax2.set_ylabel("path penalty [%]", color="#b03a2e")
        ax2.tick_params(axis="y", colors="#b03a2e")
        ax.grid(alpha=0.3)

    if df_win is not None:
        g = df_win.groupby("repair_window").agg(
            sp=("speedup_vs_fixed_median", "mean"),
            pen=("path_penalty_median", "mean"),
            p90=("path_penalty_p90", "mean"),
        )
        ax = axes[1]
        ax.plot(g.index, g.sp, "o-", color="#1f6f8b", label="speed-up")
        ax.set_xlabel("repair_window")
        ax.set_ylabel("speed-up [x]")
        ax.set_title("Local-repair window")
        ax2 = ax.twinx()
        ax2.plot(g.index, 100 * g.pen, "s--", color="#b03a2e", label="median penalty")
        ax2.plot(g.index, 100 * g.p90, "^:", color="#e08a3c", label="p90 penalty")
        ax2.set_ylabel("path penalty [%]")
        ax2.legend(fontsize=8)
        ax.grid(alpha=0.3)

    fig.tight_layout()
    out = FIGURES / "ablations.png"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {out}")


def fig_compare(df) -> None:
    if df is None:
        return
    ok = df[df.get("error").isna()] if "error" in df.columns else df
    if not len(ok):
        return

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.4), dpi=110)
    systems = ["cppclip", "fields2cover"]
    colors = {"cppclip": "#1f6f8b", "fields2cover": "#b03a2e"}
    labels = {"cppclip": "cppclip", "fields2cover": "Fields2Cover (snake)"}

    ax = axes[0]
    data = [ok[ok.system == s].coverage.dropna().values for s in systems]
    bp = ax.boxplot(data, tick_labels=[labels[s] for s in systems], patch_artist=True, widths=0.55)
    for patch, s in zip(bp["boxes"], systems):
        patch.set_facecolor(colors[s])
        patch.set_alpha(0.7)
    ax.set_ylabel("coverage")
    ax.set_title("Coverage of the drivable area")
    ax.grid(alpha=0.3, axis="y")

    ax = axes[1]
    data = [ok[ok.system == s].total_length.dropna().values for s in systems]
    bp = ax.boxplot(data, tick_labels=[labels[s] for s in systems], patch_artist=True, widths=0.55)
    for patch, s in zip(bp["boxes"], systems):
        patch.set_facecolor(colors[s])
        patch.set_alpha(0.7)
    ax.set_ylabel("total driven distance [m]")
    ax.set_title("Distance (see caveat: F2C includes Dubins turns)")
    ax.grid(alpha=0.3, axis="y")

    ax = axes[2]
    data = [100 * ok[ok.system == s].non_working_ratio.dropna().values for s in systems]
    bp = ax.boxplot(data, tick_labels=[labels[s] for s in systems], patch_artist=True, widths=0.55)
    for patch, s in zip(bp["boxes"], systems):
        patch.set_facecolor(colors[s])
        patch.set_alpha(0.7)
    ax.set_ylabel("non-working ratio [%]")
    ax.set_title("Repositioning share")
    ax.grid(alpha=0.3, axis="y")

    fig.tight_layout()
    out = FIGURES / "exp4_compare.png"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {out}")


def fig_incremental(df) -> None:
    if df is None:
        return
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.4), dpi=110)

    axes[0].hist(100 * df.affected_fraction.dropna(), bins=24, color="#0b6e4f", alpha=0.85)
    axes[0].set_xlabel("scanlines invalidated [%]")
    axes[0].set_ylabel("change events")
    axes[0].set_title(f"Work per environment change (n={len(df)})")
    axes[0].grid(alpha=0.3, axis="y")

    axes[1].hist(100 * df.path_penalty_vs_fixed.dropna(), bins=30, color="#7d5ba6", alpha=0.85)
    axes[1].axvline(0, color="k", lw=0.9)
    axes[1].set_xlabel("path-length penalty vs global re-solve [%]")
    axes[1].set_ylabel("change events")
    axes[1].set_title("Quality cost of incremental repair")
    axes[1].grid(alpha=0.3, axis="y")

    ax = axes[2]
    ax.scatter(df.n_scanlines_total, 1000 * df.t_incremental_s, s=9, alpha=0.5,
               color="#1f6f8b", label="incremental")
    ax.scatter(df.n_scanlines_total, 1000 * df.t_full_fixed_s, s=9, alpha=0.5,
               color="#b03a2e", label="full (fixed heading)")
    ax.set_xlabel("scanlines in field")
    ax.set_ylabel("time per change [ms]")
    ax.set_yscale("log")
    ax.set_title("Cost per change")
    ax.legend()
    ax.grid(alpha=0.3, which="both")

    fig.tight_layout()
    out = FIGURES / "exp2_incremental.png"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {out}")


def main() -> None:
    ensure_dirs()
    print_environment()
    print()
    fig_scaling(load("exp3_scaling"))
    fig_ablation(load("exp_ablation_repair"), load("exp_ablation_window"))
    fig_compare(load("exp4_compare"))
    fig_incremental(load("exp2_incremental"))
    print("\ndone")


if __name__ == "__main__":
    main()
