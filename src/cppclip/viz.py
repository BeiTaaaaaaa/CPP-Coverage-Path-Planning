"""Plotting helpers.

Matplotlib is only imported inside the functions that need it, so the planning
core stays usable in environments without a plotting stack.
"""

from __future__ import annotations

from . import geometry as G
from .fields import Field
from .metrics import evaluate
from .planner import Plan
from .sweep import ScanlineClipper

__all__ = ["draw_field", "draw_plan", "draw_intervals", "figure_plan"]


def _polys_to_xy(geom):
    """Yield (x, y) arrays for every ring of a (multi)polygon."""
    for poly in G.iter_polygons(geom):
        x, y = poly.exterior.xy
        yield x, y
        for interior in poly.interiors:
            xi, yi = interior.xy
            yield xi, yi


def draw_field(ax, field: Field, free=None, alpha_obstacles: float = 0.85):
    """Draw the boundary, the drivable area and the obstacles."""
    free = field.free if free is None else free
    for x, y in _polys_to_xy(free):
        ax.fill(x, y, color="#eef6ee", zorder=0)
    for x, y in _polys_to_xy(field.boundary):
        ax.plot(x, y, color="#222222", lw=1.4, zorder=3)
    for obs in field.obstacles:
        for x, y in _polys_to_xy(obs):
            ax.fill(x, y, color="#b03a2e", alpha=alpha_obstacles, zorder=2)
    return ax


def draw_intervals(ax, clip: ScanlineClipper, max_lines: int | None = None, **kw):
    """Draw every effective interval as a horizontal segment."""
    n = clip.n_scanlines if max_lines is None else min(max_lines, clip.n_scanlines)
    for i in range(n):
        for x0, x1 in clip.intervals_at(i):
            ax.plot([x0, x1], [clip.ys[i], clip.ys[i]], **kw)
    return ax


def draw_plan(ax, plan: Plan, show_transit: bool = True, width: float | None = None):
    """Draw the coverage plan: strokes coloured by visit order, plus transits."""
    import numpy as np
    from matplotlib import colors
    from matplotlib import colormaps

    strokes = plan.strokes
    if strokes:
        cmap = colormaps["viridis"]
        norm = colors.Normalize(vmin=0, vmax=max(1, len(strokes) - 1))
        for k, s in enumerate(strokes):
            ax.plot(
                [s.p0[0], s.p1[0]], [s.p0[1], s.p1[1]],
                color=cmap(norm(k)), lw=1.6, solid_capstyle="butt", zorder=4,
            )
    # Each headland loop is plotted on its own.  Joining them into one polyline
    # draws a straight segment from the end of every loop to the start of the
    # next, which the machine never drives and which cuts through whatever lies
    # between the two loops.
    for loop in plan.headland_loops:
        if len(loop) < 2:
            continue
        hp = np.asarray(loop, dtype=float)
        ax.plot(hp[:, 0], hp[:, 1], color="#1f6f8b", lw=1.3, zorder=4)
    if show_transit and len(plan.path) >= 2:
        pp = np.asarray(plan.path)
        ax.plot(pp[:, 0], pp[:, 1], color="#888888", lw=0.55, ls="--", zorder=3)
    ax.set_aspect("equal")
    return ax


def figure_plan(field: Field, plan: Plan, title: str | None = None, path=None):
    """One-field summary figure: plan on the left, metrics printed on the right."""
    import matplotlib.pyplot as plt

    metrics = evaluate(field, plan)
    fig, ax = plt.subplots(figsize=(9, 7), dpi=110)
    draw_field(ax, field)
    draw_plan(ax, plan)
    ax.set_title(title or f"{field.name}  (heading {metrics.angle_deg:.1f} deg)")
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    txt = (
        f"coverage      {metrics.coverage:6.3f}\n"
        f"missed        {metrics.missed:6.3f}\n"
        f"overlap       {metrics.overlap:6.3f}\n"
        f"spillage      {metrics.spillage:6.3f}\n"
        f"path          {metrics.path_length:8.1f} m\n"
        f"working       {metrics.working_length:8.1f} m\n"
        f"transit       {metrics.transit_length:8.1f} m\n"
        f"non-working   {100 * metrics.non_working_ratio:6.1f} %\n"
        f"strokes       {metrics.n_strokes:8d}\n"
        f"plan time     {1000 * metrics.plan_time:8.1f} ms"
    )
    ax.text(
        1.02, 0.5, txt, transform=ax.transAxes, va="center", ha="left",
        family="monospace", fontsize=9,
        bbox=dict(boxstyle="round", fc="#f7f7f7", ec="#cccccc"),
    )
    fig.tight_layout()
    if path:
        fig.savefig(path, bbox_inches="tight")
    return fig
