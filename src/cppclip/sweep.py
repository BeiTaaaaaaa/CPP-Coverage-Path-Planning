"""Clipping-driven scanline interval extraction.

This is the core of the package.  The idea is taken straight from scanline
polygon fill in computer graphics:

1. Every ring of the target region (field shell, field holes, obstacles) is
   decomposed into edges.
2. Each edge is registered, once, in the *scanline edge table* -- the list of
   scanlines whose ``y`` it spans.
3. The "effective intervals" (有效区间) of a scanline are obtained by taking
   the ``x`` where the scanline crosses an active edge, sorting them, and
   pairing consecutive crossings under the even-odd rule.

Compared with a Boustrophedon Cellular Decomposition (BCD) baseline this buys
three things:

* **No cell decomposition.** Concavity and holes fall out of the parity rule,
  so no sweep-line event handling and no cell-merging heuristics are needed.
* **Exactness.** Intervals are analytic, not rasterised, so cell boundaries do
  not sit on a grid.
* **Incrementality.** Because each edge is indexed by its ``y`` span, inserting
  or deleting one obstacle touches only the scanlines inside that span.  This
  is the structural property that makes dynamic replanning cheap; see
  :mod:`cppclip.incremental`.

The active-edge test uses the standard half-open convention ``y0 <= y < y1``
with edges normalised to ``y0 < y1``.  That convention is what makes vertices,
horizontal edges and scanlines lying exactly on a vertex behave correctly, and
it is the same rule a scanline rasteriser uses.

Assumption
----------
The even-odd rule is exact when the ring set describes a well-formed region:
one or more disjoint shells whose holes are strictly inside and do not overlap
each other.  It is *not* correct for obstacles that overlap each other, since a
doubly-covered point toggles parity twice.  :func:`check_rings` detects that
case; :meth:`ScanlineClipper.intervals_geos` gives the GEOS ground truth used
for cross-validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
from shapely.geometry import LineString, Polygon
from shapely.geometry.base import BaseGeometry

from . import geometry as G

__all__ = ["Edge", "ScanlineClipper", "Interval", "check_rings"]

Interval = tuple[float, float]


@dataclass(slots=True)
class Edge:
    """A polygon edge normalised so that ``y0 < y1``."""

    x0: float
    y0: float
    x1: float
    y1: float
    slope: float  # dx/dy
    source: int  # id of the ring-set this edge belongs to
    dead: bool = False

    @staticmethod
    def make(ax: float, ay: float, bx: float, by: float, source: int) -> "Edge | None":
        """Build an edge from two endpoints, or ``None`` if it is degenerate.

        Horizontal edges are dropped: under the half-open active rule they can
        never contribute a crossing, and dropping them early keeps the tables
        small.
        """
        if ay == by:
            return None
        if ay > by:
            ax, ay, bx, by = bx, by, ax, ay
        return Edge(x0=ax, y0=ay, x1=bx, y1=by, slope=(bx - ax) / (by - ay), source=source)

    def x_at(self, y: float) -> float:
        """``x`` where this edge crosses the horizontal line at *y*."""
        return self.x0 + (y - self.y0) * self.slope


class ScanlineClipper:
    """Edge-table based scanline clipper with incremental insert/remove.

    Parameters
    ----------
    ys:
        Ascending ``y`` coordinates of the scanlines (swath centre lines).
    x_pad:
        How far beyond the scene bounds the synthetic clipping line extends in
        :meth:`intervals_geos`.  Has no effect on the fast path.
    """

    def __init__(self, ys: Sequence[float] | np.ndarray, x_pad: float = 1.0) -> None:
        self.ys = np.asarray(ys, dtype=float)
        if self.ys.ndim != 1:
            raise ValueError("ys must be a 1-D sequence of scanline heights")
        if self.ys.size > 1 and np.any(np.diff(self.ys) < 0):
            raise ValueError("ys must be sorted ascending")
        self.x_pad = float(x_pad)

        self._edges: list[Edge] = []
        # _buckets[i] = ids of edges whose y-span covers scanline i
        self._buckets: list[list[int]] = [[] for _ in range(self.ys.size)]
        # source id -> ids of the edges it contributed
        self._sources: dict[int, list[int]] = {}
        self._next_source = 0
        self._n_dead = 0
        self._reference_geom: BaseGeometry | None = None

    # ------------------------------------------------------------------
    # introspection
    # ------------------------------------------------------------------
    def __len__(self) -> int:
        return int(self.ys.size)

    @property
    def n_scanlines(self) -> int:
        return int(self.ys.size)

    @property
    def n_edges(self) -> int:
        return len(self._edges)

    @property
    def n_live_edges(self) -> int:
        return len(self._edges) - self._n_dead

    @property
    def n_sources(self) -> int:
        return len(self._sources)

    def edge_load(self) -> np.ndarray:
        """Live active-edge count per scanline -- the algorithm's work profile."""
        out = np.empty(self.ys.size, dtype=int)
        for i, bucket in enumerate(self._buckets):
            out[i] = sum(0 if self._edges[e].dead else 1 for e in bucket)
        return out

    # ------------------------------------------------------------------
    # scanline index arithmetic
    # ------------------------------------------------------------------
    def scanline_slice(self, y_lo: float, y_hi: float) -> tuple[int, int]:
        """Half-open index range ``[i0, i1)`` of scanlines with ``y_lo <= y < y_hi``.

        This is the only place the question "which scanlines does this edge
        affect?" is answered, and therefore the only place the incremental
        speed-up comes from: an edge spanning a short ``y`` range touches few
        scanlines.
        """
        i0 = int(np.searchsorted(self.ys, y_lo, side="left"))
        i1 = int(np.searchsorted(self.ys, y_hi, side="left"))
        return i0, i1

    # ------------------------------------------------------------------
    # mutation
    # ------------------------------------------------------------------
    def add_geometry(self, geom: BaseGeometry) -> tuple[int, np.ndarray]:
        """Register every edge of *geom*; return ``(source_id, affected_scanlines)``.

        The affected scanlines are exactly those whose active-edge set changed,
        i.e. the ones whose intervals must be recomputed.
        """
        source = self._next_source
        self._next_source += 1

        new_edges: list[Edge] = []
        for poly in G.iter_polygons(geom):
            for ring, _is_hole in G.iter_rings(poly):
                for ex0, ey0, ex1, ey1 in G.ring_edges(ring):
                    e = Edge.make(float(ex0), float(ey0), float(ex1), float(ey1), source)
                    if e is not None:
                        new_edges.append(e)

        if not new_edges:
            self._sources[source] = []
            return source, np.empty(0, dtype=int)

        affected = np.zeros(self.ys.size, dtype=bool)
        ids: list[int] = []
        for e in new_edges:
            eid = len(self._edges)
            self._edges.append(e)
            ids.append(eid)
            i0, i1 = self.scanline_slice(e.y0, e.y1)
            for i in range(i0, i1):
                self._buckets[i].append(eid)
            if i1 > i0:
                affected[i0:i1] = True

        self._sources[source] = ids
        return source, np.flatnonzero(affected)

    def remove_source(self, source: int) -> np.ndarray:
        """Detach every edge contributed by *source*; return affected scanlines.

        Edges are tombstoned rather than spliced out of the buckets so that the
        ids of other edges stay stable.  :meth:`intervals_at` skips dead ids,
        and a compaction pass runs once the dead fraction gets large.
        """
        ids = self._sources.pop(source, None)
        if not ids:
            return np.empty(0, dtype=int)

        affected = np.zeros(self.ys.size, dtype=bool)
        for eid in ids:
            e = self._edges[eid]
            e.dead = True
            self._n_dead += 1
            i0, i1 = self.scanline_slice(e.y0, e.y1)
            if i1 > i0:
                affected[i0:i1] = True

        self._maybe_compact()
        return np.flatnonzero(affected)

    def _maybe_compact(self) -> None:
        """Rebuild the tables once dead edges outnumber live ones."""
        if self._n_dead == 0 or len(self._edges) < 64:
            return
        if self._n_dead * 2 < len(self._edges):
            return
        self._rebuild()

    def _rebuild(self) -> None:
        """Drop tombstoned edges and re-bucket everything from scratch."""
        remap: dict[int, int] = {}
        keep: list[Edge] = []
        for eid, e in enumerate(self._edges):
            if not e.dead:
                remap[eid] = len(keep)
                keep.append(e)
        self._edges = keep
        self._n_dead = 0
        self._buckets = [[] for _ in range(self.ys.size)]
        for eid, e in enumerate(self._edges):
            i0, i1 = self.scanline_slice(e.y0, e.y1)
            for i in range(i0, i1):
                self._buckets[i].append(eid)
        self._sources = {
            s: [remap[e] for e in ids if e in remap] for s, ids in self._sources.items()
        }

    # ------------------------------------------------------------------
    # query
    # ------------------------------------------------------------------
    def crossings_at(self, i: int) -> np.ndarray:
        """Sorted ``x`` coordinates of the live active edges on scanline *i*."""
        bucket = self._buckets[i]
        if not bucket:
            return np.empty(0, dtype=float)
        edges = self._edges
        y = self.ys[i]
        xs = np.fromiter(
            (edges[eid].x_at(y) for eid in bucket if not edges[eid].dead),
            dtype=float,
        )
        xs.sort()
        return xs

    def intervals_at(self, i: int) -> list[Interval]:
        """Effective intervals on scanline *i*, by the even-odd rule."""
        xs = self.crossings_at(i)
        if xs.size < 2:
            return []
        # Pair consecutive crossings.  An odd count means the ring set is open
        # or numerically inconsistent; drop the trailing crossing rather than
        # emit a half-open interval that would silently over-cover.
        n_pairs = xs.size // 2
        lo = xs[0 : 2 * n_pairs : 2]
        hi = xs[1 : 2 * n_pairs : 2]
        keep = hi > lo
        return [(float(a), float(b)) for a, b in zip(lo[keep], hi[keep])]

    def all_intervals(self, indices: Iterable[int] | None = None) -> list[list[Interval]]:
        """Effective intervals for every (or the given) scanline(s)."""
        idx = range(self.ys.size) if indices is None else indices
        return [self.intervals_at(i) for i in idx]

    def covered_length(self, i: int) -> float:
        """Total working length on scanline *i* (sum of its intervals)."""
        return float(sum(b - a for a, b in self.intervals_at(i)))

    # ------------------------------------------------------------------
    # reference implementation / validation
    # ------------------------------------------------------------------
    def set_reference(self, geom: BaseGeometry) -> None:
        """Attach the exact free-space polygon used by :meth:`intervals_geos`."""
        self._reference_geom = G.normalise(geom)

    def intervals_geos(self, i: int) -> list[Interval]:
        """Ground truth for scanline *i*, computed by GEOS polygon clipping.

        Intersects a long horizontal segment with the exact free-space polygon.
        This is the "graphics clipping" reference -- a parametric clip of a line
        against the region -- and the test-suite uses it to prove the edge-table
        fast path agrees with exact boolean geometry.
        """
        if self._reference_geom is None:
            raise RuntimeError("set_reference() must be called before intervals_geos()")
        if self._reference_geom.is_empty:
            return []
        minx, _miny, maxx, _maxy = self._reference_geom.bounds
        pad = max(self.x_pad, (maxx - minx) * 0.01, 1.0)
        y = float(self.ys[i])
        line = LineString([(minx - pad, y), (maxx + pad, y)])
        out: list[Interval] = []
        for (ax, _ay), (bx, _by) in G.segments_of(self._reference_geom.intersection(line)):
            out.append((min(ax, bx), max(ax, bx)))
        out.sort()
        return out

    # ------------------------------------------------------------------
    # construction helpers
    # ------------------------------------------------------------------
    @staticmethod
    def scanline_grid(y_min: float, y_max: float, width: float) -> np.ndarray:
        """Swath centre lines tiling ``[y_min, y_max]`` with spacing *width*.

        ``n = ceil(height / width)`` lines are placed at the centre of ``n``
        equal strips.  Centring matters: it keeps the first and last strip from
        being half-width, which is what makes coverage uniform at the boundary.
        """
        if width <= 0:
            raise ValueError("width must be positive")
        height = y_max - y_min
        if height <= 0:
            return np.empty(0, dtype=float)
        n = int(np.ceil(height / width))
        step = height / n
        return y_min + step * (np.arange(n) + 0.5)

    @classmethod
    def from_geometry(
        cls, region: BaseGeometry, width: float, margin: float = 0.0
    ) -> "ScanlineClipper":
        """Build a clipper whose scanlines tile *region* with spacing *width*.

        *margin* shrinks the region before gridding, which is how the headland
        is excluded from the swath pattern.
        """
        region = G.normalise(region)
        inner = G.erode(region, margin) if margin > 0 else region
        basis = inner if not inner.is_empty else region
        minx, miny, maxx, maxy = G.bounds_of(basis)
        ys = cls.scanline_grid(miny, maxy, width)
        clipper = cls(ys, x_pad=max(1.0, (maxx - minx) * 0.01))
        clipper.set_reference(basis)
        if not basis.is_empty:
            clipper.add_geometry(basis)
        return clipper


def check_rings(geom: BaseGeometry) -> list[str]:
    """Report ring-set pathologies that would break the even-odd rule.

    Returns human-readable warnings; an empty list means the fast parity path is
    exact.  Intended for real field polygons, which are often messy.

    Two conditions are checked, and together they are sufficient:

    * **No two rings may cross or touch.**  Partial overlap between a field and
      an obstacle (or between two obstacles) makes the parity region differ from
      the intended region.
    * **Nesting depth must not exceed 2.**  Parity reads a point as "inside"
      when it is covered an odd number of times, so depth 1 is field and depth 2
      is obstacle -- both correct -- but a polygon nested inside an obstacle
      would reach depth 3 and be read back as drivable.

    Proper nesting (an obstacle strictly inside the field) is *correct* and is
    deliberately not reported.

    Note the deliberate absence of ``normalise()``: that runs ``make_valid``,
    which repairs overlapping shells into their union and would hide the very
    defect this function exists to detect.
    """
    warnings: list[str] = []
    raw = list(_iter_raw_polygons(geom))
    if not raw:
        return ["region is empty"]

    for k, p in enumerate(raw):
        if not p.is_valid:
            warnings.append(f"polygon {k} is invalid (repairing it would change coverage)")

    for i in range(len(raw)):
        for j in range(i + 1, len(raw)):
            a, b = raw[i], raw[j]
            if a.exterior.intersects(b.exterior):
                kind = "overlap" if a.intersection(b).area > 0.0 else "touch"
                warnings.append(
                    f"rings {i} and {j} {kind}; even-odd parity would cancel or double-count"
                )

    depths = [1 + sum(1 for j, b in enumerate(raw) if j != i and b.contains(raw[i]))
              for i in range(len(raw))]
    if depths and max(depths) > 2:
        offenders = [i for i, d in enumerate(depths) if d > 2]
        warnings.append(
            f"nesting depth exceeds 2 at polygons {offenders}; parity would read a "
            "polygon inside an obstacle as drivable"
        )
    return warnings


def _iter_raw_polygons(geom: BaseGeometry):
    """Yield polygons from *geom* without validating or repairing it."""
    if geom is None or geom.is_empty:
        return
    if isinstance(geom, Polygon):
        yield geom
    elif hasattr(geom, "geoms"):
        for part in geom.geoms:
            yield from _iter_raw_polygons(part)
