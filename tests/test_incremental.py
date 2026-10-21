"""Correctness tests for dynamic incremental replanning.

The claim being tested is strong and checkable: after any sequence of obstacle
insertions and removals, the incrementally maintained clipper must produce
*exactly* the intervals that a from-scratch build would produce for the same
scene.  If that fails, every speed-up number in the paper is meaningless.
"""

from __future__ import annotations

import numpy as np
import pytest
from shapely.geometry import box

from cppclip import fields as F
from cppclip import geometry as G
from cppclip.incremental import IncrementalPlanner
from cppclip.planner import PlanParams, inner_region
from cppclip.sweep import ScanlineClipper


def make_params(**kw) -> PlanParams:
    base = dict(swath_width=6.0, headland_width=6.0, min_swath_length=1.0,
                n_angle_candidates=8, angle=0.0)
    base.update(kw)
    return PlanParams(**base)


def spread_obstacles(field, count: int = 6, seed: int = 5, shrink: float = 18.0):
    """Place disjoint obstacles in the field interior.

    The erosion depth matters: eroding a notched rectilinear field by 30 m
    leaves a fragmented sliver where almost nothing fits, which would silently
    turn these tests into no-ops.  18 m is enough clearance for every shape and
    seed used here.
    """
    region = G.erode(field.boundary, shrink)
    if region.is_empty or region.area < 100.0:
        pytest.skip("field interior too small for obstacle placement")
    return F.random_obstacles(region, count, seed=seed, size_range=(5.0, 10.0))


def reference_intervals(field, params: PlanParams):
    """From-scratch intervals for the same scene, computed independently."""
    inner, _ = inner_region(field.boundary, field.obstacles, params.headland_width, params.swath_width)
    clip = ScanlineClipper.from_geometry(inner, params.swath_width)
    return clip, clip.all_intervals()


def assert_intervals_match(clip: ScanlineClipper, ref_clip: ScanlineClipper, tol=1e-7):
    assert clip.n_scanlines == ref_clip.n_scanlines, "scanline grid differs"
    for i in range(ref_clip.n_scanlines):
        got = sorted(clip.intervals_at(i))
        want = sorted(ref_clip.intervals_at(i))
        assert len(got) == len(want), f"scanline {i}: {got} != {want}"
        for (a0, a1), (b0, b1) in zip(got, want):
            assert abs(a0 - b0) <= tol and abs(a1 - b1) <= tol, f"scanline {i}: {got} != {want}"


# --------------------------------------------------------------------------
# the central equivalence
# --------------------------------------------------------------------------
@pytest.mark.parametrize("kind", ["rect", "star", "rectilinear"])
def test_incremental_matches_full_rebuild_after_insertions(kind: str):
    """Insert obstacles one at a time; the clipper must track a fresh build."""
    base = F.make_field(kind, seed=1, n_obstacles=0, target_area=20_000.0)
    params = make_params()
    planner = IncrementalPlanner(base, params)

    candidates = spread_obstacles(base, 8, seed=5)
    assert len(candidates) >= 4, "test scene produced too few obstacles"

    known = []
    for k, obs in enumerate(candidates):
        planner.add_obstacle(obs)
        known.append(obs)
        scene = base.with_obstacles(known)
        ref_clip, _ = reference_intervals(scene, params)
        assert_intervals_match(planner.clipper, ref_clip)


@pytest.mark.parametrize("kind", ["rect", "star"])
def test_incremental_matches_full_rebuild_after_removals(kind: str):
    """Remove obstacles again; the scene must return to the reference exactly."""
    base = F.make_field(kind, seed=2, n_obstacles=0, target_area=20_000.0)
    params = make_params()
    planner = IncrementalPlanner(base, params)

    candidates = spread_obstacles(base, 6, seed=7)
    handles = [planner.add_obstacle(o)[0] for o in candidates]

    for h in handles:
        planner.remove_obstacle(h)

    ref_clip, _ = reference_intervals(base, params)
    assert_intervals_match(planner.clipper, ref_clip)


def test_blank_and_restored_scenes_agree_with_planner_pipeline():
    """The incremental plan's coverage geometry must equal a from-scratch plan."""
    from cppclip.metrics import evaluate
    from cppclip.planner import plan

    base = F.make_field("rectilinear", seed=3, n_obstacles=0, target_area=20_000.0)
    params = make_params()
    planner = IncrementalPlanner(base, params)

    obstacles = spread_obstacles(base, 5, seed=11)
    for o in obstacles:
        planner.add_obstacle(o)

    scene = base.with_obstacles(obstacles)
    inc_plan = planner.to_plan()
    full_plan = plan(scene, params)

    inc_metrics = evaluate(scene, inc_plan)
    full_metrics = evaluate(scene, full_plan)

    # Same swath set (routing differs by design, so only coverage must agree).
    inc_keys = sorted((round(s.p0[0], 6), round(s.p0[1], 6), round(s.p1[0], 6), round(s.p1[1], 6))
                      for s in inc_plan.strokes)
    full_keys = sorted((round(s.p0[0], 6), round(s.p0[1], 6), round(s.p1[0], 6), round(s.p1[1], 6))
                       for s in full_plan.strokes)
    assert inc_keys == full_keys, "incremental and full plans cover different strokes"

    assert inc_metrics.coverage == pytest.approx(full_metrics.coverage, abs=0.02)
    # A local route repair may cost some transit, but it must stay in the same league.
    assert inc_metrics.transit_length <= full_metrics.transit_length * 1.6 + 50.0


# --------------------------------------------------------------------------
# efficiency claim
# --------------------------------------------------------------------------
def test_incremental_touches_few_scanlines():
    """One small obstacle must invalidate a small share of the scanline grid."""
    base = F.make_field("rect", seed=0, n_obstacles=0, target_area=100_000.0)
    planner = IncrementalPlanner(base, make_params())
    n_total = planner.clipper.n_scanlines
    obstacle = G.normalise(box(150.0, 150.0, 170.0, 170.0))
    _h, report = planner.add_obstacle(obstacle)
    assert report.mode == "incremental"
    assert 0 < report.n_affected_scanlines < 0.5 * n_total
    assert report.work_fraction < 0.5


def test_adjacent_obstacles_merge_groups_and_stay_correct():
    """Dilated obstacles that touch must merge, not corrupt parity."""
    base = F.make_field("rect", seed=0, n_obstacles=0, target_area=40_000.0)
    params = make_params(headland_width=6.0, swath_width=6.0)
    planner = IncrementalPlanner(base, params)

    # Two boxes 4 m apart: with an inset of 6 m their dilations overlap heavily.
    a = G.normalise(box(80.0, 80.0, 100.0, 100.0))
    b = G.normalise(box(104.0, 80.0, 124.0, 100.0))
    planner.add_obstacle(a)
    _h, report = planner.add_obstacle(b)
    assert report.mode == "group_merge"
    assert report.merged_groups == 1

    ref_clip, _ = reference_intervals(base.with_obstacles([a, b]), params)
    assert_intervals_match(planner.clipper, ref_clip)


def test_group_split_on_removal():
    """Removing one obstacle from a merged group must restore the other."""
    base = F.make_field("rect", seed=0, n_obstacles=0, target_area=40_000.0)
    params = make_params()
    planner = IncrementalPlanner(base, params)

    a = G.normalise(box(80.0, 80.0, 100.0, 100.0))
    b = G.normalise(box(104.0, 80.0, 124.0, 100.0))
    ha, _ = planner.add_obstacle(a)
    hb, _ = planner.add_obstacle(b)

    planner.remove_obstacle(ha)
    ref_clip, _ = reference_intervals(base.with_obstacles([b]), params)
    assert_intervals_match(planner.clipper, ref_clip)

    planner.remove_obstacle(hb)
    ref_clip, _ = reference_intervals(base, params)
    assert_intervals_match(planner.clipper, ref_clip)


def test_route_stays_valid_and_covers_every_stroke():
    """Local repair must produce a permutation of all swaths, with none dropped."""
    base = F.make_field("star", seed=4, n_obstacles=0, target_area=30_000.0)
    params = make_params()
    planner = IncrementalPlanner(base, params)

    obstacles = spread_obstacles(base, 6, seed=21)
    for o in obstacles:
        planner.add_obstacle(o)

    swaths = planner.swaths()
    visited = [planner._route_swaths[st.index] for st in planner._route]
    assert len(visited) == len(swaths), "route does not visit every stroke exactly once"
    keys_route = sorted((s.scanline, round(s.x0, 9), round(s.x1, 9)) for s in visited)
    keys_all = sorted((s.scanline, round(s.x0, 9), round(s.x1, 9)) for s in swaths)
    assert keys_route == keys_all


def test_dense_arrivals_force_merges_and_stay_exact():
    """Stress the group-merge path with deliberately clustered obstacles.

    When obstacles are dense enough that their dilated shapes percolate into one
    connected component, every later arrival joins that component.  The planner
    re-clips only the new obstacle's own ``y`` span, on the argument that a union
    can only alter the boundary near the shape being added.  This test attacks
    that argument: it places obstacles close enough to merge repeatedly, and
    checks the clipper against a from-scratch reference after every insertion.
    """
    base = F.make_field("rect", seed=0, n_obstacles=0, target_area=40_000.0)
    params = make_params(headland_width=6.0, swath_width=6.0)
    planner = IncrementalPlanner(base, params)

    rng = np.random.default_rng(4)
    known = []
    merged = 0
    cx = cy = 100.0
    for k in range(16):
        if k:
            cx = float(np.clip(cx + rng.uniform(-16, 16), 35, 175))
            cy = float(np.clip(cy + rng.uniform(-16, 16), 35, 175))
        half = float(rng.uniform(3.5, 7.0))
        obs = G.normalise(box(cx - half, cy - half, cx + half, cy + half))
        if any(obs.intersects(o) for o in known):
            continue
        _h, report = planner.add_obstacle(obs)
        known.append(obs)
        merged += report.mode == "group_merge"

        ref_clip, _ = reference_intervals(base.with_obstacles(known), params)
        assert_intervals_match(planner.clipper, ref_clip)

    assert merged >= 4, f"test did not exercise merging (only {merged} merges)"


def test_removing_everything_restores_the_original_transit():
    """A pure insert/remove cycle must return the plan close to where it started."""
    base = F.make_field("rectilinear", seed=5, n_obstacles=0, target_area=30_000.0)
    params = make_params()
    planner = IncrementalPlanner(base, params)
    before = planner.route_stats().transit_length

    obstacles = spread_obstacles(base, 5, seed=31)
    handles = [planner.add_obstacle(o)[0] for o in obstacles]
    for h in handles:
        planner.remove_obstacle(h)

    after = planner.route_stats().transit_length
    assert after == pytest.approx(before, rel=0.35)


def test_grouping_does_not_cost_headland_coverage():
    """Grouping is a clipper requirement and must not leak into the headland path.

    Even-odd parity forces obstacles whose dilated shapes touch to be registered
    as one ring source, so the clipper sees a union.  If the *headland* is then
    also drawn around that union, the plan loses the free space between two
    nearby obstacles -- space the machine can drive, and which a from-scratch
    plan does cover by drawing one loop per obstacle.

    This was a real defect: it cost up to 2.2 pp of coverage on obstacle-dense
    scenes while leaving the swath set untouched, so interval-level tests could
    not see it.  The assertion is on coverage rather than on stroke geometry for
    exactly that reason.
    """
    from cppclip.metrics import evaluate
    from cppclip.planner import plan

    base = F.make_field("rectilinear", seed=4, n_obstacles=0, target_area=20_000.0)
    params = make_params(angle=0.0)
    planner = IncrementalPlanner(base, params)
    frozen = make_params(angle=planner.angle)

    # Obstacles spaced so their 6 m dilations overlap, but leaving a drivable
    # gap between the solids -- the configuration that exposes the defect.
    minx, miny, maxx, maxy = G.bounds_of(base.boundary)
    cy = 0.5 * (miny + maxy)
    half = 8.0
    step = 22.0
    x0 = minx + 0.4 * (maxx - minx)
    known = []
    merges = 0
    for k in range(4):
        cx = x0 + k * step
        obs = G.normalise(box(cx - half, cy - half, cx + half, cy + half))
        if not base.boundary.contains(obs):
            continue
        _h, report = planner.add_obstacle(obs)
        known.append(obs)
        merges += report.mode == "group_merge"

        if not known:
            continue
        scene = base.with_obstacles(known)
        m_inc = evaluate(scene, planner.to_plan())
        m_full = evaluate(scene, plan(scene, frozen))
        assert m_inc.coverage == pytest.approx(m_full.coverage, abs=0.004), (
            f"after {k + 1} obstacles the incremental plan covers "
            f"{100 * (m_full.coverage - m_inc.coverage):.2f} pp less than a full replan"
        )

    assert merges >= 2, f"test did not exercise grouping (only {merges} merges)"


def test_route_visits_every_swath_exactly_once():
    """The tour must be a permutation of the swaths, after any change sequence.

    This is the invariant that broke loudest.  ``Swath.scanline`` is part of how
    the incremental planner identifies a stroke, and the swath-building helper
    numbered lines by their index *within the list it was given*.  Called one
    line at a time -- which is exactly what an incremental refresh does -- every
    swath came out numbered zero, so two swaths on different scanlines with the
    same x range compared equal.  The survivor list then kept both copies of one
    stroke, the tour grew longer than the swath list, and every path length the
    planner reported was inflated.

    Coverage stayed correct throughout, and the interval-level tests passed, so
    nothing smaller than this caught it.
    """
    base = F.make_field("rectilinear", seed=4, n_obstacles=4, target_area=25_000.0)
    params = make_params(angle=0.0)
    planner = IncrementalPlanner(base, params)

    def check(tag: str) -> None:
        route = planner._route
        swaths = planner._route_swaths
        indices = [step.index for step in route]
        assert len(indices) == len(set(indices)), (
            f"{tag}: the tour visits {len(indices) - len(set(indices))} swath(s) more than once"
        )
        assert len(indices) == len(swaths), (
            f"{tag}: tour has {len(indices)} steps for {len(swaths)} swaths"
        )
        assert all(0 <= i < len(swaths) for i in indices), f"{tag}: step index out of range"

    check("after construction")

    minx, miny, maxx, maxy = G.bounds_of(base.boundary)
    cy = 0.5 * (miny + maxy)
    half, step = 8.0, 22.0
    x0 = minx + 0.4 * (maxx - minx)
    added = 0
    for k in range(5):
        obs = G.normalise(box(x0 + k * step - half, cy - half, x0 + k * step + half, cy + half))
        if not base.boundary.contains(obs):
            continue
        planner.add_obstacle(obs)
        added += 1
        check(f"after obstacle {added}")

        for h in [s for s in list(planner._handle_group)][:1]:
            planner.remove_obstacle(h)
            check(f"after removing {h}")

    assert added >= 3, "test did not place enough obstacles"


def test_single_line_swath_build_keeps_the_scanline_index():
    """Building one scanline at a time must not renumber it to zero."""
    from cppclip.swaths import swaths_from_intervals

    intervals = [(0.0, 5.0), (9.0, 12.0)]
    one = swaths_from_intervals([intervals], [3.0], min_length=0.0)
    assert [s.scanline for s in one] == [0, 0]

    offset = swaths_from_intervals([intervals], [3.0], min_length=0.0, scanline_offset=7)
    assert [s.scanline for s in offset] == [7, 7]

    # The whole point: identical x ranges on different lines must stay distinct.
    same_x = [(0.0, 5.0)]
    a = swaths_from_intervals([same_x], [0.0], scanline_offset=0)[0]
    b = swaths_from_intervals([same_x], [6.0], scanline_offset=1)[0]
    assert (a.scanline, a.x0, a.x1) != (b.scanline, b.x0, b.x1)
