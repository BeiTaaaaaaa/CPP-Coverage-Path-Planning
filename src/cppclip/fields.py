"""Synthetic and real field geometries for benchmarking.

The generator exists because a benchmark of *my* algorithms must control the two
properties that drive the cost of coverage planning:

* **concavity** -- how much the swath pattern has to be broken up, and
* **in-field obstacles** -- how often a single scanline carries more than one
  effective interval.

Real field data (see :mod:`cppclip.io_fields`) is the ground truth for the
final evaluation; these generators are what make mechanism-level experiments
possible (e.g. sweeping obstacle count while holding area fixed).

Every generated scene is guaranteed to satisfy the even-odd precondition of
:mod:`cppclip.sweep`: obstacles are pairwise disjoint and strictly inside the
field, so the parity rule is exact.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Iterator, Sequence

import numpy as np
from shapely import affinity
from shapely.geometry import MultiPolygon, Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from . import geometry as G

__all__ = [
    "Field",
    "rectangle",
    "l_shape",
    "u_shape",
    "star_polygon",
    "rectilinear_field",
    "random_obstacles",
    "make_field",
    "scene_grid",
]


@dataclass(slots=True)
class Field:
    """A coverage planning scene: a boundary plus in-field obstacles."""

    name: str
    boundary: MultiPolygon
    obstacles: list[MultiPolygon] = dc_field(default_factory=list)
    meta: dict = dc_field(default_factory=dict)

    @property
    def free(self) -> MultiPolygon:
        """Drivable area: boundary minus all obstacles."""
        return G.free_space(self.boundary, self.obstacles)

    @property
    def area(self) -> float:
        return G.total_area(self.boundary)

    @property
    def free_area(self) -> float:
        return G.total_area(self.free)

    @property
    def obstacle_area(self) -> float:
        return sum(G.total_area(o) for o in self.obstacles)

    def obstacle_geometry(self) -> BaseGeometry:
        return unary_union(self.obstacles) if self.obstacles else MultiPolygon()

    def bounds(self) -> tuple[float, float, float, float]:
        return G.bounds_of(self.boundary)

    def size(self) -> tuple[float, float]:
        minx, miny, maxx, maxy = self.bounds()
        return (maxx - minx, maxy - miny)

    def with_obstacles(self, obstacles: Sequence[BaseGeometry]) -> "Field":
        return Field(self.name, self.boundary, [G.normalise(o) for o in obstacles], dict(self.meta))


# --------------------------------------------------------------------------
# primitives
# --------------------------------------------------------------------------
def rectangle(width: float, height: float, origin: tuple[float, float] = (0.0, 0.0)) -> MultiPolygon:
    x, y = origin
    return G.normalise(box(x, y, x + width, y + height))


def l_shape(width: float, height: float, cut: float) -> MultiPolygon:
    """An L: a *width* x *height* rectangle with a *cut* square removed."""
    outer = box(0, 0, width, height)
    notch = box(width - cut, height - cut, width, height)
    return G.normalise(outer.difference(notch))


def u_shape(width: float, height: float, notch_w: float, notch_h: float) -> MultiPolygon:
    """A U: rectangle with a notch cut from the middle of the top edge."""
    outer = box(0, 0, width, height)
    x0 = (width - notch_w) / 2.0
    notch = box(x0, height - notch_h, x0 + notch_w, height)
    return G.normalise(outer.difference(notch))


def star_polygon(
    n_vertices: int = 12,
    r_min: float = 40.0,
    r_max: float = 100.0,
    seed: int | None = None,
    centre: tuple[float, float] = (0.0, 0.0),
) -> MultiPolygon:
    """A random star-shaped (hence simple, possibly concave) polygon.

    Sampling angles in sorted order around a common centre guarantees the ring
    is simple, so it never needs repair -- which keeps the benchmark honest,
    since a repaired polygon would silently change area.
    """
    rng = np.random.default_rng(seed)
    angles = np.sort(rng.uniform(0.0, 2.0 * np.pi, size=n_vertices))
    # Guarantee a minimum angular gap so no two vertices coincide.
    gaps = np.diff(np.concatenate([angles, angles[:1] + 2 * np.pi]))
    if np.any(gaps < 1e-6):
        angles = np.linspace(0.0, 2.0 * np.pi, n_vertices, endpoint=False)
    radii = rng.uniform(r_min, r_max, size=n_vertices)
    cx, cy = centre
    pts = np.column_stack([cx + radii * np.cos(angles), cy + radii * np.sin(angles)])
    return G.normalise(Polygon(pts))


def rectilinear_field(
    width: float = 200.0,
    height: float = 150.0,
    n_notches: int = 3,
    seed: int | None = None,
) -> MultiPolygon:
    """A rectangle with random rectangular bites taken out of its sides.

    Rectilinear boundaries are what real arable fields look like, and they are
    the adversarial case for a scanline clipper: long axis-aligned edges span
    many scanlines and therefore load up the edge table.
    """
    rng = np.random.default_rng(seed)
    geom: BaseGeometry = box(0, 0, width, height)
    for _ in range(n_notches):
        side = int(rng.integers(0, 4))
        depth = float(rng.uniform(0.10, 0.30)) * min(width, height)
        span = float(rng.uniform(0.15, 0.35))
        if side == 0:  # bottom
            x0 = float(rng.uniform(0.0, 1.0 - span)) * width
            cut = box(x0, 0.0, x0 + span * width, depth)
        elif side == 1:  # top
            x0 = float(rng.uniform(0.0, 1.0 - span)) * width
            cut = box(x0, height - depth, x0 + span * width, height)
        elif side == 2:  # left
            y0 = float(rng.uniform(0.0, 1.0 - span)) * height
            cut = box(0.0, y0, depth, y0 + span * height)
        else:  # right
            y0 = float(rng.uniform(0.0, 1.0 - span)) * height
            cut = box(width - depth, y0, width, y0 + span * height)
        geom = geom.difference(cut)
    return G.normalise(geom)


# --------------------------------------------------------------------------
# obstacles
# --------------------------------------------------------------------------
def random_obstacles(
    region: BaseGeometry,
    n: int,
    size_range: tuple[float, float] = (5.0, 20.0),
    seed: int | None = None,
    clearance: float = 0.0,
    max_attempts: int = 4000,
) -> list[MultiPolygon]:
    """Place *n* pairwise-disjoint circular obstacles strictly inside *region*.

    Rejection sampling with an explicit *clearance* gap.  Guaranteeing
    disjointness up front is what licenses the even-odd fast path in
    :mod:`cppclip.sweep`; the function therefore also shrinks the placement area
    by the largest radius so no obstacle straddles the boundary.
    """
    rng = np.random.default_rng(seed)
    r_lo, r_hi = float(size_range[0]), float(size_range[1])

    # Placement area: erode by the largest radius so that a full obstacle fits
    # with a margin.  Narrow fields (a U-shape's arms, a thin L) cannot afford
    # that, so fall back to progressively smaller erosions rather than ending up
    # with an empty sampling box.
    inner = G.normalise(region)
    for shrink in (r_hi, (r_lo + r_hi) / 2.0, r_lo, 0.0):
        candidate = G.erode(region, shrink) if shrink > 0 else G.normalise(region)
        if not candidate.is_empty and candidate.area > 0:
            inner = candidate
            break
    minx, miny, maxx, maxy = G.bounds_of(inner)
    if maxx <= minx or maxy <= miny:
        return []

    placed: list[Polygon] = []
    attempts = 0
    while len(placed) < n and attempts < max_attempts:
        attempts += 1
        r = float(rng.uniform(r_lo, r_hi))
        if maxx - minx <= 2.0 * r or maxy - miny <= 2.0 * r:
            continue
        cx = float(rng.uniform(minx + r, maxx - r))
        cy = float(rng.uniform(miny + r, maxy - r))
        cand = Polygon(
            [(cx + r * np.cos(t), cy + r * np.sin(t)) for t in np.linspace(0, 2 * np.pi, 24, endpoint=False)]
        )
        if not inner.contains(cand):
            continue
        # Disjointness is what licenses the even-odd fast path in cppclip.sweep,
        # so it must be enforced strictly.  Note `distance(p) < clearance` alone
        # is NOT sufficient: for touching or overlapping polygons the distance
        # is 0, so with clearance == 0 the test would pass and we would emit
        # exactly the overlapping ring set that breaks parity.
        if any(cand.intersects(p) or cand.distance(p) < clearance for p in placed):
            continue
        placed.append(cand)

    return [G.normalise(p) for p in placed]


# --------------------------------------------------------------------------
# scene assembly
# --------------------------------------------------------------------------
def make_field(
    kind: str = "rect",
    seed: int | None = None,
    n_obstacles: int = 0,
    target_area: float | None = None,
    **kwargs,
) -> Field:
    """Build a named synthetic scene.

    Parameters
    ----------
    kind:
        ``"rect"``, ``"l"``, ``"u"``, ``"star"`` or ``"rectilinear"``.
    n_obstacles:
        Number of disjoint circular obstacles to place inside the field.
    target_area:
        If given, the boundary is scaled so its area equals this value (m^2).
        Area normalisation is essential for fair path-length comparisons across
        fields of different size.
    """
    if kind == "rect":
        bnd = rectangle(kwargs.get("width", 200.0), kwargs.get("height", 150.0))
    elif kind == "l":
        bnd = l_shape(kwargs.get("width", 200.0), kwargs.get("height", 150.0), kwargs.get("cut", 60.0))
    elif kind == "u":
        bnd = u_shape(
            kwargs.get("width", 200.0),
            kwargs.get("height", 150.0),
            kwargs.get("notch_w", 80.0),
            kwargs.get("notch_h", 60.0),
        )
    elif kind == "star":
        bnd = star_polygon(
            kwargs.get("n_vertices", 12),
            kwargs.get("r_min", 60.0),
            kwargs.get("r_max", 110.0),
            seed=seed,
        )
    elif kind == "rectilinear":
        bnd = rectilinear_field(
            kwargs.get("width", 200.0),
            kwargs.get("height", 150.0),
            kwargs.get("n_notches", 3),
            seed=seed,
        )
    else:
        raise ValueError(f"unknown field kind: {kind!r}")

    if target_area is not None and bnd.area > 0:
        factor = float(np.sqrt(target_area / bnd.area))
        bnd = G.normalise(affinity.scale(bnd, xfact=factor, yfact=factor, origin=(0.0, 0.0)))

    obstacles = (
        random_obstacles(bnd, n_obstacles, seed=seed, size_range=kwargs.get("size_range", (5.0, 20.0)))
        if n_obstacles > 0
        else []
    )
    return Field(
        name=f"{kind}-s{seed}-o{n_obstacles}",
        boundary=bnd,
        obstacles=obstacles,
        meta={"kind": kind, "seed": seed, "n_obstacles": len(obstacles)},
    )


def scene_grid(
    kinds: Sequence[str] = ("rect", "l", "u", "star", "rectilinear"),
    obstacle_counts: Sequence[int] = (0, 5, 15, 30),
    seeds: Sequence[int] = tuple(range(3)),
    target_area: float = 10_000.0,
) -> Iterator[Field]:
    """Deterministic sweep over (shape x obstacle count x seed)."""
    for kind in kinds:
        for n_obs in obstacle_counts:
            for seed in seeds:
                yield make_field(kind, seed=seed, n_obstacles=n_obs, target_area=target_area)
