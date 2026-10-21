"""Polygon geometry helpers for clipping-driven coverage path planning (CPP).

This module is deliberately a *thin* layer over Shapely/GEOS.  It exists to fix
the conventions used by the rest of the package (metre-scale planar geometry,
y-up, exterior rings counter-clockwise, holes clockwise, everything returned as
a valid ``MultiPolygon``) and to provide the small primitives the scanline
clipper needs (edge extraction, ring iteration, offsets).

Nothing here does any planning; see :mod:`cppclip.sweep` for the clipping core
and :mod:`cppclip.planner` for the pipeline.
"""

from __future__ import annotations

from typing import Iterable, Iterator, Sequence

import numpy as np
from shapely import make_valid
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Polygon,
)
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

Point2D = tuple[float, float]
Ring = list[Point2D]

__all__ = [
    "polygon_from_rings",
    "normalise",
    "iter_polygons",
    "iter_rings",
    "free_space",
    "erode",
    "dilate",
    "ring_edges",
    "signed_area",
    "bounds_of",
    "segments_of",
    "total_area",
    "offset_ring_inward",
]


# --------------------------------------------------------------------------
# construction / normalisation
# --------------------------------------------------------------------------
def polygon_from_rings(shell: Sequence[Point2D], holes: Iterable[Sequence[Point2D]] = ()) -> Polygon:
    """Build a :class:`Polygon` from an explicit shell and hole list."""
    return Polygon(shell, [list(h) for h in holes])


def normalise(geom: BaseGeometry) -> MultiPolygon:
    """Return *geom* as a valid :class:`MultiPolygon` (possibly empty).

    Invalid input is repaired with GEOS ``make_valid`` rather than raising, so
    that benchmark field polygons harvested from the wild (self-touching
    boundaries, duplicate vertices) do not abort a whole experiment.
    """
    if geom is None or geom.is_empty:
        return MultiPolygon()

    if not geom.is_valid:
        geom = make_valid(geom)

    if isinstance(geom, Polygon):
        return MultiPolygon([geom]) if not geom.is_empty else MultiPolygon()

    if isinstance(geom, MultiPolygon):
        polys = [p for p in geom.geoms if not p.is_empty]
        return MultiPolygon(polys) if polys else MultiPolygon()

    if isinstance(geom, (GeometryCollection,)):
        polys: list[Polygon] = []
        for part in geom.geoms:
            polys.extend(iter_polygons(part))
        return MultiPolygon(polys) if polys else MultiPolygon()

    # Anything else (points/lines) carries no area and is dropped.
    return MultiPolygon()


def iter_polygons(geom: BaseGeometry) -> Iterator[Polygon]:
    """Yield every :class:`Polygon` inside *geom*, recursively."""
    if geom is None or geom.is_empty:
        return
    if isinstance(geom, Polygon):
        yield geom
    elif isinstance(geom, (MultiPolygon, GeometryCollection)):
        for part in geom.geoms:
            yield from iter_polygons(part)


def iter_rings(poly: Polygon) -> Iterator[tuple[Ring, bool]]:
    """Yield ``(ring, is_hole)`` for a polygon: exterior first, then holes."""
    yield list(poly.exterior.coords), False
    for interior in poly.interiors:
        yield list(interior.coords), True


def iter_geometries(geom: BaseGeometry) -> Iterator[BaseGeometry]:
    """Yield the leaf geometries inside *geom*, whatever their type.

    ``iter_polygons`` is the shape most callers want, but a boolean overlay can
    hand back a ``GeometryCollection`` mixing polygons and lines -- cutting a
    headland ring down to free space does exactly that -- and walking only the
    polygons silently drops the line work.
    """
    if geom is None or geom.is_empty:
        return
    if isinstance(geom, (MultiPolygon, MultiLineString, MultiPoint, GeometryCollection)):
        for part in geom.geoms:
            yield from iter_geometries(part)
    else:
        yield geom


def total_area(geom: BaseGeometry) -> float:
    """Total area of *geom*, tolerant of empty/None input."""
    if geom is None or geom.is_empty:
        return 0.0
    return float(geom.area)


# --------------------------------------------------------------------------
# free space
# --------------------------------------------------------------------------
def free_space(boundary: BaseGeometry, obstacles: Iterable[BaseGeometry] = ()) -> MultiPolygon:
    """The area a machine may drive on: *boundary* minus every obstacle.

    Obstacles are unioned first so that mutually overlapping obstacles do not
    punch the boundary twice (``difference`` is idempotent, but a single union
    keeps GEOS's overlay graph smaller).
    """
    bnd = normalise(boundary)
    if bnd.is_empty:
        return MultiPolygon()

    obs = [o for o in (normalise(o) for o in obstacles) if not o.is_empty]
    if not obs:
        return bnd

    return normalise(bnd.difference(unary_union(obs)))


def erode(geom: BaseGeometry, distance: float) -> MultiPolygon:
    """Inward offset (negative buffer) by *distance* metres."""
    if distance <= 0:
        return normalise(geom)
    return normalise(geom.buffer(-float(distance), quad_segs=8, join_style="mitre"))


def dilate(geom: BaseGeometry, distance: float) -> MultiPolygon:
    """Outward offset (positive buffer) by *distance* metres."""
    if distance <= 0:
        return normalise(geom)
    return normalise(geom.buffer(float(distance), quad_segs=8, join_style="mitre"))


def offset_ring_inward(geom: BaseGeometry, distance: float) -> MultiPolygon:
    """Alias of :func:`erode`, named for the headland use-case.

    In agricultural CPP the *headland* (地头) is the strip of width ``h`` just
    inside the field boundary; it is the region between the field and its
    inward offset by ``h``.
    """
    return erode(geom, distance)


# --------------------------------------------------------------------------
# rings / edges
# --------------------------------------------------------------------------
def signed_area(ring: Sequence[Point2D]) -> float:
    """Signed area of a closed ring (positive == counter-clockwise)."""
    pts = np.asarray(ring, dtype=float)
    if pts.shape[0] < 4:
        return 0.0
    x, y = pts[:, 0], pts[:, 1]
    return 0.5 * float(np.dot(x[:-1], y[1:]) - np.dot(x[1:], y[:-1]))


def ring_edges(ring: Sequence[Point2D]) -> np.ndarray:
    """Turn a closed ring into an ``(n, 4)`` array of ``(x0, y0, x1, y1)`` edges.

    The ring is treated as closed: if the caller omitted the repeated last
    vertex it is appended, and degenerate (zero-length) edges are dropped.
    """
    pts = np.asarray(ring, dtype=float)
    if pts.ndim != 2 or pts.shape[0] < 2:
        return np.empty((0, 4), dtype=float)

    if not np.allclose(pts[0], pts[-1]):
        pts = np.vstack([pts, pts[0]])

    edges = np.column_stack([pts[:-1], pts[1:]])  # (n, 4)
    keep = ~np.all(np.isclose(edges[:, :2], edges[:, 2:]), axis=1)
    return edges[keep]


def bounds_of(geom: BaseGeometry) -> tuple[float, float, float, float]:
    """``(minx, miny, maxx, maxy)``; returns zeros for empty geometry."""
    if geom is None or geom.is_empty:
        return (0.0, 0.0, 0.0, 0.0)
    return tuple(float(v) for v in geom.bounds)  # type: ignore[return-value]


def segments_of(geom: BaseGeometry) -> list[tuple[Point2D, Point2D]]:
    """Flatten any (multi)line/collection geometry into a list of segments."""
    out: list[tuple[Point2D, Point2D]] = []
    if geom is None or geom.is_empty:
        return out

    if isinstance(geom, LineString):
        coords = list(geom.coords)
        out.extend((coords[i], coords[i + 1]) for i in range(len(coords) - 1))
    elif isinstance(geom, (MultiLineString, GeometryCollection)):
        for part in geom.geoms:
            out.extend(segments_of(part))
    return out
