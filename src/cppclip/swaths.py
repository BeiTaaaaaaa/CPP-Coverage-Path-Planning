"""Coverage strokes derived from clipped scanline intervals.

A *swath* (条带) is one straight working stroke: the machine drives from
``(x0, y)`` to ``(x1, y)`` with its implement down.  The set of swaths is
exactly the set of effective intervals produced by :mod:`cppclip.sweep`, so
concavity and in-field obstacles are already resolved at this stage -- there is
no cell decomposition anywhere in this module.

Everything here works in a **rotated frame** where the swath direction is the
``x`` axis.  :class:`Frame` owns that rotation so the planner can pick a
heading freely and rotate the finished path back at the end.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np
from shapely import affinity
from shapely.geometry.base import BaseGeometry

from . import geometry as G
from .sweep import ScanlineClipper

__all__ = [
    "Swath",
    "Stroke",
    "Frame",
    "swaths_from_intervals",
    "swaths_from_clipper",

    "total_length",
    "candidate_angles",
    "choose_heading",
]

Point2D = tuple[float, float]


@dataclass(slots=True)
class Swath:
    """One straight working stroke, axis-aligned in its :class:`Frame`."""

    scanline: int
    y: float
    x0: float
    x1: float

    @property
    def length(self) -> float:
        return self.x1 - self.x0

    @property
    def midpoint(self) -> Point2D:
        return (0.5 * (self.x0 + self.x1), self.y)

    def endpoints(self) -> tuple[Point2D, Point2D]:
        """``(left, right)`` endpoints; a stroke may be driven either way."""
        return ((self.x0, self.y), (self.x1, self.y))

    def point(self, reversed_: bool) -> tuple[Point2D, Point2D]:
        """``(entry, exit)`` for the chosen travel direction."""
        left, right = self.endpoints()
        return (right, left) if reversed_ else (left, right)

    def sample(self, n: int | None = None) -> list[Point2D]:
        """Points along the stroke, for swept-area metrics."""
        if n is None:
            n = max(2, int(np.ceil(self.length)) + 1)
        xs = np.linspace(self.x0, self.x1, n)
        return [(float(x), self.y) for x in xs]


@dataclass(slots=True)
class Stroke:
    """A working stroke expressed in **world** coordinates.

    :class:`Swath` is axis-aligned and lives in the planning frame; a ``Stroke``
    is what the machine actually drives, so it is what metrics, plots and
    obstacle-clearance checks consume.
    """

    p0: Point2D
    p1: Point2D
    scanline: int = 0

    @property
    def length(self) -> float:
        return float(np.hypot(self.p1[0] - self.p0[0], self.p1[1] - self.p0[1]))

    @property
    def midpoint(self) -> Point2D:
        return (0.5 * (self.p0[0] + self.p1[0]), 0.5 * (self.p0[1] + self.p1[1]))

    def as_line(self):
        from shapely.geometry import LineString

        return LineString([self.p0, self.p1])


class Frame:
    """A rigid rotation of the plane, used to align swaths with the x axis.

    The planner rotates the *scene* by ``-angle``, plans axis-aligned, then
    rotates the resulting path by ``+angle``.  Both directions must use the
    **same pivot**, otherwise the round trip does not return the path to where
    it started; the pivot is therefore captured once, at construction, and never
    re-derived from whatever geometry is being transformed.
    """

    __slots__ = ("angle", "pivot", "_cos", "_sin")

    def __init__(self, angle: float = 0.0, pivot: Point2D = (0.0, 0.0)) -> None:
        self.angle = float(angle)
        self.pivot = (float(pivot[0]), float(pivot[1]))
        self._cos = float(np.cos(self.angle))
        self._sin = float(np.sin(self.angle))

    @classmethod
    def around(cls, geom: BaseGeometry, angle: float) -> "Frame":
        """Build a frame whose pivot is the centroid of *geom*."""
        if geom is None or geom.is_empty:
            return cls(angle, (0.0, 0.0))
        c = geom.centroid
        return cls(angle, (c.x, c.y))

    def to_local(self, geom: BaseGeometry) -> BaseGeometry:
        """Rotate a geometry into the swath frame."""
        if self.angle == 0.0:
            return geom
        return affinity.rotate(geom, -np.degrees(self.angle), origin=self.pivot)

    def to_world(self, geom: BaseGeometry) -> BaseGeometry:
        """Rotate a geometry back out of the swath frame."""
        if self.angle == 0.0:
            return geom
        return affinity.rotate(geom, np.degrees(self.angle), origin=self.pivot)

    def _rotate_point(self, p: Point2D, sign: float) -> Point2D:
        if self.angle == 0.0:
            return (float(p[0]), float(p[1]))
        x, y = p[0] - self.pivot[0], p[1] - self.pivot[1]
        c, s = self._cos, sign * self._sin
        return (self.pivot[0] + x * c - y * s, self.pivot[1] + x * s + y * c)

    def point_to_local(self, p: Point2D) -> Point2D:
        return self._rotate_point(p, -1.0)

    def point_to_world(self, p: Point2D) -> Point2D:
        return self._rotate_point(p, 1.0)

    def points_to_world(self, pts: Iterable[Point2D]) -> list[Point2D]:
        return [self.point_to_world(p) for p in pts]

    def points_to_local(self, pts: Iterable[Point2D]) -> list[Point2D]:
        return [self.point_to_local(p) for p in pts]

    def swaths_to_strokes(self, swaths: Iterable[Swath]) -> list[Stroke]:
        """Rotate planned swaths into world-coordinate strokes."""
        return [
            Stroke(
                p0=self.point_to_world((s.x0, s.y)),
                p1=self.point_to_world((s.x1, s.y)),
                scanline=s.scanline,
            )
            for s in swaths
        ]


# --------------------------------------------------------------------------
# interval -> swath
# --------------------------------------------------------------------------
def swaths_from_intervals(
    intervals: Sequence[Sequence[tuple[float, float]]],
    ys: Sequence[float],
    min_length: float = 0.0,
    scanline_offset: int = 0,
) -> list[Swath]:
    """Convert per-scanline effective intervals into swaths.

    *min_length* drops strokes too short to be worth a turn.  This is the only
    place a stroke can be discarded, and it is deliberate: a 0.2 m interval
    between two obstacles costs a full headland turn to mow.

    *scanline_offset* is the grid index of ``intervals[0]``.  Pass it whenever
    the caller supplies a **subset** of the grid: :attr:`Swath.scanline` is part
    of a swath's identity, and two swaths on different lines that happen to share
    an x range are otherwise indistinguishable.  Passing a single line without
    the offset silently numbers every swath line 0, which makes those two swaths
    compare equal -- and the incremental planner keys its stroke bookkeeping on
    exactly that comparison.
    """
    out: list[Swath] = []
    for i, line in enumerate(intervals):
        y = float(ys[i])
        for x0, x1 in line:
            if x1 - x0 <= min_length:
                continue
            out.append(
                Swath(scanline=i + scanline_offset, y=y, x0=float(x0), x1=float(x1))
            )
    return out


def swaths_from_clipper(clip: ScanlineClipper, min_length: float = 0.0) -> list[Swath]:
    """All swaths implied by a clipper's scanline grid."""
    return swaths_from_intervals(clip.all_intervals(), clip.ys, min_length=min_length)


def total_length(swaths: Iterable[Swath]) -> float:
    return float(sum(s.length for s in swaths))


# --------------------------------------------------------------------------
# swath heading selection
# --------------------------------------------------------------------------
def candidate_angles(n: int = 36, lo: float = 0.0, hi: float = np.pi) -> np.ndarray:
    """``n`` evenly spaced swath headings over ``[lo, hi)``.

    Coverage is symmetric under a 180 degree rotation of the swath direction
    (the same stripes are driven the other way), so a half turn is the full
    search space.
    """
    return np.linspace(lo, hi, n, endpoint=False)


def choose_heading(
    region: BaseGeometry,
    width: float,
    angles: np.ndarray | None = None,
    criterion: str = "segments",
) -> tuple[float, dict]:
    """Pick the swath heading that minimises the number of strokes.

    Fewer strokes means fewer turns, and turn cost dominates non-working
    distance in arable fields, so stroke count is a much better proxy than the
    often-quoted "minimise field width".  Returns ``(best_angle, report)``
    where *report* records every candidate's score, which is what makes the
    choice auditable in the experiment log.
    """
    region = G.normalise(region)
    if region.is_empty:
        return 0.0, {"candidates": []}
    if angles is None:
        angles = candidate_angles()

    records = []
    for a in angles:
        frame = Frame(float(a))
        local = frame.to_local(region)
        clip = ScanlineClipper.from_geometry(local, width)
        intervals = clip.all_intervals()
        n_segments = sum(len(line) for line in intervals)
        working = sum(b - a2 for line in intervals for a2, b in line)
        records.append(
            {
                "angle_rad": float(a),
                "angle_deg": float(np.degrees(a)),
                "n_scanlines": int(clip.n_scanlines),
                "n_segments": int(n_segments),
                "working_length": float(working),
            }
        )

    if criterion == "segments":
        key = lambda r: (r["n_segments"], r["n_scanlines"])  # noqa: E731
    elif criterion == "working_length":
        key = lambda r: (r["working_length"], r["n_segments"])  # noqa: E731
    else:
        raise ValueError(f"unknown criterion: {criterion!r}")

    best = min(records, key=key)
    return best["angle_rad"], {"candidates": records, "best": best}
