"""Render a few plans to PNG so the geometry can be eyeballed."""
from __future__ import annotations

import os

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("MPLCONFIGDIR", os.path.join(_HERE, ".cache", "matplotlib"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from cppclip import fields as F
from cppclip.planner import PlanParams, plan
from cppclip.viz import draw_field, draw_plan, draw_intervals, figure_plan


def main() -> None:
    out = os.path.join(_HERE, "results", "figures")
    os.makedirs(out, exist_ok=True)

    # --- 1. one detailed field -----------------------------------------
    field = F.make_field("rectilinear", seed=4, n_obstacles=12, target_area=20_000.0)
    params = PlanParams(swath_width=6.0, headland_width=6.0)
    p = plan(field, params)
    figure_plan(field, p, path=os.path.join(out, "plan_rectilinear.png"))
    plt.close("all")

    # --- 2. the four shapes side by side --------------------------------
    cases = [("l", 1, 6), ("u", 2, 6), ("star", 3, 10), ("rectilinear", 4, 0)]
    fig, axes = plt.subplots(2, 2, figsize=(14, 11), dpi=100)
    for ax, (kind, seed, n_obs) in zip(axes.ravel(), cases):
        f = F.make_field(kind, seed=seed, n_obstacles=n_obs, target_area=20_000.0)
        pl = plan(f, PlanParams(swath_width=6.0, headland_width=6.0))
        draw_field(ax, f)
        draw_plan(ax, pl, show_transit=True)
        ax.set_title(f"{kind} (obstacles={n_obs})")
        ax.set_aspect("equal")
    fig.tight_layout()
    fig.savefig(os.path.join(out, "plans_grid.png"), bbox_inches="tight")
    plt.close("all")

    # --- 3. the clipping core itself ------------------------------------
    f = F.make_field("rect", seed=0, n_obstacles=8, target_area=20_000.0)
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), dpi=100)
    draw_field(axes[0], f)
    axes[0].set_title("field + obstacles (exact free space)")

    draw_field(axes[1], f)
    for obs in f.obstacles:
        for x, y in [(p.exterior.xy[0], p.exterior.xy[1]) for p in obs.geoms]:
            axes[1].fill(x, y, color="#b03a2e", alpha=0.85, zorder=2)
    from cppclip.sweep import ScanlineClipper
    clip = ScanlineClipper.from_geometry(f.free, 6.0)
    draw_intervals(axes[1], clip, color="#0b6e4f", lw=1.1)
    axes[1].set_title(f"effective intervals  ({clip.n_scanlines} scanlines, {clip.n_edges} edges)")
    for ax in axes:
        ax.set_aspect("equal")
    fig.tight_layout()
    fig.savefig(os.path.join(out, "intervals.png"), bbox_inches="tight")
    plt.close("all")

    print("wrote figures to", out)
    for name in sorted(os.listdir(out)):
        print("  ", name)


if __name__ == "__main__":
    main()
