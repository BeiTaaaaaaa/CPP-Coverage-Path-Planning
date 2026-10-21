"""Correctness tests for the clipping core.

The central claim of :mod:`cppclip.sweep` is that an edge-table + even-odd
parity computation reproduces exact polygon clipping.  That claim is what the
whole package rests on, so it is tested directly against GEOS ground truth on
randomised scenes rather than only on hand-drawn examples.
"""

from __future__ import annotations

import numpy as np
import pytest
from shapely.geometry import LineString, Polygon, box

from cppclip import fields as F
from cppclip import geometry as G
from cppclip.sweep import ScanlineClipper, check_rings


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def assert_intervals_close(
    got: list[tuple[float, float]], want: list[tuple[float, float]], tol: float = 1e-9
) -> None:
    got = sorted(got)
    want = sorted(want)
    assert len(got) == len(want), f"interval count differs: got {got} want {want}"
    for (a0, a1), (b0, b1) in zip(got, want):
        assert abs(a0 - b0) <= tol and abs(a1 - b1) <= tol, f"{got} != {want}"


def build(region, width: float, margin: float = 0.0) -> ScanlineClipper:
    return ScanlineClipper.from_geometry(region, width, margin=margin)


# --------------------------------------------------------------------------
# basic geometry
# --------------------------------------------------------------------------
def test_scanline_grid_tiles_without_half_strips():
    ys = ScanlineClipper.scanline_grid(0.0, 100.0, 10.0)
    assert ys.size == 10
    assert np.isclose(ys[0], 5.0)
    assert np.isclose(ys[-1], 95.0)
    assert np.allclose(np.diff(ys), 10.0)


def test_scanline_grid_covers_exactly_with_non_divisible_height():
    ys = ScanlineClipper.scanline_grid(0.0, 105.0, 10.0)
    assert ys.size == 11  # ceil(105/10)
    assert np.isclose(ys[0], 105.0 / 11 / 2)
    assert np.isclose(ys[-1], 105.0 - 105.0 / 11 / 2)


def test_square_gives_full_width_intervals():
    sq = G.normalise(box(0, 0, 100, 100))
    clip = build(sq, width=10.0)
    for i in range(len(clip)):
        assert_intervals_close(clip.intervals_at(i), [(0.0, 100.0)], tol=1e-9)


def test_hole_splits_scanline_into_two_intervals():
    outer = box(0, 0, 100, 100)
    hole = box(40, 40, 60, 60)
    region = G.normalise(outer.difference(hole))
    clip = build(region, width=5.0)
    hit = [i for i in range(len(clip)) if len(clip.intervals_at(i)) == 2]
    assert hit, "scanlines crossing the hole must yield two intervals"
    for i in hit:
        assert_intervals_close(clip.intervals_at(i), [(0.0, 40.0), (60.0, 100.0)], tol=1e-9)


def test_concave_region_intervals_track_the_notch():
    geom = F.u_shape(100.0, 100.0, notch_w=40.0, notch_h=50.0)
    clip = build(geom, width=5.0)
    # Scanlines in the notch band must be split in two by the notch.
    notch_band = [i for i in range(len(clip)) if clip.ys[i] > 50.0]
    assert notch_band
    for i in notch_band:
        assert len(clip.intervals_at(i)) == 2


def test_total_covered_length_approximates_area():
    """Integrating interval length over the grid must recover the area."""
    geom = F.star_polygon(14, 60.0, 110.0, seed=7)
    width = 1.0
    clip = build(geom, width=width)
    total = sum(clip.covered_length(i) for i in range(len(clip))) * width
    assert total == pytest.approx(geom.area, rel=0.02)


def test_line_outside_region_has_no_intervals():
    sq = G.normalise(box(0, 0, 10, 10))
    clip = ScanlineClipper([-5.0, 5.0, 15.0])
    clip.add_geometry(sq)
    clip.set_reference(sq)
    assert clip.intervals_at(0) == []
    assert clip.intervals_at(1) == [(0.0, 10.0)]
    assert clip.intervals_at(2) == []


def test_vertex_exactly_on_scanline_is_not_double_counted():
    """The half-open rule must count a shared vertex once, not zero or twice."""
    tri = G.normalise(Polygon([(0, 0), (10, 0), (5, 10)]))
    clip = ScanlineClipper([0.0, 5.0, 10.0])
    clip.add_geometry(tri)
    assert_intervals_close(clip.intervals_at(0), [(0.0, 10.0)], tol=1e-9)  # base edge
    assert_intervals_close(clip.intervals_at(1), [(2.5, 7.5)], tol=1e-9)
    assert clip.intervals_at(2) == []  # apex: degenerate, excluded


def test_horizontal_edge_never_contributes():
    sq = G.normalise(box(0, 0, 10, 10))
    clip = ScanlineClipper([5.0])
    clip.add_geometry(sq)
    assert clip.n_edges == 2  # only the two vertical edges survive
    assert_intervals_close(clip.intervals_at(0), [(0.0, 10.0)])


# --------------------------------------------------------------------------
# agreement with exact GEOS clipping
# --------------------------------------------------------------------------
@pytest.mark.parametrize("seed", range(8))
@pytest.mark.parametrize("n_obstacles", [0, 3, 12])
def test_fast_path_matches_geos_on_random_scenes(seed: int, n_obstacles: int):
    field = F.make_field("star", seed=seed, n_obstacles=n_obstacles, target_area=10_000.0)
    free = field.free
    if free.is_empty:
        pytest.skip("degenerate scene")
    clip = build(free, width=3.0)
    for i in range(len(clip)):
        assert_intervals_close(clip.intervals_at(i), clip.intervals_geos(i), tol=1e-7)


@pytest.mark.parametrize("seed", range(6))
def test_fast_path_matches_geos_on_rectilinear_fields(seed: int):
    field = F.make_field("rectilinear", seed=seed, n_obstacles=6, target_area=15_000.0)
    free = field.free
    if free.is_empty:
        pytest.skip("degenerate scene")
    clip = build(free, width=2.5)
    for i in range(len(clip)):
        assert_intervals_close(clip.intervals_at(i), clip.intervals_geos(i), tol=1e-7)


def test_boundary_plus_obstacle_edges_match_boolean_difference():
    """Feeding shell+obstacles as separate sources must equal the GEOS difference.

    This is the equivalence the incremental planner relies on: it never recomputes
    a boolean difference, it just toggles one obstacle's edges.
    """
    field = F.make_field("rect", seed=1, n_obstacles=10, target_area=10_000.0)
    width = 4.0
    ys = ScanlineClipper.scanline_grid(*G.bounds_of(field.boundary)[1::2], width)

    # (a) parity over shell edges + every obstacle's edges, added separately
    parity = ScanlineClipper(ys)
    parity.add_geometry(field.boundary)
    for obs in field.obstacles:
        parity.add_geometry(obs)

    # (b) exact GEOS free space
    exact = build(field.free, width)

    assert parity.ys.size == exact.ys.size
    for i in range(len(parity)):
        assert_intervals_close(parity.intervals_at(i), exact.intervals_at(i), tol=1e-7)


def test_check_rings_accepts_proper_nesting_but_flags_partial_overlap():
    from shapely.geometry import MultiPolygon

    # An obstacle strictly inside the field is a *hole*: correct, not a defect.
    nested = MultiPolygon([box(0, 0, 100, 100), box(40, 40, 60, 60)])
    assert check_rings(nested) == []

    # Partial overlap crosses rings and breaks parity.
    overlapping = MultiPolygon([box(0, 0, 100, 100), box(50, 50, 150, 150)])
    assert any("overlap" in w for w in check_rings(overlapping))

    # Depth 3: a polygon inside an obstacle would be read back as drivable.
    deep = MultiPolygon([box(0, 0, 100, 100), box(10, 10, 90, 90), box(40, 40, 60, 60)])
    assert any("depth" in w for w in check_rings(deep))


@pytest.mark.parametrize("kind", ["rect", "l", "u", "star", "rectilinear"])
@pytest.mark.parametrize("seed", range(4))
def test_generated_scenes_satisfy_the_parity_precondition(kind: str, seed: int):
    """Regression guard: the generator must never emit an overlapping scene.

    An earlier version used ``distance(p) < clearance`` to reject collisions,
    which silently accepted overlapping obstacles whenever ``clearance == 0``
    (distance is 0 for overlapping polygons, and ``0 < 0`` is false).  The
    result was a scene whose parity intervals disagreed with GEOS.  This test
    pins the invariant at the source.
    """
    from shapely.geometry import MultiPolygon

    field = F.make_field(kind, seed=seed, n_obstacles=20, target_area=10_000.0)
    ring_set = MultiPolygon(
        [p for poly in field.boundary.geoms for p in [poly]]
        + [p for obs in field.obstacles for p in obs.geoms]
    )
    assert check_rings(ring_set) == [], f"generated scene violates the precondition: {kind}/{seed}"


# --------------------------------------------------------------------------
# incrementality
# --------------------------------------------------------------------------
def test_insert_then_compare_with_rebuild():
    """Adding an obstacle incrementally must equal building the scene anew."""
    field = F.make_field("rect", seed=3, n_obstacles=0, target_area=20_000.0)
    region = G.erode(field.boundary, 5.0)
    width = 4.0

    clip = build(region, width)
    before = [clip.intervals_at(i) for i in range(len(clip))]

    new_obs = F.random_obstacles(region, 4, seed=99, size_range=(8.0, 15.0))
    assert new_obs, "test scene produced no obstacles"
    affected = np.zeros(len(clip), dtype=bool)
    for obs in new_obs:
        _src, aff = clip.add_geometry(obs)
        affected[aff] = True

    # Unaffected scanlines must be byte-identical to before.
    for i in np.flatnonzero(~affected):
        assert clip.intervals_at(int(i)) == before[i]

    rebuilt = build(G.free_space(region, new_obs), width)
    for i in range(len(clip)):
        assert_intervals_close(clip.intervals_at(i), rebuilt.intervals_at(i), tol=1e-7)


def test_remove_restores_original_intervals():
    field = F.make_field("rect", seed=4, n_obstacles=0, target_area=20_000.0)
    region = G.erode(field.boundary, 5.0)
    width = 4.0

    clip = build(region, width)
    baseline = [clip.intervals_at(i) for i in range(len(clip))]

    obs = F.random_obstacles(region, 3, seed=11, size_range=(8.0, 15.0))
    srcs = [clip.add_geometry(o)[0] for o in obs]
    assert any(clip.intervals_at(i) != baseline[i] for i in range(len(clip)))

    for s in srcs:
        clip.remove_source(s)

    for i in range(len(clip)):
        assert_intervals_close(clip.intervals_at(i), baseline[i], tol=1e-9)


def test_affected_scanlines_equal_obstacle_y_span():
    """The incremental work set must be exactly the obstacle's y span."""
    region = G.erode(G.normalise(box(0, 0, 500, 200)), 5.0)
    clip = build(region, width=2.0)
    obs = G.normalise(box(200, 80, 240, 120))
    _src, aff = clip.add_geometry(obs)
    assert aff.size > 0
    ys = clip.ys[aff]
    assert ys.min() >= 80.0
    assert ys.max() < 120.0
    # and the span must be tight: the scanline just below must not be touched
    expected = int(np.searchsorted(clip.ys, 120.0, "left")) - int(
        np.searchsorted(clip.ys, 80.0, "left")
    )
    assert aff.size == expected


def test_dead_edges_are_compacted_and_stay_correct():
    """Exercise the tombstone/compaction path with many insert/remove cycles."""
    region = G.erode(G.normalise(box(0, 0, 400, 300)), 5.0)
    clip = build(region, width=2.0)
    rng = np.random.default_rng(0)
    for _ in range(40):
        cx, cy = rng.uniform(50, 350), rng.uniform(50, 250)
        obs = G.normalise(box(cx - 8, cy - 8, cx + 8, cy + 8))
        src, _ = clip.add_geometry(obs)
        clip.remove_source(src)
    # After all removals the scene must be the pristine region again.
    fresh = build(region, 2.0)
    for i in range(len(clip)):
        assert_intervals_close(clip.intervals_at(i), fresh.intervals_at(i), tol=1e-9)
