"""Tests for Dubins curves and agricultural headland turns.

The Dubins solver is closed-form, which means it can be *checked* rather than
trusted.  Two properties carry the weight:

* **Arrival.**  Every returned path is re-integrated segment by segment and its
  endpoint compared with the pose that was asked for.  A closed form with a sign
  error still produces a plausible number; it does not produce a path that
  arrives.
* **Optimality.**  The returned optimum must be no longer than any other word
  that also closes.  Without this the module would be a path generator rather
  than a shortest-path solver, and every turn-cost comparison built on it would
  be wrong.

Empirical validation against an independent numerical search lives in
``tools/verify_dubins.py``; what is here is fast enough to run in the suite.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cppclip.turns import (
    Segment,
    TurnPath,
    available_turns,
    dubins_length,
    dubins_path,
    dubins_solutions,
    headland_turn,
    select_turn,
    turn_feasible,
)

WORDS = ("LSL", "RSR", "LSR", "RSL", "RLR", "LRL")


def wrap(angle: float) -> float:
    return (angle + math.pi) % (2 * math.pi) - math.pi


def polyline_length(path: TurnPath) -> float:
    pts = np.asarray([(p[0], p[1]) for p in path.sample()], dtype=float)
    return float(np.sum(np.hypot(np.diff(pts[:, 0]), np.diff(pts[:, 1]))))


def arrival_error(path: TurnPath) -> float:
    x, y, theta = path.endpoint()
    ex, ey, etheta = path.end
    return max(abs(x - ex), abs(y - ey), abs(wrap(theta - etheta)))


def flip(q):
    return (q[0], q[1], wrap(q[2] + math.pi))


def random_pair(rng):
    return (
        (float(rng.uniform(-50, 50)), float(rng.uniform(-50, 50)), float(rng.uniform(-math.pi, math.pi))),
        (float(rng.uniform(-50, 50)), float(rng.uniform(-50, 50)), float(rng.uniform(-math.pi, math.pi))),
        float(rng.uniform(0.5, 12.0)),
    )


# --------------------------------------------------------------------------
# the arc primitive
# --------------------------------------------------------------------------
def test_left_quarter_arc_from_origin():
    x, y, t = Segment("L", math.pi / 2).endpoint(0, 0, 0, 1.0)
    assert (x, y, t) == pytest.approx((1.0, 1.0, math.pi / 2))


def test_right_quarter_arc_is_the_mirror():
    x, y, t = Segment("R", math.pi / 2).endpoint(0, 0, 0, 1.0)
    assert (x, y, t) == pytest.approx((1.0, -1.0, -math.pi / 2))


def test_half_arc_returns_across_the_diameter():
    x, y, t = Segment("L", math.pi).endpoint(0, 0, 0, 1.0)
    assert (x, y, t) == pytest.approx((0.0, 2.0, math.pi))


def test_zero_length_arc_is_a_no_op():
    for r in (0.3, 1.0, 25.0):
        assert Segment("L", 0.0).endpoint(3.0, -2.0, 0.7, r) == pytest.approx((3.0, -2.0, 0.7))


def test_arc_is_rotation_equivariant():
    """Rotating the start pose must rotate the end pose by the same angle."""
    r, sweep, phi = 2.5, 1.1, 0.6
    base = Segment("L", r * sweep).endpoint(0.0, 0.0, 0.0, r)
    c, s = math.cos(phi), math.sin(phi)
    rotated = (base[0] * c - base[1] * s, base[0] * s + base[1] * c, base[2] + phi)
    assert Segment("L", r * sweep).endpoint(0.0, 0.0, phi, r) == pytest.approx(rotated)


# --------------------------------------------------------------------------
# degenerate input
# --------------------------------------------------------------------------
@pytest.mark.parametrize("radius", [0.0, -1.0, float("nan"), float("inf")])
def test_non_positive_or_non_finite_radius_raises(radius: float):
    with pytest.raises(ValueError):
        dubins_path((0, 0, 0), (1, 1, 0), radius)
    with pytest.raises(ValueError):
        dubins_length((0, 0, 0), (1, 1, 0), radius)


def test_identical_poses_give_the_empty_path():
    path = dubins_path((3.0, 4.0, 0.9), (3.0, 4.0, 0.9), 2.0)
    assert path.length == 0.0
    assert dubins_length((3.0, 4.0, 0.9), (3.0, 4.0, 0.9), 2.0) == 0.0


def test_non_positive_spacing_raises():
    for w in (0.0, -1.0, float("nan")):
        with pytest.raises(ValueError):
            headland_turn("omega", w, 1.0)


def test_unknown_turn_kind_raises():
    with pytest.raises(ValueError):
        headland_turn("barrel_roll", 3.0, 1.0)


# --------------------------------------------------------------------------
# Dubins: arrival
# --------------------------------------------------------------------------
@pytest.mark.parametrize("seed", range(4))
def test_every_returned_path_reaches_its_goal(seed: int):
    rng = np.random.default_rng(seed)
    worst = 0.0
    for _ in range(40):
        q0, q1, r = random_pair(rng)
        worst = max(worst, arrival_error(dubins_path(q0, q1, r)))
    assert worst < 1e-9, f"worst arrival error {worst:.3e}"


@pytest.mark.parametrize("seed", range(3))
def test_every_candidate_word_reaches_its_goal(seed: int):
    """Not just the winner: every word admitted by the gate must arrive."""
    rng = np.random.default_rng(100 + seed)
    for _ in range(25):
        q0, q1, r = random_pair(rng)
        for solution in dubins_solutions(q0, q1, r):
            assert arrival_error(solution.as_path()) < 1e-9


def test_sampled_polyline_matches_the_analytic_length():
    rng = np.random.default_rng(5)
    for _ in range(12):
        q0, q1, r = random_pair(rng)
        path = dubins_path(q0, q1, r)
        assert polyline_length(path) == pytest.approx(path.length, rel=2e-3)


def test_straight_line_sanity():
    """Aligned, colinear poses must give exactly the Euclidean distance."""
    for r in (0.5, 2.0, 6.0):
        path = dubins_path((0, 0, 0), (7, 0, 0), r)
        assert path.length == pytest.approx(7.0)
        assert path.backwards == 0.0


# --------------------------------------------------------------------------
# Dubins: optimality
# --------------------------------------------------------------------------
@pytest.mark.parametrize("seed", range(4))
def test_returned_optimum_beats_every_other_closing_word(seed: int):
    rng = np.random.default_rng(200 + seed)
    for _ in range(25):
        q0, q1, r = random_pair(rng)
        sols = dubins_solutions(q0, q1, r)
        assert sols, "no word closed"
        best = sols[0].length
        for other in sols[1:]:
            assert best <= other.length + 1e-9
        assert dubins_length(q0, q1, r) == pytest.approx(best)


@pytest.mark.parametrize("seed", range(3))
def test_reversal_symmetry(seed: int):
    """``L(a, b) == L(flip(b), flip(a))``.

    Deliberately *not* ``L(a, b) == L(b, a)``, which is false for Dubins: running
    a path backwards turns each L into an R and rotates both headings by pi, so
    the poses must be flipped as well.
    """
    rng = np.random.default_rng(300 + seed)
    for _ in range(25):
        q0, q1, r = random_pair(rng)
        assert dubins_length(q0, q1, r) == pytest.approx(
            dubins_length(flip(q1), flip(q0), r), abs=1e-9
        )


def test_ninety_degree_turn_at_minimum_radius():
    """The tightest possible 90 degree turn must be found, not missed."""
    path = dubins_path((0, 0, 0), (0, 1, math.pi / 2), 1.0)
    assert arrival_error(path) < 1e-12
    assert path.length == pytest.approx(6.99939, abs=1e-4)
    assert path.is_forward_only


def test_u_turn_in_place_is_found():
    path = dubins_path((0, 0, 0), (0, 0, math.pi), 1.0)
    assert arrival_error(path) < 1e-12
    assert path.length == pytest.approx(7.33038, abs=1e-4)
    assert path.is_forward_only


def test_ccc_words_are_used_when_they_win():
    """A short lateral hop needs a CCC word; the CSC words overestimate it."""
    path = dubins_path((0, 0, 0), (0.4, 0.4, 2.8), 1.0)
    assert path.word in WORDS
    assert path.word in ("RLR", "LRL")


# --------------------------------------------------------------------------
# headland turns
# --------------------------------------------------------------------------
def test_omega_turn_is_optimal_below_two_radii():
    r = 2.0
    w = 1.5 * r
    turn = headland_turn("omega", w, r)
    assert turn is not None
    assert turn.path.word in ("RLR", "LRL")
    assert turn.length == pytest.approx(available_turns(w, r)[0].length, abs=1e-9)
    assert turn.backwards == 0.0


def test_pi_turn_is_optimal_above_two_radii():
    r = 2.0
    w = 3.0 * r
    turn = headland_turn("pi", w, r)
    assert turn is not None
    assert turn.path.word in ("LSL", "RSR")
    # two quarter arcs plus a straight of w - 2r
    assert turn.length == pytest.approx(math.pi * r + (w - 2.0 * r), abs=1e-9)


def test_flat_turn_at_exactly_two_radii():
    r = 2.0
    turn = headland_turn("flat", 2.0 * r, r)
    assert turn is not None
    assert turn.length == pytest.approx(math.pi * r, abs=1e-9)
    straight = next((abs(s.length) for s in turn.path.segments if s.turn == "S"), 0.0)
    assert straight == pytest.approx(0.0, abs=1e-9)


def test_three_point_turn_needs_a_lateral_offset():
    """The cross-side words only become available once the swaths are offset."""
    assert headland_turn("three_point", 1.0, 1.0, offset=0.0) is None
    turn = headland_turn("three_point", 1.0, 1.0, offset=3.0)
    assert turn is not None
    assert turn.path.word in ("LSR", "RSL")


def test_pi_is_the_optimum_above_two_radii():
    """Above 2r the omega loop still closes but is no longer optimal."""
    ts = available_turns(4.0, 1.0)
    assert ts[0].kind == "pi"
    assert ts[0].length < min(t.length for t in ts[1:]) + 1e-9


def test_infeasible_turn_is_reported_not_silently_returned():
    """Nothing closes for a spacing the manoeuvre cannot span."""
    assert headland_turn("flat", 5.0, 1.0) is None
    assert not turn_feasible("flat", 5.0, 1.0)


def test_select_turn_raises_when_nothing_fits_the_headland():
    with pytest.raises(ValueError):
        select_turn(1.0, 1.0, headland=0.01)
    assert select_turn(1.0, 1.0, headland=5.0) is not None


def test_available_turns_is_shortest_first():
    for w in (0.5, 1.0, 2.0, 4.0, 9.0):
        ts = available_turns(w, 1.0)
        assert ts
        assert [t.length for t in ts] == sorted(t.length for t in ts)


def test_required_headland_is_measured_from_the_geometry():
    """The omega loop dips below the first swath; the pi turn does not."""
    omega = headland_turn("omega", 1.0, 1.0)
    pi_turn = headland_turn("pi", 4.0, 1.0)
    assert omega.required_headland > 0.0
    assert omega.required_field > 0.0
    assert pi_turn.required_field == pytest.approx(0.0, abs=1e-9)
