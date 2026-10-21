"""Coverage, path-length and cost metrics.

The definitions are stated explicitly because "coverage rate" and "overlap
rate" are used loosely in the CPP literature, and a benchmark is only
comparable if the definitions travel with the numbers.

Let ``w`` be the implement (swath) width and ``F`` the drivable area, i.e. the
field boundary minus all in-field obstacles.

``swept``
    Union of the ``w``-wide rectangle swept along every working stroke
    (headland loops included).  Flat-capped, so a stroke covers exactly a
    ``w``-wide band and nothing beyond its endpoints.
``coverage``
    ``area(swept ∩ F) / area(F)`` -- the fraction of the field actually worked.
    This is the number that must approach 1.
``overlap``
    ``(Σ area(stroke band) - area(swept)) / area(F)`` -- the area worked more
    than once, normalised by field area.  This is the multiplicity excess, so a
    perfectly tiled field scores 0 and a doubled pass scores 1.
``spillage``
    ``area(swept \\ F) / area(swept)`` -- the fraction of the worked area that
    fell outside the drivable region, i.e. onto obstacles or over the boundary.
``non_working_ratio``
    ``transit / (working + transit)`` -- the 空走率 of the research plan.  Turn
    and repositioning travel, which is pure cost in fuel and compaction.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Sequence

import numpy as np
from shapely import contains_xy, prepare
from shapely.geometry import LineString
from shapely.ops import unary_union

from . import geometry as G
from .fields import Field
from .planner import Plan
from .swaths import Point2D, Stroke

__all__ = [
    "CoverageMetrics",
    "CoverageGrid",
    "coverage_grid",
    "evaluate",
    "score_solution",
    "polyline_length",
    "band_area",
    "swept_geometry",
]


@dataclass(slots=True)
class CoverageMetrics:
    """Every scalar a benchmark row needs."""

    field: str
    field_area: float
    free_area: float
    stroke_width: float

    coverage: float
    missed: float
    overlap: float
    spillage: float

    path_length: float
    working_length: float
    transit_length: float
    non_working_ratio: float
    headland_length: float

    n_strokes: int
    n_turns: int
    n_headland_passes: int

    plan_time: float
    time_free: float
    time_heading: float
    time_clip: float
    time_route: float

    angle_deg: float

    def as_dict(self) -> dict:
        return asdict(self)


def polyline_length(points: Sequence[Point2D]) -> float:
    """Total length of an open polyline."""
    pts = np.asarray(points, dtype=float)
    if pts.ndim != 2 or pts.shape[0] < 2:
        return 0.0
    return float(np.sum(np.hypot(np.diff(pts[:, 0]), np.diff(pts[:, 1]))))


def band_area(stroke: Stroke, width: float):
    """The ``width``-wide rectangle swept by one stroke."""
    return stroke.as_line().buffer(width / 2.0, cap_style="flat", join_style="mitre")


def loop_band(loop: Sequence[Point2D], width: float):
    """The ``width``-wide strip swept by one headland loop.

    Takes a single loop, never a sequence of them.  Accepting a flat point list
    spanning several loops would silently weld them together with straight
    segments the machine never drives.
    """
    return LineString(loop).buffer(width / 2.0, cap_style="flat", join_style="round")


def _is_point(obj) -> bool:  # noqa: ANN001
    """True for ``(x, y)`` and for any sequence that starts with a number."""
    if isinstance(obj, (int, float)):
        return False
    try:
        return len(obj) >= 2 and isinstance(obj[0], (int, float))
    except TypeError:
        return False


def _as_loops(headland) -> list[list[Point2D]]:  # noqa: ANN001
    """Normalise a headland argument to a list of loops.

    A **loop** is a sequence of points; a **point** is a pair of numbers.  So the
    argument is a list of loops, unless its first element is itself a point -- in
    which case a single loop was passed unwrapped and is wrapped here.

    Getting this wrong is silent in the worst way: an earlier version tested
    whether the first element of a loop was a number, which it never is, so every
    argument was read as "no headland at all".  Coverage dropped by 17 points on
    both sides of the comparison and nothing raised.
    """
    if headland is None:
        return []
    seq = list(headland)
    if not seq:
        return []
    if _is_point(seq[0]):
        return [seq]  # one loop, given as a flat point list
    return [list(loop) for loop in seq if loop is not None and len(loop) >= 2]


def swept_geometry(plan: Plan, free=None):  # noqa: ANN001, ANN201
    """The area the plan's strokes and headland loops actually sweep.

    Exposed because the coverage raster needs the same geometry the scalar
    coverage is computed from; rebuilding it with different code would let the
    picture and the number disagree.
    """
    width = plan.params.swath_width
    bands = [band_area(s, width) for s in plan.strokes if s.length > 0]
    bands.extend(loop_band(loop, width) for loop in plan.headland_loops if len(loop) >= 2)
    return unary_union(bands) if bands else None


@dataclass(slots=True)
class CoverageGrid:
    """A raster view of what the plan covered, cell by cell.

    This is a *rendering* of the same swept geometry that :func:`evaluate`
    measures, sampled on a lattice rather than intersected exactly.  The two
    disagree by roughly the perimeter of the covered region times half a cell, so
    the raster reading is slightly low and converges to the exact one as the cell
    shrinks; :meth:`difference` exists so a caller can show that rather than
    assert it.
    """

    x_edges: np.ndarray  # cell boundaries, length nx + 1
    y_edges: np.ndarray  # length ny + 1
    covered: np.ndarray  # bool [ny, nx], cell centre inside swept AND inside free
    free: np.ndarray  # bool [ny, nx], cell centre inside free
    cell: float
    exact_coverage: float

    @property
    def nx(self) -> int:
        return int(self.covered.shape[1])

    @property
    def ny(self) -> int:
        return int(self.covered.shape[0])

    @property
    def missed(self) -> np.ndarray:
        """Free cells the plan did not cover -- the gaps worth looking at."""
        return self.free & ~self.covered

    @property
    def coverage(self) -> float:
        """Coverage estimated from the raster, over the free cells sampled."""
        n_free = int(self.free.sum())
        if n_free == 0:
            return 0.0
        return float((self.covered & self.free).sum()) / n_free

    @property
    def difference(self) -> float:
        """Raster estimate minus the exact figure, in coverage units."""
        return self.coverage - self.exact_coverage

    @property
    def cell_area(self) -> float:
        return float(self.cell * self.cell)

    def covered_area(self) -> float:
        return float((self.covered & self.free).sum()) * self.cell_area

    def missed_area(self) -> float:
        return float(self.missed.sum()) * self.cell_area


def coverage_grid(
    field: Field,
    plan: Plan,
    cell: float | None = None,
    swept=None,  # noqa: ANN001
) -> CoverageGrid:
    """Sample the plan's swept area onto a square lattice.

    The default cell is half the swath width.  That is the coarsest spacing that
    still resolves the thing the raster exists to show: two adjacent swaths
    nominally touch, so a gap between them is at most one swath wide, and half a
    swath puts at least one sample inside any such gap.

    Only cell centres are tested, which is what makes this cheap enough to
    recompute while a slider moves: one vectorised ``contains_xy`` over the
    lattice, against two prepared geometries.

    Pass *swept* to reuse a union the caller already has.  Building it dominates
    the cost -- about 33 ms on a 2.5 ha field, against under 3 ms for the lattice
    sampling itself -- and :func:`evaluate` builds exactly the same geometry.

    The raster reading is an estimate and is reported as one: centre sampling
    errs by roughly the covered perimeter times half a cell, and because the
    lattice is anchored to the bounding box the sign of that error flips as the
    cell size changes.  :attr:`CoverageGrid.difference` carries the gap so a
    caller can show it rather than imply the two agree.
    """
    width = plan.params.swath_width
    if cell is None:
        cell = max(0.25, width / 2.0)
    cell = float(cell)

    minx, miny, maxx, maxy = field.free.bounds
    if not np.isfinite([minx, miny, maxx, maxy]).all():
        empty = np.zeros((0, 0), dtype=bool)
        return CoverageGrid(np.array([]), np.array([]), empty, empty, cell, 0.0)

    x_edges = np.arange(minx, maxx + cell, cell)
    y_edges = np.arange(miny, maxy + cell, cell)
    xs = 0.5 * (x_edges[:-1] + x_edges[1:])
    ys = 0.5 * (y_edges[:-1] + y_edges[1:])
    gx, gy = np.meshgrid(xs, ys)

    free = field.free
    prepare(free)
    free_mask = contains_xy(free, gx, gy).reshape(gx.shape)

    if swept is None:
        swept = swept_geometry(plan, free)
    if swept is None:
        covered = np.zeros_like(free_mask)
    else:
        prepare(swept)
        covered = contains_xy(swept, gx, gy).reshape(gx.shape) & free_mask

    return CoverageGrid(
        x_edges=x_edges,
        y_edges=y_edges,
        covered=covered,
        free=free_mask,
        cell=cell,
        exact_coverage=float(evaluate(field, plan).coverage),
    )


def score_solution(
    field: Field,
    *,
    swaths: Sequence[tuple[Point2D, Point2D]] | Sequence[Sequence[Point2D]],
    headland: Sequence[Point2D] = (),
    path: Sequence[Point2D] = (),
    width: float,
    free: G.MultiPolygon | None = None,
    working_length: float | None = None,
    transit_length: float | None = None,
    total_length: float | None = None,
) -> dict:
    """Score a solution described by raw geometry rather than by a :class:`Plan`.

    This exists so that two different planners can be compared by *identical*
    code: the caller supplies working strokes, headland loops and the driven
    polyline in metres, and every metric is computed here, once.  Letting each
    library report its own numbers would make the comparison meaningless.

    ``headland`` is a **sequence of loops**, each a sequence of points.  Passing
    a flat point list that spans several loops welds them together with straight
    joining segments; those are then measured as work and swept as area, and
    neither is true.  A genuine single loop may be passed unwrapped.

    ``working_length`` and ``transit_length`` may be supplied by the caller when
    its planner tracks them exactly.  That matters for multi-loop headlands,
    where the joins *between* loops are transit rather than work: measuring the
    loops as separate polylines here gets the along-loop distance right, and the
    caller's own figures take precedence when it knows better.
    """
    free_geom = free if free is not None else field.free
    free_area = float(free_geom.area)

    bands = []
    stroke_total = 0.0
    for seg in swaths:
        line = LineString([seg[0], seg[1]])
        length = float(line.length)
        if length <= 0:
            continue
        stroke_total += length
        bands.append(line.buffer(width / 2.0, cap_style="flat", join_style="mitre"))

    head_len = 0.0
    # ``headland`` is a sequence of loops, each a sequence of points.  A caller
    # whose solution really is one loop may pass that loop directly and it is
    # wrapped; a caller holding several loops must keep them separate, because
    # welding them into one polyline invents joining segments that are then
    # measured as work and as swept area.
    head_loops = _as_loops(headland)
    for loop in head_loops:
        if len(loop) < 2:
            continue
        head_line = LineString(loop)
        head_len += float(head_line.length)
        bands.append(head_line.buffer(width / 2.0, cap_style="flat", join_style="round"))

    if bands and free_area > 0:
        multiplicity = float(sum(b.area for b in bands))
        swept = unary_union(bands)
        swept_area = float(swept.area)
        covered_area = float(swept.intersection(free_geom).area)
        spill_area = float(swept.difference(free_geom).area)
        coverage = covered_area / free_area
        overlap = max(0.0, (multiplicity - swept_area) / free_area)
        spillage = spill_area / swept_area if swept_area > 0 else 0.0
    else:
        coverage = overlap = spillage = 0.0

    derived_working = stroke_total + head_len
    working = derived_working if working_length is None else float(working_length)

    if total_length is not None:
        # The caller knows its own true total.  This matters because a planner
        # may export a ``path`` that omits the headland loops, in which case
        # measuring the polyline would silently drop that distance.
        total = float(total_length)
    else:
        total = polyline_length(path)
        if total <= 0:
            total = working + (transit_length or 0.0)

    if transit_length is None:
        transit = max(0.0, total - working)
    else:
        transit = float(transit_length)
        if total <= 0:
            total = working + transit

    return {
        "field": field.name,
        "free_area": free_area,
        "coverage": float(coverage),
        "missed": float(max(0.0, 1.0 - coverage)),
        "overlap": float(overlap),
        "spillage": float(spillage),
        "working_length": working,
        "stroke_length": stroke_total,
        "headland_length": head_len,
        "transit_length": transit,
        "total_length": total,
        "non_working_ratio": float(transit / total) if total > 0 else 0.0,
        "n_swaths": len(swaths),
        "headland_measured_from_geometry": working_length is None,
    }


def evaluate(
    field: Field,
    plan: Plan,
    free: G.MultiPolygon | None = None,
) -> CoverageMetrics:
    """Compute every metric for *plan* on *field*.

    Coverage is measured against the swept geometry, not against the stroke
    centrelines, so a stroke that pokes out over an obstacle is correctly
    credited only for the part that lies inside the field.
    """
    width = plan.params.swath_width
    free_geom = free if free is not None else field.free
    free_area = float(free_geom.area)

    bands = [band_area(s, width) for s in plan.strokes if s.length > 0]
    # Each headland loop is buffered on its own.  Concatenating them into one
    # polyline first would add a straight segment joining the end of every loop
    # to the start of the next, and those segments are not driven by anything --
    # on a sixteen-obstacle field they ran to 343 m, straight through the
    # obstacles they connected, and were counted as swept area.
    bands.extend(loop_band(loop, width) for loop in plan.headland_loops if len(loop) >= 2)

    if bands and free_area > 0:
        multiplicity = float(sum(b.area for b in bands))
        swept = unary_union(bands)
        swept_area = float(swept.area)
        covered = swept.intersection(free_geom)
        covered_area = float(covered.area)
        spill_area = float(swept.difference(free_geom).area)
        coverage = covered_area / free_area
        overlap = max(0.0, (multiplicity - swept_area) / free_area)
        spillage = spill_area / swept_area if swept_area > 0 else 0.0
    else:
        coverage = overlap = spillage = 0.0

    # The odometer split is taken from the planner's own route statistics rather
    # than re-derived from the polyline.  Re-deriving it double-counts: the
    # concatenated headland point list contains the straight joins *between*
    # separate loops, and those joins are already inside `transit_length`.
    stroke_total = float(sum(s.length for s in plan.strokes))
    working = float(plan.route_stats.working_length)
    transit = float(plan.route_stats.transit_length)
    headland = max(0.0, working - stroke_total)
    total = working + transit
    path_len = total

    return CoverageMetrics(
        field=field.name,
        field_area=float(field.area),
        free_area=free_area,
        stroke_width=width,
        coverage=float(coverage),
        missed=float(max(0.0, 1.0 - coverage)),
        overlap=float(overlap),
        spillage=float(spillage),
        path_length=float(path_len),
        working_length=working,
        transit_length=transit,
        non_working_ratio=float(transit / total) if total > 0 else 0.0,
        headland_length=headland,
        n_strokes=plan.route_stats.n_strokes,
        n_turns=plan.route_stats.n_turns,
        n_headland_passes=plan.n_headland_passes,
        plan_time=plan.total_time,
        time_free=plan.timings.get("free", 0.0),
        time_heading=plan.timings.get("heading", 0.0),
        time_clip=plan.timings.get("clip", 0.0),
        time_route=plan.timings.get("route", 0.0),
        angle_deg=float(np.degrees(plan.angle)),
    )
