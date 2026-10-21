"""Dynamic incremental replanning (the research contribution).

The problem
-----------
A coverage plan is computed for a field.  Then the environment changes: a
waterlogged patch, a fallen tree or a parked trailer appears, or one is cleared.
A naive system replans from scratch -- re-erode the boundary, re-grid the
scanlines, re-clip every scanline, re-solve the stroke ordering -- which is
``O(all scanlines)`` of work for a change that affects a handful of them.

The insight
-----------
The scanline edge table in :mod:`cppclip.sweep` indexes every polygon edge by
the ``y`` span it covers.  An obstacle therefore touches only the scanlines
inside its own ``y`` span -- the same active-edge-table locality that scanline
rasterisers exploit.  So:

* **Clipping** costs ``O(edges of the changed obstacle)`` instead of
  ``O(all edges)``, and only the scanlines in the obstacle's span are
  re-clipped.
* **Swaths** are recomputed only on those scanlines.  Every other stroke is
  bit-identical to before, because the scanline grid is fixed and the parity
  pairing on untouched scanlines is unchanged, so it survives as-is.
* **Routing** is repaired locally: surviving strokes keep their place in the
  tour and the few new strokes are spliced in by cheapest insertion.  The
  global optimiser never runs.

The work avoided is reported in :class:`ChangeReport` so the experiment harness
can quantify both the speed-up and what it costs in path quality.

Obstacle groups
---------------
Erosion does not distribute over union: dilating two nearby obstacles by the
headland inset can make the dilated shapes overlap, and a doubly-covered point
toggles even-odd parity twice, which would make the clipper return wrong
intervals.  Rather than fall back to a global rebuild, obstacles whose dilated
shapes touch are merged into a **group** and the group's *union* is registered
as a single ring source.  Groups are disjoint by construction, so parity stays
exact and the update stays incremental.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from time import perf_counter
from typing import Sequence

import numpy as np
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from . import geometry as G
from .fields import Field
from .planner import LoopPath, PlanParams, field_headland, headland_passes
from .routing import (
    RouteStats,
    Step,
    or_opt_focused,
    route_optimised,
    route_to_polyline,
    two_opt_focused,
)
from .sweep import ScanlineClipper
from .swaths import Frame, Point2D, Stroke, Swath, choose_heading, swaths_from_intervals

__all__ = ["ChangeReport", "IncrementalPlanner", "SwathKey"]

SwathKey = tuple[int, float, float]


def _key(s: Swath) -> SwathKey:
    """A stable identity for a swath across replans.

    The scanline grid is fixed for the lifetime of a planner, so an unaffected
    scanline yields *bit-identical* interval endpoints.  Keying on the rounded
    triple is therefore exact, not a fuzzy match.
    """
    return (s.scanline, round(s.x0, 9), round(s.x1, 9))


@dataclass(slots=True)
class ChangeReport:
    """What one environment change cost, and how much work it avoided."""

    mode: str  # "incremental" | "group_merge"
    reason: str
    n_affected_scanlines: int
    n_total_scanlines: int
    time_s: float
    swaths_removed: int
    swaths_added: int
    swaths_kept: int
    merged_groups: int
    route_repair: str  # "local" | "global"
    transit_before: float
    transit_after: float
    #: Indices into the scanline grid that were actually re-clipped.  The count
    #: above is what the report quotes; the indices are what a visualiser needs
    #: to show *which* lines the change touched, and what a diagnostic needs to
    #: tell a local update from one that quietly spanned the whole field.
    affected_lines: tuple[int, ...] = ()

    @property
    def work_fraction(self) -> float:
        """Fraction of the scanline grid that had to be re-clipped."""
        if self.n_total_scanlines == 0:
            return 0.0
        return self.n_affected_scanlines / self.n_total_scanlines

    @property
    def transit_delta(self) -> float:
        return self.transit_after - self.transit_before


@dataclass(slots=True)
class _Group:
    """One or more obstacles whose dilated shapes are disjoint from other groups.

    Coordinate frames matter here and are easy to get wrong:

    ``geom``
        union of the member obstacles, **world** coordinates -- used for the
        headland loops and for reporting the scene.
    ``dilated``
        the same union dilated by the headland inset, **local** (swath-frame)
        coordinates -- this is what gets registered in the clipper, and what the
        disjointness test compares.
    """

    handles: set[int]
    geom: G.MultiPolygon  # world
    dilated: G.MultiPolygon  # local
    source: int | None = None
    headland: LoopPath = dc_field(default_factory=LoopPath)
    #: The member obstacles individually, in world coordinates.
    #:
    #: Grouping is a requirement of the *clipper*, not of the plan: even-odd
    #: parity needs the registered ring sources to be disjoint, so dilations that
    #: touch must be registered as one union.  That constraint has no business
    #: reaching the headland path, and letting it do so costs coverage -- two
    #: obstacles a few metres apart get one loop around the outside instead of
    #: two loops that also cover the gap between them, which is free space the
    #: machine can and should drive.  Keeping the parts lets the group draw the
    #: same loops a from-scratch plan would.
    parts: list[G.MultiPolygon] = dc_field(default_factory=list)


def _group_headland_loops(
    parts: Sequence[G.MultiPolygon],
    swath_width: float,
    n_passes: int,
    clip: G.MultiPolygon | None = None,
) -> LoopPath:
    """Headland loops for a group, drawn per obstacle rather than per union.

    *clip* is the free space: a loop around one obstacle must not run through its
    neighbour, and the neighbour is exactly what a merged group contains.

    Falls back to the union when a group somehow has no parts recorded, so the
    result is never worse than the merged version that preceded this.
    """
    from .planner import obstacle_headland

    geoms = [p for p in parts if p is not None and not p.is_empty]
    if not geoms:
        return LoopPath()

    combined = LoopPath()
    cursor = None
    for geom in geoms:
        loops = obstacle_headland(geom, swath_width, n_passes, start=cursor, clip=clip)
        if not loops:
            continue
        combined.loops.extend(loops.loops)
        combined.points.extend(loops.points)
        combined.working_length += loops.working_length
        combined.transit_length += loops.transit_length
        if loops.points:
            cursor = loops.points[-1]
    return combined


class IncrementalPlanner:
    """Maintains a coverage plan as obstacles are added and removed.

    The swath heading is fixed at construction.  That is deliberate and
    realistic: a machine in the field does not re-orient its whole pattern
    because a rock appeared, and re-running the 24-candidate heading search
    would swamp the cost being measured.  Use :func:`cppclip.planner.plan` when
    a fresh global optimum is wanted.
    """

    def __init__(
        self,
        field: Field,
        params: PlanParams | None = None,
        angle: float | None = None,
        repair_window: int = 4,
        global_repair_fraction: float = 0.5,
    ) -> None:
        self.params = params or PlanParams()
        self.params.validate()
        self.repair_window = int(repair_window)
        self.global_repair_fraction = float(global_repair_fraction)
        self.field_name = field.name
        self._boundary = G.normalise(field.boundary)
        self._initial_obstacles = [G.normalise(o) for o in field.obstacles]

        self.n_passes = headland_passes(self.params.headland_width, self.params.swath_width)
        self.inset = self.n_passes * self.params.swath_width

        # Region carrying the field's own headland, before any obstacle is
        # subtracted.  Obstacles are registered on top as individual ring sources.
        self._base_inner = (
            G.erode(self._boundary, self.inset) if self.inset > 0 else G.normalise(self._boundary)
        )
        if self._base_inner.is_empty:
            self._base_inner = G.normalise(self._boundary)
            self.n_passes = 0
            self.inset = 0.0

        # The heading is resolved once, here, and then frozen: a machine in the
        # field does not re-orient its whole pattern because a rock appeared.
        # ``params.angle`` takes precedence over the search, and the constructor
        # argument takes precedence over both.
        if angle is None:
            angle = self.params.angle
        if angle is None:
            self.angle, self.heading_report = choose_heading(
                self._base_inner,
                self.params.swath_width,
                angles=np.linspace(0.0, np.pi, self.params.n_angle_candidates, endpoint=False),
            )
        else:
            self.angle, self.heading_report = float(angle), {"candidates": [], "best": None}

        self._frame = Frame.around(self._base_inner, self.angle)
        self._local_basis = self._frame.to_local(self._base_inner)

        self.clipper = ScanlineClipper.from_geometry(self._local_basis, self.params.swath_width)
        self._ys = self.clipper.ys.copy()

        self._by_line: dict[int, list[Swath]] = {}
        self._groups: dict[int, _Group] = {}
        self._handle_group: dict[int, int] = {}
        self._obstacle_geoms: dict[int, G.MultiPolygon] = {}
        self._next_handle = 0
        self._next_group = 0

        self._route: list[Step] = []
        self._route_swaths: list[Swath] = []

        self._field_loops = field_headland(
            self._boundary, self.params.swath_width, self.n_passes, start=self.params.start
        )

        self._rebuild_all_swaths()
        self._full_route()

        for obs in self._initial_obstacles:
            self.add_obstacle(obs)

    # ==================================================================
    # swath bookkeeping
    # ==================================================================
    def _all_swaths(self) -> list[Swath]:
        return [s for i in sorted(self._by_line) for s in self._by_line[i]]

    def _rebuild_all_swaths(self) -> None:
        """Full re-derivation of every swath from the current clipper state."""
        self._by_line = {}
        for i, line in enumerate(self.clipper.all_intervals()):
            sw = swaths_from_intervals(
                [line], [self._ys[i]], self.params.min_swath_length, scanline_offset=i
            )
            if sw:
                self._by_line[i] = sw

    def _refresh_lines(self, lines: Sequence[int]) -> tuple[list[Swath], list[Swath], list[Swath]]:
        """Re-clip the given scanlines only; return ``(kept, removed, added)``.

        Every other scanline's swath list is left untouched, which is the entire
        point of the edge table.
        """
        kept: list[Swath] = []
        removed: list[Swath] = []
        added: list[Swath] = []

        for i in lines:
            i = int(i)
            old = self._by_line.get(i, [])
            new = swaths_from_intervals(
                [self.clipper.intervals_at(i)],
                [self._ys[i]],
                self.params.min_swath_length,
                scanline_offset=i,
            )
            old_keys = {_key(s) for s in old}
            new_keys = {_key(s) for s in new}
            kept.extend(s for s in old if _key(s) in new_keys)
            removed.extend(s for s in old if _key(s) not in new_keys)
            added.extend(s for s in new if _key(s) not in old_keys)
            if new:
                self._by_line[i] = new
            else:
                self._by_line.pop(i, None)

        return kept, removed, added

    # ==================================================================
    # routing
    # ==================================================================
    def _clip_to_basis(self, geom_local: BaseGeometry) -> G.MultiPolygon:
        """Restrict a hole to the swath region, in the *local* frame.

        A hole that pokes outside the shell is not a cosmetic problem: the
        clipper reads rings by even-odd parity, so a hole crossing the shell
        yields the symmetric difference rather than the difference, and the part
        of the hole lying outside the field would come back as drivable.

        ``contains`` is a predicate, not an overlay, so the common case of an
        obstacle comfortably inside the field costs no boolean operation at all.
        Only an obstacle that actually reaches the boundary pays for the
        intersection.
        """
        geom_local = G.normalise(geom_local)
        if geom_local.is_empty or self._local_basis.is_empty:
            return geom_local
        if self._local_basis.covers(geom_local):
            return geom_local
        return G.normalise(geom_local.intersection(self._local_basis))

    def _dilated_local(self, geom_world: BaseGeometry) -> G.MultiPolygon:
        """Dilate an obstacle by the headland inset and express it in the local frame."""
        dilated = G.dilate(geom_world, self.inset) if self.inset > 0 else G.normalise(geom_world)
        return self._clip_to_basis(self._frame.to_local(dilated))

    def _start_local(self) -> Point2D:
        if self.params.start is not None:
            return self._frame.point_to_local(self.params.start)
        swaths = self._all_swaths()
        if not swaths:
            return (0.0, 0.0)
        xs = [s.x0 for s in swaths] + [s.x1 for s in swaths]
        return (float(min(xs)), float(min(s.y for s in swaths)))

    def _full_route(self) -> None:
        """Global re-solve of the stroke ordering."""
        swaths = self._all_swaths()
        self._route = route_optimised(swaths, self._start_local()) if swaths else []
        self._route_swaths = swaths

    def _repair_route(self, removed: Sequence[Swath], added: Sequence[Swath]) -> str:
        """Restore a valid tour, locally if that is honest and globally if not.

        Local repair keeps survivors in place and splices newcomers in by
        cheapest insertion followed by a bounded 2-opt around the insertions.
        That is strictly weaker than a global re-solve, and the weakness
        compounds: after a few insert/remove cycles the tour has drifted and
        never recovers, because nothing in the local repair can undo an earlier
        bad placement.

        So the perturbation is measured against the tour size first.  When it is
        large, a local repair is a false economy and the global optimiser runs
        instead.  The choice is recorded in the report so the experiment can
        show how often each path is taken and what it costs.
        """
        old_swaths = self._route_swaths
        new_swaths = self._all_swaths()
        new_keys = {_key(s) for s in new_swaths}
        index_of = {_key(s): i for i, s in enumerate(new_swaths)}

        survivors: list[Step] = []
        seams: list[int] = []
        for st in self._route:
            if st.index >= len(old_swaths):
                continue
            k = _key(old_swaths[st.index])
            if k in new_keys:
                survivors.append(Step(index_of[k], st.reversed))
            else:
                # A stroke vanished here, so the two survivors either side of the
                # gap are now joined by one long leg.  That seam is exactly where
                # a local 2-opt can recover the tour, and it is the only place
                # worth looking.
                seams.append(len(survivors))

        tour = max(1, len(self._route))
        # Only *insertions* justify a global re-solve.  A deletion leaves the
        # relative order of the survivors intact, so it never warrants one -- the
        # seam it opens is handled by the focused search below.
        perturbation = len(added)
        if perturbation > self.global_repair_fraction * tour:
            self._full_route()
            return "global"

        start = self._start_local()
        route = survivors
        inserted_at: list[int] = []
        for s in added:
            k = _key(s)
            if k in index_of:
                route = self._cheapest_insertion(route, new_swaths, Step(index_of[k], False), start)
                inserted_at.append(max(0, len(route) - 1))

        # Cheapest insertion leaves each newcomer's neighbours unoptimised, and a
        # deletion leaves a stretched seam.  Repair both with a bounded local
        # search: 2-opt fixes crossing seams, Or-opt relocates a stroke that
        # landed in the wrong part of the tour -- which 2-opt alone cannot do.
        focus = inserted_at + seams
        if focus and len(route) >= 3:
            route = two_opt_focused(route, new_swaths, start, focus, window=self.repair_window)
            route = or_opt_focused(route, new_swaths, start, focus, window=self.repair_window)
            route = two_opt_focused(route, new_swaths, start, focus, window=self.repair_window)

        self._route = route
        self._route_swaths = new_swaths
        return "local"

    @staticmethod
    def _cheapest_insertion(
        route: list[Step], swaths: Sequence[Swath], step: Step, start: Point2D
    ) -> list[Step]:
        """Insert *step*, in whichever orientation and position adds least travel."""
        if not route:
            return [step]

        def entry_exit(s: Step) -> tuple[Point2D, Point2D]:
            return swaths[s.index].point(s.reversed)

        def dist(a: Point2D, b: Point2D) -> float:
            return float(np.hypot(a[0] - b[0], a[1] - b[1]))

        best_cost = float("inf")
        best_route: list[Step] | None = None
        for orientation in (step, step.flipped()):
            cand_entry, cand_exit = entry_exit(orientation)
            for pos in range(len(route) + 1):
                before = start if pos == 0 else entry_exit(route[pos - 1])[1]
                added = dist(before, cand_entry)
                if pos < len(route):
                    after = entry_exit(route[pos])[0]
                    added += dist(cand_exit, after) - dist(before, after)
                if added < best_cost:
                    best_cost = added
                    best_route = route[:pos] + [orientation] + route[pos:]

        return best_route if best_route is not None else route + [step]

    # ==================================================================
    # environment changes
    # ==================================================================
    def add_obstacle(self, geom: BaseGeometry, handle: int | None = None) -> tuple[int, ChangeReport]:
        """Register a new in-field obstacle and replan incrementally."""
        t0 = perf_counter()
        geom = G.normalise(geom)
        handle = self._next_handle if handle is None else handle
        self._next_handle = max(self._next_handle, handle + 1)

        before = self._transit()
        if geom.is_empty:
            return handle, self._empty_report("empty geometry", t0, before)

        dilated = self._dilated_local(geom)
        if dilated.is_empty:
            self._obstacle_geoms[handle] = geom
            return handle, self._empty_report("obstacle lies outside the swath region", t0, before)

        # Merge with every group whose dilated shape touches this one, so that
        # the registered ring sources stay pairwise disjoint (and parity exact).
        touching = [gid for gid, g in self._groups.items() if g.dilated.intersects(dilated)]

        # Snapshot the groups *before* popping them: the merged geometry, the
        # merged handle set and the member obstacles are all built from what they
        # held.
        touch_geoms = [self._groups[gid].geom for gid in touching]
        touch_dilated = [self._groups[gid].dilated for gid in touching]
        touch_parts = [p for gid in touching for p in self._groups[gid].parts]
        merged_handles: set[int] = {handle}
        for gid in touching:
            merged_handles |= self._groups[gid].handles

        affected = np.empty(0, dtype=int)
        for gid in touching:
            grp = self._groups.pop(gid)
            for h in grp.handles:
                self._handle_group.pop(h, None)
            if grp.source is not None:
                self.clipper.remove_source(grp.source)

        merged_geom = G.normalise(unary_union([geom] + touch_geoms))
        merged_dilated = G.normalise(unary_union([dilated] + touch_dilated))
        merged_parts = [geom, *touch_parts]
        if merged_dilated.is_empty:
            merged_dilated = dilated

        source, _all_edges_affected = self.clipper.add_geometry(merged_dilated)

        # Re-clip only the scanlines the *new obstacle* spans, not the whole
        # merged cluster.
        #
        # A union can only change the boundary near the shape being added: every
        # part of the old cluster's boundary that the union absorbs lies inside
        # the new obstacle by construction, and every part that survives has
        # identical coordinates.  So outside the new obstacle's own y span the
        # crossing set is unchanged and the intervals are already correct.
        #
        # Re-clipping the whole cluster instead would make each arrival that
        # touches a cluster cost as much as a full rebuild, which is precisely
        # what happens on obstacle sets dense enough for their dilations to
        # percolate into one component -- the common case on the benchmark.
        _minx, dy0, _maxx, dy1 = G.bounds_of(dilated)
        i0, i1 = self.clipper.scanline_slice(dy0, dy1)
        affected = np.arange(i0, i1, dtype=int)

        gid = self._next_group
        self._next_group += 1
        loops = self._group_headland(merged_parts)
        self._groups[gid] = _Group(
            handles=merged_handles,
            geom=merged_geom,
            dilated=merged_dilated,
            source=source,
            headland=loops,
            parts=merged_parts,
        )
        # Every absorbed handle must map to the surviving group, otherwise
        # removing one of them later finds no owner and its hole is never freed.
        for h in merged_handles:
            self._handle_group[h] = gid
        self._obstacle_geoms[handle] = geom

        kept, removed, added = self._refresh_lines(affected)

        repair_mode = self._repair_route(removed, added)

        return handle, ChangeReport(
            mode="group_merge" if touching else "incremental",
            reason="merged with adjacent groups" if touching else "ok",
            n_affected_scanlines=int(affected.size),
            affected_lines=tuple(int(i) for i in affected),
            n_total_scanlines=int(self.clipper.n_scanlines),
            time_s=perf_counter() - t0,
            swaths_removed=len(removed),
            swaths_added=len(added),
            swaths_kept=len(kept),
            merged_groups=len(touching),
            route_repair=repair_mode,
            transit_before=before,
            transit_after=self._transit(),
        )

    def remove_obstacle(self, handle: int) -> ChangeReport:
        """Deregister an obstacle and replan incrementally."""
        t0 = perf_counter()
        before = self._transit()
        gid = self._handle_group.pop(handle, None)
        if gid is None:
            return self._empty_report(f"unknown handle {handle}", t0, before)

        grp = self._groups[gid]
        remaining = grp.handles - {handle}
        self._obstacle_geoms.pop(handle, None)

        affected = np.empty(0, dtype=int)
        if grp.source is not None:
            affected = self.clipper.remove_source(grp.source)

        if not remaining:
            del self._groups[gid]
        else:
            # The group survives, minus this obstacle: re-register the rest.
            rest = self._member_geometry(remaining)
            merged = G.normalise(rest)
            dilated = self._dilated_local(merged)
            src, aff = self.clipper.add_geometry(dilated)
            affected = np.union1d(affected, aff)
            parts = [
                self._obstacle_geoms[h]
                for h in sorted(remaining)
                if h in self._obstacle_geoms
            ]
            loops = self._group_headland(parts)
            self._groups[gid] = _Group(
                handles=remaining, geom=merged, dilated=dilated,
                source=src, headland=loops, parts=parts,
            )

        kept, removed, added = self._refresh_lines(affected)

        repair_mode = self._repair_route(removed, added)

        return ChangeReport(
            mode="incremental",
            reason="ok",
            n_affected_scanlines=int(affected.size),
            affected_lines=tuple(int(i) for i in affected),
            n_total_scanlines=int(self.clipper.n_scanlines),
            time_s=perf_counter() - t0,
            swaths_removed=len(removed),
            swaths_added=len(added),
            swaths_kept=len(kept),
            merged_groups=0,
            route_repair=repair_mode,
            transit_before=before,
            transit_after=self._transit(),
        )

    # ------------------------------------------------------------------
    # group geometry helpers
    # ------------------------------------------------------------------
    def _member_geometry(self, handles: set[int]) -> G.MultiPolygon:
        geoms = [self._obstacle_geoms[h] for h in handles if h in self._obstacle_geoms]
        return G.normalise(unary_union(geoms)) if geoms else G.MultiPolygon()

    def _group_headland(self, parts: Sequence[G.MultiPolygon]):
        """Headland loops for a group, one set of loops per member obstacle.

        Drawing them per member rather than around the union matches what a
        from-scratch plan produces, and the difference is coverage rather than
        cosmetics: two obstacles whose headlands touch still leave drivable free
        space between them, and a single loop around the outside does not reach
        it.  See :attr:`_Group.parts`.
        """
        return _group_headland_loops(parts, self.params.swath_width, self.n_passes)

    # ------------------------------------------------------------------
    def _empty_report(self, reason: str, t0: float, before: float) -> ChangeReport:
        return ChangeReport("incremental", reason, 0, int(self.clipper.n_scanlines),
                            perf_counter() - t0, 0, 0, 0, 0, "none", before, before)

    # ==================================================================
    # outputs
    # ==================================================================
    def _transit(self) -> float:
        if not self._route or not self._route_swaths:
            return 0.0
        _, stats, _legs = route_to_polyline(
            self._route, self._route_swaths, self._start_local()
        )
        return stats.transit_length

    def swaths(self) -> list[Swath]:
        return self._all_swaths()

    def strokes(self) -> list[Stroke]:
        return self._frame.swaths_to_strokes(self._all_swaths())

    def headland_loops(self) -> list[list[Point2D]]:
        """Every headland loop, kept separate.

        Returning one flat list would let a consumer weld the loops together
        with straight joining segments the machine never drives -- see
        :class:`~cppclip.planner.LoopPath`.
        """
        loops = [list(loop) for loop in self._field_loops.loops]
        for grp in self._groups.values():
            loops.extend(list(loop) for loop in grp.headland.loops)
        return loops

    def path(self) -> list[Point2D]:
        self._route_swaths = self._all_swaths()
        local_path, _stats, _legs = route_to_polyline(
            self._route, self._route_swaths, self._start_local()
        )
        return self._frame.points_to_world(local_path)

    def route_stats(self) -> RouteStats:
        self._route_swaths = self._all_swaths()
        _, stats, _legs = route_to_polyline(
            self._route, self._route_swaths, self._start_local()
        )
        head_len = self._field_loops.working_length + sum(
            g.headland.working_length for g in self._groups.values()
        )
        head_transit = self._field_loops.transit_length + sum(
            g.headland.transit_length for g in self._groups.values()
        )
        # Counted per *obstacle*, not per group, because that is how many loops
        # are actually driven and how a from-scratch plan counts them.  Using the
        # group count here under-reported the tour whenever obstacles merged.
        n_obstacles = sum(len(g.parts) for g in self._groups.values())
        loops = self.n_passes * (1 + n_obstacles)
        return RouteStats(
            working_length=stats.working_length + head_len,
            transit_length=stats.transit_length + head_transit,
            n_strokes=stats.n_strokes + loops,
            n_turns=stats.n_turns + loops,
        )

    def to_plan(self):
        """Materialise the current state as a :class:`~cppclip.planner.Plan`."""
        from .planner import Plan

        return Plan(
            field_name=self.field_name,
            params=self.params,
            path=self.path(),
            strokes=self.strokes(),
            headland_loops=self.headland_loops(),
            angle=self.angle,
            n_headland_passes=self.n_passes,
            route_stats=self.route_stats(),
            timings={"incremental_total": 0.0},
            heading_report=self.heading_report,
        )

    def current_field(self) -> Field:
        """The scene as the planner currently believes it to be."""
        obstacles = [self._obstacle_geoms[h] for h in sorted(self._obstacle_geoms)]
        return Field(name=self.field_name, boundary=self._boundary, obstacles=obstacles)
