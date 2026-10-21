"""Ordering the working strokes, and turning an order into a drivable path.

The routing problem here is the one Fields2Cover and ``field-coverage`` also
solve, and it is the reason coverage planning is not just "sort the stripes":
each stroke is a *segment* that may be driven in either direction, so choosing
an order means choosing an orientation too.  That makes it a Generalised TSP
(GTSP) rather than a plain TSP.

Two solvers are provided:

``route_boustrophedon``
    The classic field pattern, recovered from the interval set with no cell
    decomposition.  It is the baseline the optimiser has to beat.
``route_optimised``
    Nearest-endpoint greedy seeding, then 2-opt and Or-opt.

The 2-opt move on oriented segments is worth spelling out, because the naive
version is silently wrong: reversing a sub-sequence also has to flip the travel
direction of every stroke inside it, so that the sub-path is traversed
backwards.  :func:`two_opt` does both.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from .swaths import Point2D, Swath

__all__ = [
    "Step",
    "RouteStats",
    "route_boustrophedon",
    "route_greedy",
    "two_opt",
    "two_opt_focused",
    "or_opt",
    "or_opt_focused",
    "route_optimised",
    "route_cost",
    "route_to_polyline",
]


@dataclass(slots=True)
class Step:
    """One stroke in a route: which swath, and which way along it."""

    index: int
    reversed: bool = False

    def flipped(self) -> "Step":
        return Step(self.index, not self.reversed)


@dataclass(slots=True)
class RouteStats:
    working_length: float
    transit_length: float
    n_strokes: int
    n_turns: int

    @property
    def total_length(self) -> float:
        return self.working_length + self.transit_length

    @property
    def non_working_ratio(self) -> float:
        total = self.total_length
        return self.transit_length / total if total > 0 else 0.0


def _dist(a: Point2D, b: Point2D) -> float:
    return float(np.hypot(a[0] - b[0], a[1] - b[1]))


def _entry_exit(swaths: Sequence[Swath], step: Step) -> tuple[Point2D, Point2D]:
    return swaths[step.index].point(step.reversed)


def route_cost(route: Sequence[Step], swaths: Sequence[Swath], start: Point2D) -> float:
    """Total non-working distance of a route starting at *start*."""
    if not route:
        return 0.0
    total = 0.0
    cursor = start
    for step in route:
        entry, exit_ = _entry_exit(swaths, step)
        total += _dist(cursor, entry)
        cursor = exit_
    return total


# --------------------------------------------------------------------------
# baselines
# --------------------------------------------------------------------------
def route_boustrophedon(swaths: Sequence[Swath]) -> list[Step]:
    """Classic back-and-forth ordering over the scanline grid.

    Scanlines are visited in ``y`` order and the travel direction alternates, so
    consecutive strokes meet at a shared side of the field.  Multiple intervals
    on one scanline (the case created by obstacles and concavity) are driven in
    the current sweep direction, which is what a human operator would do.
    """
    by_line: dict[int, list[int]] = defaultdict(list)
    for k, s in enumerate(swaths):
        by_line[s.scanline].append(k)

    route: list[Step] = []
    for parity, line in enumerate(sorted(by_line)):
        members = sorted(by_line[line], key=lambda k: swaths[k].x0)
        left_to_right = parity % 2 == 0
        if not left_to_right:
            members = members[::-1]
        for k in members:
            route.append(Step(k, reversed=not left_to_right))
    return route


def route_greedy(swaths: Sequence[Swath], start: Point2D) -> list[Step]:
    """Nearest-endpoint greedy: repeatedly take the cheapest reachable stroke."""
    n = len(swaths)
    if n == 0:
        return []
    remaining = set(range(n))
    route: list[Step] = []
    cursor = start
    while remaining:
        best_k = -1
        best_rev = False
        best_d = float("inf")
        for k in remaining:
            entry_l, exit_l = swaths[k].point(False)
            d_fwd = _dist(cursor, entry_l)
            if d_fwd < best_d:
                best_d, best_k, best_rev = d_fwd, k, False
            d_rev = _dist(cursor, exit_l)
            if d_rev < best_d:
                best_d, best_k, best_rev = d_rev, k, True
        remaining.discard(best_k)
        route.append(Step(best_k, best_rev))
        cursor = _entry_exit(swaths, route[-1])[1]
    return route


# --------------------------------------------------------------------------
# local search
# --------------------------------------------------------------------------
def _points(route: Sequence[Step], swaths: Sequence[Swath], start: Point2D):
    """Entry/exit arrays plus the two leg-cost vectors, for vectorised deltas.

    ``d_prev[k]`` is the distance from the previous stroke's exit (or from
    *start*) to stroke ``k``'s entry; ``d_next[k]`` is the distance from stroke
    ``k``'s exit to stroke ``k+1``'s entry.  Both are exactly the leg costs a
    2-opt move has to compare against.
    """
    n = len(route)
    entries = np.empty((n, 2), dtype=float)
    exits = np.empty((n, 2), dtype=float)
    for k, st in enumerate(route):
        e, x = _entry_exit(swaths, st)
        entries[k] = e
        exits[k] = x
    prev_exit = np.vstack([np.asarray(start, dtype=float), exits[:-1]]) if n else exits
    d_prev = np.linalg.norm(entries - prev_exit, axis=1) if n else np.empty(0)
    d_next = np.linalg.norm(exits[:-1] - entries[1:], axis=1) if n > 1 else np.empty(0)
    return entries, exits, prev_exit, d_prev, d_next


def two_opt(
    route: Sequence[Step],
    swaths: Sequence[Swath],
    start: Point2D,
    max_passes: int = 40,
) -> list[Step]:
    """2-opt for oriented segments.

    Reversing ``route[i:j+1]`` must also flip each stroke's direction, so that
    the reversed sub-path is the original one walked backwards.  Flipping the
    order without flipping the orientations would produce a route whose
    connection points do not line up -- a cheap bug that improves the objective
    while making the path undrivable.

    The move deltas are evaluated with NumPy over the whole ``j`` slice at once:
    only the two seams change, so a sweep is ``O(n^2)`` float operations rather
    than ``O(n^2)`` Python calls, which matters because routing -- not clipping
    -- dominates planning time on these fields.
    """
    route = list(route)
    n = len(route)
    if n < 3:
        return route

    for _ in range(max_passes):
        entries, exits, prev_exit, d_prev, d_next = _points(route, swaths, start)
        best_delta = -1e-9
        best_move: tuple[int, int] | None = None

        for i in range(n - 1):
            # j ranges over [i+1, n-1].  The final j has no following stroke, so
            # its "new leg 2" and "old leg 2" are both zero.
            a = np.linalg.norm(exits[i + 1 :] - prev_exit[i], axis=1)  # new leg 1
            if i + 2 <= n - 1:
                b = np.linalg.norm(entries[i + 2 :] - entries[i], axis=1)
            else:
                b = np.empty(0)
            new = a + np.concatenate([b, np.zeros(1)])
            old = d_prev[i] + np.concatenate([d_next[i + 1 :], np.zeros(1)])
            delta = new - old
            k = int(np.argmin(delta))
            if delta[k] < best_delta:
                best_delta = float(delta[k])
                best_move = (i, i + 1 + k)

        if best_move is None:
            break
        i, j = best_move
        route[i : j + 1] = [s.flipped() for s in reversed(route[i : j + 1])]

    return route


def or_opt(
    route: Sequence[Step],
    swaths: Sequence[Swath],
    start: Point2D,
    max_segment: int = 3,
    max_passes: int = 12,
) -> list[Step]:
    """Or-opt: relocate a run of 1..*max_segment* strokes elsewhere in the route.

    Lifting a block out and re-inserting it changes only two seams, so both the
    removal gain and the insertion cost are O(1).  The route with the block
    removed is addressed through an index offset rather than rebuilt, which
    keeps a full sweep at ``O(n^2)`` arithmetic instead of ``O(n^3)`` with list
    slicing.  On the benchmark fields the naive version dominated the entire
    planning time.
    """
    route = list(route)
    n = len(route)
    if n < 3:
        return route

    start_pt = (float(start[0]), float(start[1]))

    for _ in range(max_passes):
        # Endpoints are fixed for the whole sweep, so hoist them out of the
        # inner loop: the delta arithmetic itself is then pure float work.
        ents: list[Point2D] = []
        exts: list[Point2D] = []
        for st in route:
            e, x = _entry_exit(swaths, st)
            ents.append(e)
            exts.append(x)
        prev_pts = [start_pt] + exts[:-1]
        current = sum(_dist(prev_pts[k], ents[k]) for k in range(n))

        best_cost = current
        best_route: list[Step] | None = None

        for seg_len in range(1, max_segment + 1):
            for i in range(0, n - seg_len + 1):
                block = route[i : i + seg_len]
                flipped_block = [s.flipped() for s in reversed(block)]
                next_idx = i + seg_len
                has_next = next_idx < n

                # Cost of the tour with the block lifted out: the seam it
                # occupied is bridged by a single leg.
                gap = _dist(prev_pts[i], ents[i])
                if has_next:
                    gap += _dist(exts[next_idx - 1], ents[next_idx])
                    gap -= _dist(prev_pts[i], ents[next_idx])
                base = current - gap

                def rest_index(j: int, i: int = i, seg_len: int = seg_len) -> int:
                    """Index into *route* of the j-th stroke once the block is removed."""
                    return j if j < i else j + seg_len

                rest_len = n - seg_len
                for j in range(0, rest_len + 1):
                    a_pt = start_pt if j == 0 else exts[rest_index(j - 1)]
                    b = rest_index(j) if j < rest_len else -1
                    b_pt = ents[b] if b >= 0 else None

                    for blk, ent, ext in (
                        (block, ents[i], exts[i + seg_len - 1]),
                        (flipped_block, exts[next_idx - 1], ents[i]),
                    ):
                        delta = _dist(a_pt, ent)
                        if b_pt is not None:
                            delta += _dist(ext, b_pt) - _dist(a_pt, b_pt)
                        cand = base + delta
                        if cand < best_cost - 1e-9:
                            best_cost = cand
                            rest = route[:i] + route[next_idx:]
                            best_route = rest[:j] + blk + rest[j:]

        if best_route is None:
            break
        route = best_route

    return route


def two_opt_focused(
    route: Sequence[Step],
    swaths: Sequence[Swath],
    start: Point2D,
    focus: Sequence[int],
    window: int = 12,
    max_passes: int = 12,
) -> list[Step]:
    """2-opt restricted to pairs of positions near a *focus* set, run to convergence.

    Cheapest insertion alone leaves a route that is locally terrible around each
    insertion: the new stroke is spliced in at the cheapest available gap, which
    perturbs the two neighbours it lands between and nothing else ever fixes
    them.  Repairing only windows around the inserted strokes recovers most of
    the quality of a global 2-opt for a small fraction of its cost, which is
    what keeps the incremental planner inside its time budget.

    A pair ``(i, j)`` is considered when either endpoint lies within *window*
    positions of some focused index.  The sweep repeats until it stops finding
    improvements -- a single pass is not enough when a change inserts a third of
    the tour at once.
    """
    route = list(route)
    n = len(route)
    if n < 3 or not focus:
        return route

    near = np.zeros(n, dtype=bool)
    for f in focus:
        lo = max(0, int(f) - window)
        hi = min(n, int(f) + window + 1)
        near[lo:hi] = True
    if not near.any():
        return route

    for _ in range(max_passes):
        entries, exits, prev_exit, d_prev, d_next = _points(route, swaths, start)
        best_delta = -1e-9
        best_move: tuple[int, int] | None = None

        for i in range(n - 1):
            a = np.linalg.norm(exits[i + 1 :] - prev_exit[i], axis=1)
            if i + 2 <= n - 1:
                b = np.linalg.norm(entries[i + 2 :] - entries[i], axis=1)
            else:
                b = np.empty(0)
            new = a + np.concatenate([b, np.zeros(1)])
            old = d_prev[i] + np.concatenate([d_next[i + 1 :], np.zeros(1)])
            delta = new - old

            # A pair (i, j) is in scope when either end is near a focused index.
            in_scope = near[i + 1 :] | near[i]
            delta = np.where(in_scope, delta, np.inf)
            k = int(np.argmin(delta))
            if delta[k] < best_delta:
                best_delta = float(delta[k])
                best_move = (i, i + 1 + k)

        if best_move is None:
            break
        i, j = best_move
        route[i : j + 1] = [s.flipped() for s in reversed(route[i : j + 1])]

    return route


def or_opt_focused(
    route: Sequence[Step],
    swaths: Sequence[Swath],
    start: Point2D,
    focus: Sequence[int],
    window: int = 12,
    max_segment: int = 3,
    max_passes: int = 8,
) -> list[Step]:
    """Or-opt restricted to blocks near a *focus* set.

    2-opt cannot move a stroke that is simply in the wrong part of the tour
    without disturbing everything between its old and new positions.  Or-opt can,
    and after a change inserts a third of the tour at once that is exactly the
    repair needed.  Only blocks starting near a focused index are considered, so
    the sweep costs ``O(|focus| * n)`` rather than ``O(n^2)``.
    """
    route = list(route)
    n = len(route)
    if n < 3 or not focus:
        return route

    start_pt = (float(start[0]), float(start[1]))
    focus = [f for f in focus if 0 <= f < n]
    if not focus:
        return route

    for _ in range(max_passes):
        ents: list[Point2D] = []
        exts: list[Point2D] = []
        for st in route:
            e, x = _entry_exit(swaths, st)
            ents.append(e)
            exts.append(x)
        prev_pts = [start_pt] + exts[:-1]
        current = sum(_dist(prev_pts[k], ents[k]) for k in range(n))

        best_cost = current
        best_route: list[Step] | None = None

        candidates: set[int] = set()
        for f in focus:
            for d in range(-window, window + 1):
                k = f + d
                if 0 <= k < n:
                    candidates.add(k)

        for seg_len in (1, 2, 3)[:max_segment]:
            for i in sorted(candidates):
                if i + seg_len > n:
                    continue
                block = route[i : i + seg_len]
                flipped_block = [s.flipped() for s in reversed(block)]
                next_idx = i + seg_len
                has_next = next_idx < n

                gap = _dist(prev_pts[i], ents[i])
                if has_next:
                    gap += _dist(exts[next_idx - 1], ents[next_idx])
                    gap -= _dist(prev_pts[i], ents[next_idx])
                base = current - gap
                rest_len = n - seg_len

                for j in range(0, rest_len + 1):
                    if j == 0:
                        a_pt = start_pt
                    else:
                        pj = j - 1
                        a_pt = exts[pj if pj < i else pj + seg_len]
                    b = j if j < i else j + seg_len
                    b_pt = ents[b] if b < n else None

                    for blk, ent, ext in (
                        (block, ents[i], exts[i + seg_len - 1]),
                        (flipped_block, exts[next_idx - 1], ents[i]),
                    ):
                        delta = _dist(a_pt, ent)
                        if b_pt is not None:
                            delta += _dist(ext, b_pt) - _dist(a_pt, b_pt)
                        cand = base + delta
                        if cand < best_cost - 1e-9:
                            best_cost = cand
                            rest = route[:i] + route[next_idx:]
                            best_route = rest[:j] + blk + rest[j:]

        if best_route is None:
            break
        route = best_route

    return route


def route_optimised(
    swaths: Sequence[Swath],
    start: Point2D,
    use_two_opt: bool = True,
    use_or_opt: bool = True,
) -> list[Step]:
    """Greedy seeding followed by local search."""
    route = route_greedy(swaths, start)
    if use_two_opt:
        route = two_opt(route, swaths, start)
    if use_or_opt:
        route = or_opt(route, swaths, start)
    return route


# --------------------------------------------------------------------------
# route -> path
# --------------------------------------------------------------------------
def route_to_polyline(
    route: Sequence[Step],
    swaths: Sequence[Swath],
    start: Point2D,
    radius: float = 0.0,
) -> tuple[list[Point2D], RouteStats, list[list[Point2D]]]:
    """Expand a route into ``(full_path, stats, transit_legs)``.

    With ``radius <= 0`` the transit legs are straight lines, which is what a
    holonomic machine (or a first-cut model of one) drives.  With a positive
    radius each leg becomes the **Dubins path** between the exit pose of one
    stroke and the entry pose of the next, so the result is kinematically
    feasible and its length is comparable with a planner that models turns.

    The difference is not cosmetic.  A straight connector between two opposed
    swath ends is geometrically the shortest line, but no car with a turning
    radius can drive it; the Dubins leg is longer by an amount that grows as the
    radius does, and on small fields it dominates the driven distance.

    ``transit_legs`` is returned separately because the full path *includes the
    strokes themselves*.  A visualiser that draws the whole path on top of the
    strokes traces over them and makes the working pattern unreadable, which is
    exactly what the picture exists to show.
    """
    from .turns import dubins_path

    path: list[Point2D] = []
    legs: list[list[Point2D]] = []
    working = 0.0
    transit = 0.0
    cursor = start
    heading: float | None = None

    for k, step in enumerate(route):
        entry, exit_ = _entry_exit(swaths, step)
        leg_heading = math.atan2(exit_[1] - entry[1], exit_[0] - entry[0])
        leg: list[Point2D] = []

        if k == 0:
            # No heading is defined before the first stroke, so the approach is
            # a straight run-in regardless of the radius.
            d = _dist(cursor, entry)
            transit += d
            path.append(cursor)
            leg.append(cursor)
            if d > 1e-12:
                path.append(entry)
                leg.append(entry)
        elif radius > 0.0 and heading is not None:
            turn = dubins_path(
                (cursor[0], cursor[1], heading), (entry[0], entry[1], leg_heading), radius
            )
            transit += turn.length
            points = turn.points()
            # turn.points() starts exactly at the previous pose.
            taken = points[1:] if path else points
            path.extend(taken)
            leg.extend(taken)
        else:
            d = _dist(cursor, entry)
            transit += d
            if d > 1e-12:
                path.append(entry)
                leg.append(cursor)
                leg.append(entry)

        if len(leg) >= 2:
            legs.append(leg)

        working += _dist(entry, exit_)
        path.append(exit_)
        cursor = exit_
        heading = leg_heading

    stats = RouteStats(
        working_length=working,
        transit_length=transit,
        n_strokes=len(route),
        n_turns=max(0, len(route) - 1),
    )
    return path, stats, legs
