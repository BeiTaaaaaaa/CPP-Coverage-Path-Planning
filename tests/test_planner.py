"""Tests for the planning pipeline's headland handling and bookkeeping.

The headland is where working distance and repositioning distance are easiest to
conflate, and conflating them silently corrupts the working-length comparison
against any other planner.  An external head-to-head run caught exactly that:
on fields whose inward offset splits into several loops, the straight joins
between loops were being counted as work (71-260 m per field).  These tests pin
the distinction.
"""

from __future__ import annotations

import pytest
from shapely.geometry import box

from cppclip import geometry as G
from cppclip.fields import Field
from cppclip.metrics import polyline_length
from cppclip.planner import PlanParams, field_headland, inner_region, obstacle_headland, plan


def annulus_field() -> Field:
    """A square field with a square hole: the inward offset has two loops."""
    outer = box(0, 0, 100, 100)
    hole = box(40, 40, 60, 60)
    return Field(name="annulus", boundary=G.normalise(outer.difference(hole)))


def test_single_loop_headland_has_no_transit():
    square = Field(name="square", boundary=G.normalise(box(0, 0, 100, 100)))
    loops = field_headland(square.boundary, 6.0, 1)
    assert loops.working_length > 0
    assert loops.transit_length == 0.0
    assert polyline_length(loops.points) == pytest.approx(loops.total_length, rel=1e-9)


def test_multi_loop_headland_counts_joins_as_transit():
    """The joins between separate headland loops are repositioning, not work."""
    loops = field_headland(annulus_field().boundary, 6.0, 1)
    assert loops.working_length > 0
    assert loops.transit_length > 0, "a two-loop headland must register a join"
    assert polyline_length(loops.points) == pytest.approx(loops.total_length, rel=1e-9)

    # Both loops of the annulus are squares of side 100 - 2*3 and 20 + 2*3.
    expected = 4 * (100 - 6) + 4 * (20 + 6)
    assert loops.working_length == pytest.approx(expected, rel=1e-6)


def test_obstacle_headland_is_local_and_single_loop():
    obstacle = G.normalise(box(40, 40, 60, 60))
    loops = obstacle_headland(obstacle, 6.0, 1)
    assert loops.working_length == pytest.approx(4 * (20 + 6), rel=1e-6)
    assert loops.transit_length == 0.0


def test_plan_working_length_excludes_inter_loop_jumps():
    """`Plan.route_stats.working_length` must not absorb headland joins."""
    field = annulus_field()
    params = PlanParams(swath_width=6.0, headland_width=6.0, min_swath_length=1.0,
                        n_angle_candidates=4, angle=0.0)
    p = plan(field, params)

    loops = field_headland(field.boundary, params.swath_width, p.n_headland_passes)
    stroke_total = sum(s.length for s in p.strokes)

    assert p.route_stats.working_length == pytest.approx(
        stroke_total + loops.working_length, rel=1e-9
    )
    assert p.route_stats.transit_length >= loops.transit_length


def test_inner_region_shrinks_by_the_headland_inset():
    field = annulus_field()
    inner, n_passes = inner_region(field.boundary, [], 6.0, 6.0)
    assert n_passes == 1
    # Eroded by 6 m: the outer square loses 6 m per side, the hole grows by 6.
    assert inner.area == pytest.approx((100 - 12) ** 2 - (20 + 12) ** 2, rel=1e-6)


def test_headland_loops_never_enter_an_obstacle():
    """No part of the headland path may drive through an obstacle.

    This failed in two different ways before it was fixed, and both are easy to
    reintroduce:

    * the loops were cut from the boundary or the obstacle alone, so a lap around
      one obstacle ran straight through its neighbour;
    * ``Plan`` exposed the headland as a single flat point list, so joining the
      loops into a polyline invented straight segments between them.  On a field
      with sixteen obstacles those phantom joins came to 343 m, every metre of it
      inside something solid.
    """
    from shapely.geometry import LineString

    from cppclip.fields import make_field

    field = make_field("rectilinear", seed=4, n_obstacles=16, target_area=25_000.0)
    params = PlanParams(swath_width=6.0, headland_width=6.0, min_swath_length=1.0,
                        n_angle_candidates=4, angle=0.0)
    p = plan(field, params)

    obstacles = G.normalise(G.unary_union(field.obstacles))
    assert not obstacles.is_empty
    assert len(p.headland_loops) > 1, "test needs a multi-loop headland to be meaningful"

    inside = 0.0
    outside = 0.0
    for loop in p.headland_loops:
        assert len(loop) >= 2
        line = LineString(loop)
        crossing = line.intersection(obstacles)
        if not crossing.is_empty:
            inside += float(crossing.length)
        beyond = line.difference(field.boundary.buffer(1e-9))
        if not beyond.is_empty:
            outside += float(beyond.length)

    assert inside < 1e-6, f"{inside:.3f} m of headland runs through an obstacle"
    assert outside < 1e-6, f"{outside:.3f} m of headland runs outside the field"


def test_headland_loops_are_kept_apart():
    """The loops must be separable, not welded into one polyline.

    Every consumer that wants a single path can concatenate them itself; none can
    recover the separation once it has been thrown away, and the segments that
    welding adds are indistinguishable from driven path.
    """
    field = annulus_field()
    params = PlanParams(swath_width=6.0, headland_width=6.0, min_swath_length=1.0,
                        n_angle_candidates=4, angle=0.0)
    p = plan(field, params)

    assert p.headland_loops, "annulus should produce headland loops"
    flat = sum(len(loop) for loop in p.headland_loops)

    # The loops must not have been merged into one by the round trip.
    from shapely.geometry import LineString

    welded = LineString([pt for loop in p.headland_loops for pt in loop])
    lengths = sum(float(LineString(loop).length) for loop in p.headland_loops)
    assert float(welded.length) >= lengths - 1e-9
    # On an annulus the joins are real distance the welded form would add, so the
    # two must differ; if they did not, this field could not detect a regression.
    assert float(welded.length) > lengths + 1.0
    assert flat == len(p.headland_loops[0]) + sum(len(x) for x in p.headland_loops[1:])


def test_headland_argument_parsing_distinguishes_one_loop_from_many():
    """A headland argument is a list of loops, not a list of points.

    ``score_solution`` has to accept both a genuine multi-loop headland and a
    single loop passed unwrapped, and the two differ only in what the *first*
    element is: a point (pair of numbers) versus a loop (sequence of points).

    An earlier version tested whether the first element of the first loop was a
    number -- which it never is, since loops contain points -- so **every**
    argument was read as "no headland". Both systems in the head-to-head
    comparison silently lost their headland: coverage fell from 0.987 to 0.817
    and nothing raised. These assertions pin the discrimination.
    """
    from cppclip.metrics import _as_loops, _is_point

    assert _is_point((3.0, 4.0))
    assert _is_point([3.0, 4.0])

    loop_a = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)]
    loop_b = [(5.0, 5.0), (6.0, 5.0), (6.0, 6.0)]
    assert not _is_point(loop_a)

    assert _as_loops(loop_a) == [loop_a]
    assert _as_loops([loop_a, loop_b]) == [loop_a, loop_b]
    # The shape that actually arrives from the comparison's JSON.
    assert _as_loops([[[0.0, 0.0], [1.0, 0.0]], [[2.0, 2.0], [3.0, 2.0]]]) == [
        [[0.0, 0.0], [1.0, 0.0]],
        [[2.0, 2.0], [3.0, 2.0]],
    ]
    assert _as_loops([]) == []
    assert _as_loops(None) == []
    assert _as_loops(()) == []


def test_score_solution_counts_the_headland_it_is_given():
    """Coverage must move when a headland is supplied, and by a sane amount."""
    from cppclip.fields import make_field
    from cppclip.metrics import score_solution

    field = make_field("rect", seed=1, n_obstacles=0, target_area=20_000.0)
    params = PlanParams(swath_width=6.0, headland_width=6.0, min_swath_length=1.0,
                        n_angle_candidates=4, angle=0.0)
    p = plan(field, params)
    swaths = [(s.p0, s.p1) for s in p.strokes]

    without = score_solution(field, swaths=swaths, headland=[], width=params.swath_width)
    with_hl = score_solution(
        field, swaths=swaths, headland=p.headland_loops, width=params.swath_width
    )
    assert with_hl["coverage"] > without["coverage"] + 0.01
    assert with_hl["headland_length"] > 0.0

    # Feeding the loops welded into one polyline must over-count the joins.
    welded = [[pt for loop in p.headland_loops for pt in loop]]
    welded_score = score_solution(
        field, swaths=swaths, headland=welded, width=params.swath_width
    )
    assert welded_score["headland_length"] >= with_hl["headland_length"] - 1e-9
