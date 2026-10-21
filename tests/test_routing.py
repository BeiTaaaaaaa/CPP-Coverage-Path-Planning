"""Correctness and sanity tests for stroke ordering.

The 2-opt and Or-opt implementations evaluate move deltas analytically instead of
rebuilding and re-costing the whole route.  That is what makes routing fast
enough to run over 350 real fields, but it also means a single wrong index would
silently produce a worse route while still looking plausible.  These tests pin
the deltas against brute force.
"""

from __future__ import annotations

import numpy as np
import pytest

from cppclip.routing import (
    Step,
    or_opt,
    route_boustrophedon,
    route_cost,
    route_greedy,
    route_optimised,
    route_to_polyline,
    two_opt,
    two_opt_focused,
)
from cppclip.swaths import Swath


def synthetic_swaths(n_lines: int = 6, per_line: int = 2, seed: int = 0) -> list[Swath]:
    """A grid of strokes, deliberately not in any sensible order."""
    rng = np.random.default_rng(seed)
    out: list[Swath] = []
    for i in range(n_lines):
        y = 10.0 * i
        for _ in range(per_line):
            x0 = float(rng.uniform(0, 40))
            x1 = x0 + float(rng.uniform(5, 30))
            out.append(Swath(scanline=i, y=y, x0=x0, x1=x1))
    return out


def brute_force_two_opt_step(route, swaths, start):
    """The move the analytic delta claims is best, recomputed by full re-costing."""
    base = route_cost(route, swaths, start)
    best = (base, None)
    for i in range(len(route) - 1):
        for j in range(i + 1, len(route)):
            cand = route[:i] + [s.flipped() for s in reversed(route[i : j + 1])] + route[j + 1 :]
            c = route_cost(cand, swaths, start)
            if c < best[0] - 1e-9:
                best = (c, cand)
    return best


# --------------------------------------------------------------------------
def test_analytic_two_opt_delta_matches_brute_force():
    """One 2-opt sweep must pick exactly the move brute force would pick."""
    swaths = synthetic_swaths(seed=3)
    start = (0.0, -5.0)
    route = route_greedy(swaths, start)

    _cost, expected = brute_force_two_opt_step(route, swaths, start)
    got = two_opt(route, swaths, start, max_passes=1)

    if expected is None:
        assert route_cost(got, swaths, start) == pytest.approx(
            route_cost(route, swaths, start), abs=1e-9
        )
    else:
        assert route_cost(got, swaths, start) == pytest.approx(
            route_cost(expected, swaths, start), abs=1e-6
        )


@pytest.mark.parametrize("seed", range(6))
def test_local_search_never_worsens_the_route(seed: int):
    swaths = synthetic_swaths(seed=seed)
    start = (0.0, 0.0)
    base = route_cost(route_greedy(swaths, start), swaths, start)

    r2 = two_opt(route_greedy(swaths, start), swaths, start)
    assert route_cost(r2, swaths, start) <= base + 1e-9

    r3 = or_opt(r2, swaths, start)
    assert route_cost(r3, swaths, start) <= route_cost(r2, swaths, start) + 1e-9


@pytest.mark.parametrize("seed", range(4))
def test_optimised_beats_or_matches_greedy(seed: int):
    swaths = synthetic_swaths(n_lines=8, per_line=2, seed=seed)
    start = (0.0, -3.0)
    greedy = route_cost(route_greedy(swaths, start), swaths, start)
    optimised = route_cost(route_optimised(swaths, start), swaths, start)
    assert optimised <= greedy + 1e-9


def test_boustrophedon_is_a_permutation():
    swaths = synthetic_swaths(n_lines=5, per_line=3, seed=2)
    route = route_boustrophedon(swaths)
    assert sorted(s.index for s in route) == list(range(len(swaths)))


def test_focused_two_opt_never_worsens():
    swaths = synthetic_swaths(n_lines=7, per_line=2, seed=5)
    start = (0.0, 0.0)
    route = route_greedy(swaths, start)
    focus = [0, len(route) // 2, len(route) - 1]
    got = two_opt_focused(route, swaths, start, focus, window=4)
    assert route_cost(got, swaths, start) <= route_cost(route, swaths, start) + 1e-9


def test_route_to_polyline_lengths_are_consistent():
    swaths = synthetic_swaths(n_lines=4, per_line=2, seed=1)
    start = (0.0, -1.0)
    route = route_optimised(swaths, start)
    path, stats, legs = route_to_polyline(route, swaths, start)

    assert stats.working_length == pytest.approx(sum(swaths[s.index].length for s in route))
    assert stats.n_strokes == len(route)

    # The polyline's own length must equal working + transit.
    pts = np.asarray(path, dtype=float)
    drawn = float(np.sum(np.hypot(np.diff(pts[:, 0]), np.diff(pts[:, 1]))))
    assert drawn == pytest.approx(stats.total_length, rel=1e-9)

    # The transit legs must account for the transit length and nothing else.
    leg_total = 0.0
    for leg in legs:
        arr = np.asarray(leg, dtype=float)
        leg_total += float(np.sum(np.hypot(np.diff(arr[:, 0]), np.diff(arr[:, 1]))))
    assert leg_total == pytest.approx(stats.transit_length, rel=1e-9)


def test_transit_legs_do_not_contain_the_strokes():
    """A leg must be repositioning only, never a stroke redrawn.

    Drawing the two together traces the transit over the working pattern, which
    is the one thing a coverage picture exists to show.
    """
    swaths = synthetic_swaths(n_lines=5, per_line=2, seed=3)
    start = (0.0, 0.0)
    route = route_optimised(swaths, start)
    _path, stats, legs = route_to_polyline(route, swaths, start)

    for leg in legs:
        arr = np.asarray(leg, dtype=float)
        if len(arr) < 2:
            continue
        length = float(np.sum(np.hypot(np.diff(arr[:, 0]), np.diff(arr[:, 1]))))
        longest_stroke = max(s.length for s in swaths)
        assert length < longest_stroke + 1e-9, "a transit leg is as long as a stroke"


def test_or_opt_delta_matches_brute_force_on_one_pass():
    swaths = synthetic_swaths(n_lines=5, per_line=2, seed=9)
    start = (0.0, 0.0)
    route = route_greedy(swaths, start)

    got = or_opt(route, swaths, start, max_passes=1)
    got_cost = route_cost(got, swaths, start)

    # Brute force: try every single-block relocation and both orientations.
    best = route_cost(route, swaths, start)
    n = len(route)
    for seg_len in (1, 2, 3):
        for i in range(0, n - seg_len + 1):
            block = route[i : i + seg_len]
            rest = route[:i] + route[i + seg_len :]
            for j in range(0, len(rest) + 1):
                for blk in (block, [s.flipped() for s in reversed(block)]):
                    cand = rest[:j] + blk + rest[j:]
                    best = min(best, route_cost(cand, swaths, start))

    assert got_cost == pytest.approx(best, abs=1e-6)
