"""Runnable tour of the library. Prints a report and writes two figures.

    python examples/quickstart.py

Covers, in order: the clipping core on its own; the full planning pipeline; the
metrics; and a dynamic replan under an obstacle appearing and being cleared.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".cache" / "matplotlib"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from cppclip import fields as F  # noqa: E402
from cppclip import geometry as G  # noqa: E402
from cppclip.incremental import IncrementalPlanner  # noqa: E402
from cppclip.metrics import evaluate  # noqa: E402
from cppclip.planner import PlanParams, plan  # noqa: E402
from cppclip.sweep import ScanlineClipper  # noqa: E402
from cppclip.viz import draw_field, draw_intervals, draw_plan  # noqa: E402

OUT = ROOT / "results" / "figures"
OUT.mkdir(parents=True, exist_ok=True)
WIDTH = 6.0
HEADLAND = 6.0


def section(title: str) -> None:
    print(f"\n{title}\n" + "-" * len(title))


def main() -> None:
    # ------------------------------------------------------------------
    section("1. The clipping core")
    field = F.make_field("rectilinear", seed=4, n_obstacles=8, target_area=20_000.0)
    clip = ScanlineClipper.from_geometry(field.free, WIDTH)
    print(f"field            {field.name}   {field.area:,.0f} m2")
    print(f"free area        {field.free_area:,.0f} m2  ({len(field.obstacles)} obstacles)")
    print(f"scanlines        {clip.n_scanlines}")
    print(f"edges in table   {clip.n_edges}   peak active {int(clip.edge_load().max())}")

    worst = 0.0
    for i in range(clip.n_scanlines):
        got, ref = sorted(clip.intervals_at(i)), sorted(clip.intervals_geos(i))
        assert len(got) == len(ref)
        for (a0, a1), (b0, b1) in zip(got, ref):
            worst = max(worst, abs(a0 - b0), abs(a1 - b1))
    print(f"vs GEOS clipping max error {worst:.2e} m  -> {'exact' if worst < 1e-9 else 'MISMATCH'}")

    fig, ax = plt.subplots(figsize=(6, 5), dpi=110)
    draw_field(ax, field)
    draw_intervals(ax, clip, color="#0b6e4f", lw=1.0)
    ax.set_aspect("equal")
    ax.set_title("Effective intervals (one per swath pass)")
    fig.tight_layout()
    fig.savefig(OUT / "quickstart_intervals.png", bbox_inches="tight")
    plt.close(fig)

    # ------------------------------------------------------------------
    section("2. Planning")
    params = PlanParams(swath_width=WIDTH, headland_width=HEADLAND)
    p = plan(field, params)
    m = evaluate(field, p)
    print(f"heading          {m.angle_deg:.1f} deg")
    print(f"strokes          {m.n_strokes}")
    print(f"coverage         {m.coverage:.4f}   (missed {m.missed:.4f}, overlap {m.overlap:.4f})")
    print(f"path             {m.path_length:,.0f} m")
    print(f"non-working      {100 * m.non_working_ratio:.1f} %")
    print(f"plan time        {1000 * m.plan_time:.1f} ms "
          f"(clip {1000 * m.time_clip:.1f} ms, route {1000 * m.time_route:.1f} ms)")

    fig, ax = plt.subplots(figsize=(7, 6), dpi=110)
    draw_field(ax, field)
    draw_plan(ax, p)
    ax.set_aspect("equal")
    ax.set_title(f"Coverage plan — coverage {m.coverage:.3f}, non-working {100*m.non_working_ratio:.0f}%")
    fig.tight_layout()
    fig.savefig(OUT / "quickstart_plan.png", bbox_inches="tight")
    plt.close(fig)

    # ------------------------------------------------------------------
    section("3. Dynamic replanning")
    dynamic = IncrementalPlanner(field, params)
    print(f"heading frozen at {dynamic.angle * 180 / 3.141592653589793:.1f} deg "
          f"for the whole session")
    print(f"{'change':<8}{'mode':<13}{'scanlines':>10}{'affected':>10}"
          f"{'t_inc':>10}{'t_full':>10}{'coverage':>10}")

    import time

    from shapely.geometry import box

    minx, miny, maxx, maxy = G.bounds_of(field.boundary)
    cx, cy = 0.5 * (minx + maxx), 0.5 * (miny + maxy)
    # Obstacle size relative to the field is what sets the affected fraction, so
    # keep them modest (8 m) rather than filling the field with one big block.
    arrivals = [
        G.normalise(box(cx - 4 + 34 * k, cy - 4, cx + 4 + 34 * k, cy + 4))
        for k in range(-1, 2)
    ]

    handles = []
    for obs in arrivals:
        t0 = time.perf_counter()
        handle, rep = dynamic.add_obstacle(obs)
        t_inc = time.perf_counter() - t0
        handles.append(handle)

        scene = dynamic.current_field()
        t0 = time.perf_counter()
        full = plan(scene, PlanParams(angle=dynamic.angle, swath_width=WIDTH,
                                      headland_width=HEADLAND))
        t_full = time.perf_counter() - t0
        cov = evaluate(scene, dynamic.to_plan()).coverage

        print(f"add {handle:<4}{rep.mode:<13}{rep.n_affected_scanlines:>10}"
              f"{rep.work_fraction:>9.0%}{1000*t_inc:>9.1f}ms{1000*t_full:>9.1f}ms{cov:>10.4f}")

    for handle in handles:
        rep = dynamic.remove_obstacle(handle)
        print(f"del {handle:<4}{rep.mode:<13}{rep.n_affected_scanlines:>10}"
              f"{rep.work_fraction:>9.0%}{1000*rep.time_s:>9.1f}ms")

    print(f"\nfigures written to {OUT}")


if __name__ == "__main__":
    main()
