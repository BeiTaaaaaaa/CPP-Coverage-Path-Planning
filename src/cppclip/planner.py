"""The end-to-end planning pipeline.

``field + parameters -> coverage path``, decomposed into timed stages so that
the experiment harness can attribute cost to each one:

============  ==========================================================
stage         what it does
============  ==========================================================
``free``      boundary minus obstacles (one GEOS overlay)
``headland``  concentric inward offsets forming the 地头 ring
``heading``   search over swath headings
``clip``      scanline edge table -> effective intervals  (the core)
``swaths``    intervals -> working strokes
``route``     stroke ordering (boustrophedon baseline or optimiser)
``turns``     transit legs, straight or Dubins
============  ==========================================================

No cell decomposition appears anywhere in this pipeline: the scanline clipper
subsumes it.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from time import perf_counter
from typing import Sequence

import numpy as np
from shapely.geometry import LineString, MultiLineString, Point
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from . import geometry as G
from .fields import Field
from .routing import RouteStats, route_boustrophedon, route_greedy, route_optimised, route_to_polyline
from .sweep import ScanlineClipper
from .swaths import (
    Frame,
    Point2D,
    Stroke,
    Swath,
    choose_heading,
    swaths_from_clipper,
)

__all__ = ["PlanParams", "Plan", "plan", "headland_passes", "inner_region", "LoopPath"]


@dataclass(slots=True)
class PlanParams:
    """Coverage planning parameters, all lengths in metres."""

    swath_width: float = 6.0
    headland_width: float = 6.0
    angle: float | None = None
    n_angle_candidates: int = 24
    route: str = "optimised"  # "boustrophedon" | "greedy" | "optimised"
    min_swath_length: float = 1.0
    start: Point2D | None = None
    turn_radius: float = 0.0
    """Minimum turning radius in metres.  ``0`` joins strokes with straight
    transit legs; a positive value replaces each leg with the Dubins path
    between the two strokes' poses, which is what makes the driven distance
    comparable with a planner that models turn curvature."""

    def validate(self) -> None:
        if self.swath_width <= 0:
            raise ValueError("swath_width must be positive")
        if self.headland_width < 0:
            raise ValueError("headland_width must be non-negative")
        if self.turn_radius < 0:
            raise ValueError("turn_radius must be non-negative")
        if self.route not in {"boustrophedon", "greedy", "optimised"}:
            raise ValueError(f"unknown route strategy: {self.route!r}")


@dataclass(slots=True)
class Plan:
    """The result of :func:`plan`, with per-stage timings for the evaluation."""

    field_name: str
    params: PlanParams
    path: list[Point2D]  # world coordinates, working strokes + transit legs
    strokes: list[Stroke]  # working strokes, in world coordinates
    headland_loops: list[list[Point2D]]
    n_headland_passes: int
    route_stats: RouteStats
    angle: float = 0.0
    #: Polyline for each repositioning leg, kept apart from ``path`` so a
    #: visualiser can draw the transit without tracing over the strokes.
    transit_legs: list[list[Point2D]] = dc_field(default_factory=list)
    timings: dict[str, float] = dc_field(default_factory=dict)
    heading_report: dict = dc_field(default_factory=dict)

    @property
    def total_time(self) -> float:
        return float(sum(self.timings.values()))

    def working_linework(self) -> MultiLineString:
        return MultiLineString(
            [[(s.x0, s.y), (s.x1, s.y)] for s in self.strokes]
        ) if self.strokes else MultiLineString()

    def path_linework(self) -> LineString:
        return LineString(self.path) if len(self.path) >= 2 else LineString()


# --------------------------------------------------------------------------
# headland
# --------------------------------------------------------------------------
@dataclass(slots=True)
class LoopPath:
    """A set of headland loops joined into one drivable sequence.

    The distinction between the two lengths is not bookkeeping pedantry.  A
    multi-loop headland (which is what a field with holes, or a pinched inward
    offset, produces) is several separate loops, and driving from one to the next
    is *transit* -- the implement is up.  Folding those joins into the working
    length inflates it by 71-260 m per field on the benchmark data and makes the
    working-length comparison against another planner wrong.

    ``loops`` holds each loop separately for the same reason, and it is the
    attribute consumers should use.  ``points`` is the concatenation, kept only
    because the lengths are accumulated while walking it; anything that treats it
    as a single polyline -- drawing it, or buffering it into a swept area --
    **invents straight segments joining one loop to the next** that no machine
    ever drives.  On a field with sixteen obstacles those phantom joins ran to
    343 m, straight through the obstacles they connected.
    """

    loops: list[list[Point2D]] = dc_field(default_factory=list)
    points: list[Point2D] = dc_field(default_factory=list)
    working_length: float = 0.0  # distance driven along the loops
    transit_length: float = 0.0  # distance driven between separate loops

    @property
    def total_length(self) -> float:
        return self.working_length + self.transit_length

    def __bool__(self) -> bool:
        return bool(self.points)


def headland_passes(headland_width: float, swath_width: float) -> int:
    """Number of concentric passes needed to cover a headland of that width."""
    if headland_width <= 0:
        return 0
    return int(np.ceil(headland_width / swath_width))


def field_headland(
    boundary: BaseGeometry,
    swath_width: float,
    n_passes: int,
    start: Point2D | None = None,
    clip: BaseGeometry | None = None,
) -> LoopPath:
    """Headland loops that follow the *field boundary* only.

    *clip* is the region the loops may occupy -- normally the free space, so a
    boundary loop that would clip a corner of an obstacle is cut there instead of
    driving through it.
    """
    return _rings_to_path(G.normalise(boundary), swath_width, n_passes, start, clip=clip)


def obstacle_headland(
    obstacle: BaseGeometry,
    swath_width: float,
    n_passes: int,
    start: Point2D | None = None,
    clip: BaseGeometry | None = None,
) -> LoopPath:
    """Headland loops around a single obstacle.

    Pass *i* runs on the *outward* offset at ``(i + 0.5) * swath_width``, i.e.
    on the boundary of ``dilate(obstacle, (i+0.5)w)``.  Because this depends
    only on the obstacle, adding or removing an obstacle costs one local buffer
    per pass instead of a global re-erosion of the whole field.

    *clip* must be the free space, which is what keeps a loop around one obstacle
    from running through its neighbour.  The ring itself is computed from the
    obstacle alone; it is the cutting that involves the neighbours, and that
    keeps the update local in the common case where nothing is near by.
    """
    obstacle = G.normalise(obstacle)
    if obstacle.is_empty or n_passes <= 0:
        return LoopPath()
    return _rings_to_path(_Outward(obstacle), swath_width, n_passes, start, clip=clip)


class _Outward:
    """Adapter so :func:`_rings_to_path` can drive either offset direction."""

    __slots__ = ("geom",)

    def __init__(self, geom: BaseGeometry) -> None:
        self.geom = geom


def _boxes_within(a: BaseGeometry, b: BaseGeometry, reach: float) -> bool:
    """Cheap bounding-box test for "could these two come within *reach*?"."""
    ax0, ay0, ax1, ay1 = a.bounds
    bx0, by0, bx1, by1 = b.bounds
    return not (
        ax0 - reach > bx1 or bx0 - reach > ax1 or ay0 - reach > by1 or by0 - reach > ay1
    )


def headland_clip(
    boundary: BaseGeometry,
    subject: BaseGeometry,
    others: Sequence[BaseGeometry],
    n_passes: int,
    swath_width: float,
) -> BaseGeometry:
    """The region a headland loop around *subject* is allowed to occupy.

    The loop is the boundary of ``dilate(subject, (i+0.5)w)``, which reaches at
    most ``n_passes * swath_width`` beyond the obstacle.  So only neighbours
    within that distance can obstruct it, and only those need subtracting -- the
    result is identical to subtracting every obstacle, at a cost that does not
    grow with the obstacle count.

    The field boundary is always part of the clip, so a loop around an obstacle
    near the edge stops at the edge instead of running outside the field.
    """
    region = G.normalise(boundary)
    reach = max(0.0, n_passes * swath_width)
    near = [
        o
        for o in others
        if o is not None and not o.is_empty and _boxes_within(o, subject, reach)
    ]
    if near:
        region = region.difference(G.normalise(unary_union(near)))
    return region


def _iter_lines(geom: BaseGeometry):
    """Yield the individual ``LineString`` pieces of any line-ish geometry."""
    from shapely.geometry import LineString

    if geom is None or geom.is_empty:
        return
    if isinstance(geom, LineString):
        yield geom
        return
    for part in G.iter_geometries(geom):
        if isinstance(part, LineString) and not part.is_empty:
            yield part


def _ring_pieces(ring_geom: BaseGeometry, clip: BaseGeometry | None) -> list[list[Point2D]]:
    """The boundary rings of *ring_geom*, cut down to the parts inside *clip*.

    A headland ring is a closed curve, and a closed curve that runs through an
    obstacle is not drivable.  Cutting it leaves an open path ending at the
    obstacle's edge, which is what the machine actually does: it drives the
    headland up to the obstruction and then moves on to the next loop.
    """
    from shapely.geometry import LineString

    pieces: list[list[Point2D]] = []
    for poly in G.iter_polygons(ring_geom):
        rings = [poly.exterior, *poly.interiors]
        for ring in rings:
            line: BaseGeometry = LineString(ring.coords)
            if clip is not None:
                line = line.intersection(clip)
            for part in _iter_lines(line):
                coords = [(float(x), float(y)) for x, y in part.coords]
                if len(coords) >= 2:
                    pieces.append(coords)
    return pieces


def _rings_to_path(
    source: BaseGeometry | _Outward,
    swath_width: float,
    n_passes: int,
    start: Point2D | None,
    clip: BaseGeometry | None = None,
) -> LoopPath:
    """Walk the concentric offset rings of *source* in nearest-neighbour order.

    *clip* is the free space the headland is allowed to occupy.  Rings are cut to
    it, so a loop that would cross an obstacle or leave the field becomes an open
    path that stops at the boundary instead of driving through.
    """
    if n_passes <= 0:
        return LoopPath()

    outward = isinstance(source, _Outward)
    base = source.geom if outward else source

    out = LoopPath()
    cursor = start
    started = False

    for i in range(n_passes):
        offset = (i + 0.5) * swath_width
        ring_geom = G.dilate(base, offset) if outward else G.erode(base, offset)
        if ring_geom.is_empty:
            break

        remaining = _ring_pieces(ring_geom, clip)
        while remaining:
            # Pick the piece whose nearer end is closest to the cursor, and
            # enter it from that end.  A closed ring can additionally be rotated
            # to start beside the cursor; an open path cannot, because its
            # endpoints are where it was cut.
            best_k, best_d, best_reverse = 0, float("inf"), False
            for k, piece in enumerate(remaining):
                if cursor is None:
                    best_k, best_d, best_reverse = k, 0.0, False
                    break
                d0 = float(np.hypot(piece[0][0] - cursor[0], piece[0][1] - cursor[1]))
                d1 = float(np.hypot(piece[-1][0] - cursor[0], piece[-1][1] - cursor[1]))
                if d1 < d0:
                    if d1 < best_d:
                        best_d, best_k, best_reverse = d1, k, True
                elif d0 < best_d:
                    best_d, best_k, best_reverse = d0, k, False

            piece = remaining.pop(best_k)
            if best_reverse:
                piece = piece[::-1]
            is_closed = piece[0] == piece[-1]
            if is_closed and cursor is not None and len(piece) > 2:
                best_rot = min(
                    range(len(piece) - 1),
                    key=lambda r: (piece[r][0] - cursor[0]) ** 2
                    + (piece[r][1] - cursor[1]) ** 2,
                )
                if best_rot:
                    piece = piece[best_rot:] + piece[1 : best_rot + 1]

            if started and cursor is not None:
                # Getting to the next loop is repositioning, not coverage.
                out.transit_length += float(
                    np.hypot(piece[0][0] - cursor[0], piece[0][1] - cursor[1])
                )
            out.loops.append(piece)
            out.points.extend(piece)
            for a, b in zip(piece[:-1], piece[1:]):
                out.working_length += float(np.hypot(b[0] - a[0], b[1] - a[1]))
            cursor = piece[-1]
            started = True

    return out


def inner_region(
    boundary: BaseGeometry,
    obstacles: Sequence[BaseGeometry],
    headland_width: float,
    swath_width: float,
) -> tuple[G.MultiPolygon, int]:
    """The area the swath pattern must tile: boundary eroded, obstacles dilated.

    Returns ``(inner, n_headland_passes)``.  This is `plan()`'s definition of
    the swath region, exposed so the incremental planner and the experiment
    harness can compute it without duplicating the arithmetic.
    """
    boundary = G.normalise(boundary)
    n_passes = headland_passes(headland_width, swath_width)
    if n_passes <= 0 or boundary.is_empty:
        return boundary, 0
    inset = n_passes * swath_width
    inner = G.erode(boundary, inset)
    for obs in obstacles:
        obs = G.normalise(obs)
        if obs.is_empty:
            continue
        inner = G.normalise(inner.difference(G.dilate(obs, inset)))
    return inner, n_passes


# --------------------------------------------------------------------------
# main entry point
# --------------------------------------------------------------------------
def plan(field: Field, params: PlanParams | None = None) -> Plan:
    """Plan a coverage path for *field*.

    The field is rotated so that swaths run along the local x axis, planned
    there, then rotated back.  Working strokes are returned in world
    coordinates so that metrics and plots never have to know about the frame.
    """
    params = params or PlanParams()
    params.validate()
    timings: dict[str, float] = {}

    t = perf_counter()
    free = field.free
    timings["free"] = perf_counter() - t
    if free.is_empty:
        return Plan(
            field_name=field.name,
            params=params,
            path=[],
            strokes=[],
            headland_loops=[],
            angle=0.0,
            n_headland_passes=0,
            route_stats=RouteStats(0.0, 0.0, 0, 0),
            timings=timings,
        )

    n_passes = headland_passes(params.headland_width, params.swath_width)

    t = perf_counter()
    inner, n_passes = inner_region(
        field.boundary, field.obstacles, params.headland_width, params.swath_width
    )
    timings["headland"] = perf_counter() - t
    if inner.is_empty:
        inner = free
        n_passes = 0

    # ---- swath heading -------------------------------------------------
    t = perf_counter()
    if params.angle is None:
        angle, report = choose_heading(
            inner, params.swath_width, angles=np.linspace(0.0, np.pi, params.n_angle_candidates, endpoint=False)
        )
    else:
        angle, report = float(params.angle), {"candidates": [], "best": None}
    frame = Frame.around(inner, angle)
    timings["heading"] = perf_counter() - t

    # ---- clipping (the core) -------------------------------------------
    t = perf_counter()
    local_inner = frame.to_local(inner)
    clip = ScanlineClipper.from_geometry(local_inner, params.swath_width)
    local_swaths = swaths_from_clipper(clip, min_length=params.min_swath_length)
    timings["clip"] = perf_counter() - t

    # ---- routing --------------------------------------------------------
    t = perf_counter()
    start_local = frame.point_to_local(params.start) if params.start is not None else _default_start(local_swaths)
    if params.route == "boustrophedon":
        route = route_boustrophedon(local_swaths)
    elif params.route == "greedy":
        route = route_greedy(local_swaths, start_local)
    else:
        route = route_optimised(local_swaths, start_local)
    local_path, route_stats, transit_legs = route_to_polyline(
        route, local_swaths, start_local, radius=params.turn_radius
    )
    timings["route"] = perf_counter() - t

    # ---- rotate back to world, build headland ---------------------------
    t = perf_counter()
    strokes = frame.swaths_to_strokes(local_swaths)
    world_path = frame.points_to_world(local_path)
    timings["rotate"] = perf_counter() - t

    t = perf_counter()
    # Every headland loop is cut to the space it is actually allowed to occupy,
    # so no part of the headland path drives through an obstacle or leaves the
    # field.  Without this a loop around one obstacle runs straight through its
    # neighbour, and a boundary loop clips the corner off any obstacle near the
    # edge.
    field_loops = field_headland(
        field.boundary,
        params.swath_width,
        n_passes,
        start=params.start,
        clip=headland_clip(field.boundary, field.boundary, field.obstacles, n_passes, params.swath_width),
    )
    head_loops = list(field_loops.loops)
    head_len = field_loops.working_length
    head_transit = field_loops.transit_length
    cursor = field_loops.points[-1] if field_loops.points else params.start
    for k, obs in enumerate(field.obstacles):
        others = [o for j, o in enumerate(field.obstacles) if j != k]
        loops = obstacle_headland(
            obs,
            params.swath_width,
            n_passes,
            start=cursor,
            clip=headland_clip(field.boundary, obs, others, n_passes, params.swath_width),
        )
        if loops:
            head_loops.extend(loops.loops)
            head_len += loops.working_length
            head_transit += loops.transit_length
            cursor = loops.points[-1]
    timings["headland_path"] = perf_counter() - t

    stats = RouteStats(
        working_length=route_stats.working_length + head_len,
        transit_length=route_stats.transit_length + head_transit,
        n_strokes=route_stats.n_strokes + n_passes * (1 + len(field.obstacles)),
        n_turns=route_stats.n_turns + n_passes * (1 + len(field.obstacles)),
    )

    return Plan(
        field_name=field.name,
        params=params,
        path=world_path,
        strokes=strokes,
        headland_loops=head_loops,
        transit_legs=transit_legs,
        angle=angle,
        n_headland_passes=n_passes,
        route_stats=stats,
        timings=timings,
        heading_report=report,
    )


def _default_start(swaths: Sequence[Swath]) -> Point2D:
    """Enter the field at the corner of the first stroke."""
    if not swaths:
        return (0.0, 0.0)
    xs = [s.x0 for s in swaths] + [s.x1 for s in swaths]
    ys = [s.y for s in swaths]
    return (float(min(xs)), float(min(ys)))
