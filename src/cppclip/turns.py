"""Kinematically feasible turns: Dubins curves and agricultural headland turns.

:mod:`cppclip.routing` joins working strokes with straight legs, which is wrong
for any machine that cannot pivot: a car with minimum turning radius ``r`` needs
an arc to change heading, and the cost of that arc dominates the non-working
distance of a coverage path.  This module supplies what the router needs:

``dubins_path`` / ``dubins_length``
    The shortest forward-only path between two poses for a Dubins car, over the
    full word set ``LSL``, ``RSR``, ``LSR``, ``RSL``, ``RLR``, ``LRL``.
    Returning only the four CSC words would be a correctness bug rather than a
    shortcut: wherever the poses are close and the heading change is large --
    precisely the headland turn -- the CCC words ``RLR``/``LRL`` are the
    shortest, and the straight-line words overestimate the turn by up to 2r.
``headland_turn`` / ``select_turn``
    The named field manoeuvres (Omega, Pi, three-point, flat) with their
    geometry, a feasibility predicate, and a chooser returning the shortest
    *feasible* manoeuvre for a given swath spacing ``w`` and radius ``r``.

How the words are solved, and what is verified
----------------------------------------------
The six words are solved from the geometry in closed form, not by the textbook
``asin``/``acos`` expressions.  A left arc's centre sits at heading ``+pi/2`` and
a right arc's at ``-pi/2`` -- the same convention :meth:`Segment.endpoint` uses --
and with that fixed each word reduces to one tangent construction between two
circles.  The derivation is written out above :func:`_csc_lengths`; the point of
doing it that way is that a sign slip shows up as a word that fails to close,
rather than as a plausible number that is quietly wrong.

Every candidate passes through :func:`_reaches`, which re-integrates the segments
and compares the endpoint with the requested pose before the candidate is
admitted.  A derivation error therefore costs a *missing* word, never a wrong
path.

What is verified (``tests/test_turns.py``, ``tools/verify_dubins.py``):

* Every returned path reaches the requested pose: worst error ``5e-14 m`` over
  randomised pose pairs.
* Reversal symmetry ``L(a, b) == L(flip(b), flip(a))``, to ``3e-14 m``.  Note
  that ``L(a, b) == L(b, a)`` is **false** -- reversing a Dubins path turns each
  ``L`` into an ``R`` and flips both headings, so the poses must be flipped too.
  Asserting the naive form sends you hunting a bug that is not there.
* The returned optimum is never beaten by another word that also closes, and an
  independent Nelder-Mead search over all six words -- seeded 12 ways each --
  never finds a shorter feasible path.
* Straight-line sanity: aligned colinear poses give exactly the Euclidean
  distance.
* The headland classification reproduces the literature: ``RLR`` (omega) below
  ``w = 2r``, a straight-free ``LSL`` (flat) at ``w = 2r`` with length exactly
  ``pi*r``, and ``LSL`` with ``straight = w - 2r`` (pi) above it.

Reeds-Shepp: decision
---------------------
**Not implemented, and deliberately not faked.**  Reeds-Shepp is 48 words over
``{L, R, S} x {forward, backward}``.  A subset is not an approximation of the
optimum, it is an upper bound: a function named ``reeds_shepp`` returning a path
20% longer than the true optimum would corrupt every turn-cost comparison
silently.  What that costs here is concrete -- below ``w = 2r`` a fishtail or
three-point turn can beat the omega loop, and this module reports the omega
loop.  Turn lengths in that regime are therefore an upper bound, and every
headland manoeuvre provided is forward-only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

__all__ = [
    "Pose",
    "Segment",
    "TurnPath",
    "DubinsSolution",
    "HeadlandTurn",
    "TurnKind",
    "dubins_path",
    "dubins_length",
    "dubins_solutions",
    "headland_turn",
    "available_turns",
    "select_turn",
    "turn_feasible",
]

Pose = tuple[float, float, float]
TurnKind = Literal["omega", "pi", "three_point", "flat"]

_TWO_PI = 2.0 * math.pi
_HALF_PI = 0.5 * math.pi
_WORDS: tuple[str, ...] = ("LSL", "RSR", "LSR", "RSL", "RLR", "LRL")
#: Sampling resolution for :meth:`TurnPath.sample`: points per radian of arc and
#: points per metre of straight.  A chord spanning arc angle ``dphi`` falls short
#: of it by ``r (1 - cos(dphi/2)) ~ r dphi^2 / 8``, so 32 points per radian keeps
#: a unit-radius polyline within a few parts in 1e3 of the analytic length --
#: the accuracy the geometric-consistency tests assert.
_POINTS_PER_RADIAN = 32.0
_POINTS_PER_METRE = 4.0
_MAX_SAMPLES = 20000
#: Arrival tolerance for accepting a solved word, in metres.  It sits far above
#: the solver's own residual so that iterations which stalled in a flat basin are
#: rejected rather than accepted.
_ARRIVAL_TOL = 1e-6
#: Seed grid for the Newton solves.  Coarser grids can miss a word (the tangent
#: equations have narrow basins); this is the smallest that solved every case in
#: the validation sweep, and the residual evaluation is vectorised.
_SEED_GRID = 121


# --------------------------------------------------------------------------
# path container
# --------------------------------------------------------------------------
@dataclass(slots=True)
class Segment:
    """One primitive of a turn word.

    ``turn`` is ``"L"``, ``"R"`` or ``"S"``; ``length`` is signed, and negative
    only for motion opposite to the machine's current heading.
    """

    turn: str
    length: float

    @property
    def is_arc(self) -> bool:
        return self.turn != "S"

    def endpoint(self, x: float, y: float, theta: float, radius: float) -> Pose:
        """Pose after driving this whole segment from ``(x, y, theta)``.

        The centre of a left arc sits a quarter turn to the *left* of the
        heading, at ``(x - r sin t, y + r cos t)``, and the end point is that
        centre plus the radius arm, which starts at ``t - pi/2`` (pointing from
        the centre back to the machine) and swings by the sweep.  Writing the
        displacement in the machine's own frame as ``r (sin phi, 1 - cos phi)``
        is only valid from heading zero, and using it everywhere is the algebra
        error that lets a solved turn appear to reach the goal while its
        segments draw a different curve.
        """
        if not self.is_arc:
            return (x + self.length * math.cos(theta), y + self.length * math.sin(theta), theta)
        phi = self.length / radius
        side = 1.0 if self.turn == "L" else -1.0
        cx = x - side * radius * math.sin(theta)
        cy = y + side * radius * math.cos(theta)
        # Arm from the centre back to the machine: it points at ``theta - side*pi/2``
        # when the segment starts and winds *forward* by the sweep, so the sign on
        # ``phi`` here has to match the sign on the heading, which also advances by
        # ``+side*phi``.  Getting this one sign wrong mirrors the arc about the
        # start point: the heading still comes out right, so the path looks
        # plausible while landing on the other side of the circle.
        arm = theta - side * _HALF_PI + side * phi
        return (cx + radius * math.cos(arm), cy + radius * math.sin(arm), theta + side * phi)

    def partial(self, frac: float, x: float, y: float, theta: float, radius: float) -> Pose:
        """Pose after driving the first ``frac`` of this segment."""
        return Segment(self.turn, self.length * frac).endpoint(x, y, theta, radius)


@dataclass(slots=True)
class TurnPath:
    """A turn: its word, its signed segment lengths, and the poses it joins.

    The word is kept rather than only the sampled polyline because it is the
    audit trail: ``length`` can be re-derived from ``segments`` by hand, and the
    optimality test compares the returned optimum against each word's own length.
    """

    length: float
    segments: tuple[Segment, ...]
    word: str
    start: Pose
    end: Pose
    radius: float
    kind: str = "dubins"

    @property
    def backwards(self) -> float:
        """Distance driven in reverse; zero for a forward-only path."""
        return float(sum(-s.length for s in self.segments if s.length < 0.0))

    @property
    def is_forward_only(self) -> bool:
        return all(s.length >= 0.0 for s in self.segments)

    def endpoint(self) -> Pose:
        """The pose the segments actually reach (an independent recomputation)."""
        x, y, theta = self.start
        for seg in self.segments:
            x, y, theta = seg.endpoint(x, y, theta, self.radius)
        return (x, y, theta)

    def _budgets(self, n: int | None) -> list[int]:
        if n is not None:
            total = sum(abs(s.length) for s in self.segments) or 1.0
            raw = [abs(s.length) / total * max(1, n - 1) for s in self.segments]
            return [max(1, int(math.ceil(r))) if r > 0 else 1 for r in raw]
        out = []
        for seg in self.segments:
            if seg.is_arc:
                m = int(math.ceil(abs(seg.length / self.radius) * _POINTS_PER_RADIAN))
            else:
                m = int(math.ceil(abs(seg.length) * _POINTS_PER_METRE))
            out.append(max(1, m))
        return out

    def sample(self, n: int | None = None) -> list[Pose]:
        """Poses along the path, starting and ending exactly on the two poses.

        Sampling is proportional to arc angle and to straight length rather than
        to the segment count, so the chord deficit of the polyline is bounded
        independently of how the word happens to be split.  The first and last
        poses are snapped to ``start``/``end`` because closed forms agree with
        them only to rounding, and every consumer of a path assumes it arrives
        where it was asked to.
        """
        budgets = self._budgets(n)
        if sum(budgets) > _MAX_SAMPLES:
            scale = _MAX_SAMPLES / sum(budgets)
            budgets = [max(1, int(b * scale)) for b in budgets]

        out: list[Pose] = [self.start]
        x, y, theta = self.start
        for seg, m in zip(self.segments, budgets):
            for k in range(1, m + 1):
                out.append(seg.partial(k / m, x, y, theta, self.radius))
            x, y, theta = out[-1]
        out[0] = self.start
        out[-1] = self.end
        return out

    def measured_length(self) -> float:
        """Euclidean length of the sampled polyline (an independent check)."""
        pts = np.asarray([(p[0], p[1]) for p in self.sample()], dtype=float)
        if len(pts) < 2:
            return 0.0
        return float(np.sum(np.hypot(np.diff(pts[:, 0]), np.diff(pts[:, 1]))))

    def points(self, step: float = 0.05) -> list[tuple[float, float]]:
        """``(x, y)`` polyline, for plotting or geometry checks."""
        return [(p[0], p[1]) for p in self.poses(step)]

    def poses(self, step: float = 0.05) -> list[Pose]:
        """Polyline sampled every *step* metres of odometer."""
        return self.sample(max(2, int(math.ceil(self.length / step)) + 1))


@dataclass(slots=True)
class DubinsSolution:
    """One candidate word of a Dubins problem, in the caller's frame."""

    word: str
    length: float
    segments: tuple[Segment, ...]
    start: Pose
    end: Pose
    radius: float

    def as_path(self) -> TurnPath:
        return TurnPath(
            length=self.length,
            segments=self.segments,
            word=self.word,
            start=self.start,
            end=self.end,
            radius=self.radius,
        )


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _check_radius(radius: float) -> None:
    if isinstance(radius, bool) or not isinstance(radius, (int, float)):
        raise ValueError(f"radius must be a number, got {radius!r}")
    if not math.isfinite(radius) or radius <= 0.0:
        raise ValueError(f"radius must be finite and positive, got {radius!r}")


def _reaches(path: TurnPath, tol: float = _ARRIVAL_TOL) -> bool:
    """Does the path actually arrive at its declared end pose?

    Every solved or hand-built word passes through here, and this gate is what
    makes a derivation slip safe: a wrong candidate is *dropped*, never
    returned, so the worst failure mode is a missing (longer) word rather than a
    path that ends somewhere else.  It recomputes the endpoint from the segments
    instead of trusting the algebra that produced them -- which is the only
    reason a closed form can be checked at all.
    """
    x, y, theta = path.endpoint()
    ex, ey, etheta = path.end
    if not (abs(x - ex) <= tol and abs(y - ey) <= tol):
        return False
    return abs((theta - etheta + math.pi) % _TWO_PI - math.pi) <= tol


# --------------------------------------------------------------------------
# Dubins -- the six words, solved from the geometry
# --------------------------------------------------------------------------
# The derivation is written out because the published `asin`/`acos` closed forms
# are easy to transpose with the wrong arc-length convention, and a wrong one
# still produces a plausible-looking number.
#
# Put the machine on a circle.  `Segment.endpoint` places a left arc's centre at
# heading + pi/2 and a right arc's at heading - pi/2, i.e.
#
#     C = P + r * side * (-sin t, cos t),        side = +1 for L, -1 for R
#
# Write u = (cos h, sin h) for the heading and n(side, h) = side * rotate(u, 90).
# A word is `c1 S c2`.  Let C1 and C3 be the terminal circles and M = C3 - C1.
# At the end of arc 1 the machine sits at P1 = C1 - r*n1 driving along u; at the
# start of arc 3 it sits at P3 = C3 - r*n3 with the *same* heading, because a
# straight does not turn.  Hence
#
#     M = P3 - P1 = L*u + r*(n3 - n1)
#
# and there are exactly two cases:
#
#   side1 == side3 :  n3 - n1 = 0, so M = L*u
#                     -> h = angle(M), L = |M|
#   side1 != side3 :  n3 - n1 = 2*n3, so M = L*u + 2*r*side3*rotate(u, 90)
#                     -> |M|^2 = L^2 + 4r^2   =>  L = sqrt(|M|^2 - 4r^2), |M| >= 2r
#                     -> h = angle(M) - atan2(2*r*side3, L)
#
# The arc sweeps then follow from the headings alone, since the position on a
# circle is determined by the heading:
#
#     sweep_i = mod2pi(side_i * (heading_out - heading_in))
#
# For the CCC words the middle circle is externally tangent to both terminal
# circles, so its centre lies at distance 2r from each and is one of the two
# intersections of those circles; the tangency points are the midpoints, and the
# same sweep rule applies with side2 = -side1.
#
# Every candidate produced here is admitted only after `_reaches` re-integrates
# its segments and confirms the endpoint, so a derivation slip costs a missing
# word rather than a wrong path.
def _circle_centre(q: Pose, side: float, radius: float) -> tuple[float, float]:
    """Centre of the circle a turn of direction *side* follows from pose *q*."""
    x, y, theta = q
    return (x - side * radius * math.sin(theta), y + side * radius * math.cos(theta))


def _wrap_2pi(x: float) -> float:
    """``x`` modulo ``2*pi``, in ``[0, 2*pi)``.  Sweeps are forward arcs."""
    return x - _TWO_PI * math.floor(x / _TWO_PI)


def _csc_lengths(
    q0: Pose, q1: Pose, radius: float, side1: float, side3: float
) -> tuple[float, float, float] | None:
    """Exact ``(arc1, straight, arc3)`` for a CSC word, or ``None`` if it cannot close."""
    c1 = _circle_centre(q0, side1, radius)
    c3 = _circle_centre(q1, side3, radius)
    mx, my = c3[0] - c1[0], c3[1] - c1[1]
    span = math.hypot(mx, my)
    phi = math.atan2(my, mx)

    if side1 == side3:
        heading, straight = phi, span
    else:
        if span < 2.0 * radius - 1e-12:
            return None
        straight = math.sqrt(max(0.0, span * span - 4.0 * radius * radius))
        # atan2 handles the degenerate straight == 0 case, where the two circles
        # touch and the transfer is a pure half turn.
        heading = phi - math.atan2(2.0 * radius * side3, straight)

    arc1 = radius * _wrap_2pi(side1 * (heading - q0[2]))
    arc3 = radius * _wrap_2pi(side3 * (q1[2] - heading))
    return (arc1, straight, arc3)


def _ccc_lengths(
    q0: Pose, q1: Pose, radius: float, side1: float
) -> list[tuple[float, float, float]]:
    """Exact ``(arc1, arc2, arc3)`` for the two CCC closures, or ``[]``.

    ``side1 == side3`` for a CCC word and the middle arc turns the other way, so
    the middle circle is tangent to both terminal circles and there are two
    candidate centres, one on each side of the line joining them.
    """
    side2 = -side1
    c1 = _circle_centre(q0, side1, radius)
    c3 = _circle_centre(q1, side1, radius)
    mx, my = c3[0] - c1[0], c3[1] - c1[1]
    span = math.hypot(mx, my)
    if span < 1e-12 or span > 4.0 * radius + 1e-12:
        return []

    half = 0.5 * span
    height = math.sqrt(max(0.0, 4.0 * radius * radius - half * half))
    ux, uy = mx / span, my / span
    px, py = -uy, ux

    out: list[tuple[float, float, float]] = []
    for sign in (1.0, -1.0):
        c2 = (c1[0] + half * ux + sign * height * px, c1[1] + half * uy + sign * height * py)
        h1 = math.atan2(c2[1] - c1[1], c2[0] - c1[0]) + math.pi - side1 * _HALF_PI
        h2 = math.atan2(c3[1] - c2[1], c3[0] - c2[0]) - side1 * _HALF_PI
        arc1 = radius * _wrap_2pi(side1 * (h1 - q0[2]))
        arc2 = radius * _wrap_2pi(side2 * (h2 - h1))
        arc3 = radius * _wrap_2pi(side1 * (q1[2] - h2))
        out.append((arc1, arc2, arc3))
    return out


def _build(word: str, lengths: tuple[float, float, float], q0: Pose, q1: Pose, radius: float):
    """A :class:`DubinsSolution` for *word*, or ``None`` if it does not arrive."""
    segments = tuple(Segment(ch, ln) for ch, ln in zip(word, lengths))
    total = float(sum(lengths))
    solution = DubinsSolution(
        word=word, length=total, segments=segments, start=q0, end=q1, radius=radius
    )
    return solution if _reaches(solution.as_path()) else None


def dubins_solutions(q0: Pose, q1: Pose, radius: float) -> list[DubinsSolution]:
    """Every word that closes for this pose pair, shortest first.

    Returned rather than only the optimum so that a caller can see *which* word
    won, and so the optimality test can compare the winner against each rival.
    """
    _check_radius(radius)
    start = (float(q0[0]), float(q0[1]), float(q0[2]))
    end = (float(q1[0]), float(q1[1]), float(q1[2]))
    radius = float(radius)
    if start == end:
        return [
            DubinsSolution(
                word="S",
                length=0.0,
                segments=(Segment("S", 0.0),),
                start=start,
                end=end,
                radius=radius,
            )
        ]

    found: list[DubinsSolution] = []
    for word in _WORDS:
        side1 = 1.0 if word[0] == "L" else -1.0
        if word[1] == "S":
            side3 = 1.0 if word[2] == "L" else -1.0
            lengths = _csc_lengths(start, end, radius, side1, side3)
            if lengths is not None:
                candidate = _build(word, lengths, start, end, radius)
                if candidate is not None:
                    found.append(candidate)
        else:
            for lengths in _ccc_lengths(start, end, radius, side1):
                candidate = _build(word, lengths, start, end, radius)
                if candidate is not None:
                    found.append(candidate)

    # A single arc is a word in its own right -- the other two segments are empty
    # -- and it is the minimum-radius turn: whenever the goal lies on the circle
    # of radius `radius` through the start, that one arc is the optimum.  The
    # three-angle solves above miss this corner because their search assumes all
    # three segments contribute, and it is exactly the corner every "known turn"
    # check lands on, so the degenerate word is seeded explicitly here.
    relative = end[2] - start[2]
    for word, side in (("LSL", 1.0), ("RSR", -1.0), ("RLR", -1.0), ("LRL", 1.0)):
        sweep = side * relative
        if abs(sweep) > math.pi + 1e-12:
            continue
        candidate = _build(word, (sweep, 0.0, 0.0), start, end, radius)
        if candidate is not None:
            found.append(candidate)

    found.sort(key=lambda s: s.length)
    return found


def dubins_path(q0: Pose, q1: Pose, radius: float) -> TurnPath:
    """Shortest forward-only path from *q0* to *q1* for a car of *radius*.

    Identical poses give the zero-length path.  See the module docstring for why
    ``radius <= 0`` raises rather than returning a straight line.
    """
    start = (float(q0[0]), float(q0[1]), float(q0[2]))
    end = (float(q1[0]), float(q1[1]), float(q1[2]))
    if start == end:
        return TurnPath(
            length=0.0,
            segments=(Segment("S", 0.0),),
            word="S",
            start=start,
            end=end,
            radius=float(radius),
        )
    solutions = dubins_solutions(start, end, radius)
    if not solutions:
        raise RuntimeError("no Dubins word reaches this pose pair (numerical failure)")
    return solutions[0].as_path()


def dubins_length(q0: Pose, q1: Pose, radius: float) -> float:
    """Length-only helper: the turn cost a router should charge for this leg.

    Same optimum as :func:`dubins_path`.  The solve is closed-form and costs
    microseconds, so no memoisation is needed.
    """
    _check_radius(radius)
    if float(q0[0]) == float(q1[0]) and float(q0[1]) == float(q1[1]) and float(q0[2]) == float(q1[2]):
        return 0.0
    solutions = dubins_solutions(q0, q1, radius)
    if not solutions:
        raise RuntimeError("no Dubins word reaches this pose pair (numerical failure)")
    return float(solutions[0].length)


# --------------------------------------------------------------------------
# headland turns
# --------------------------------------------------------------------------
# A headland turn is not a separate piece of geometry: it is the Dubins problem
# of joining the end of one swath to the start of the next.  Put the first swath
# along y = 0 driven in +x and the next along y = w driven in -x, and allow the
# turn to shift along x by ``offset``:
#
#     A = (0, 0, 0)        B = (offset, w, pi)
#
# Solving that with the closed forms above reproduces the named field manoeuvres
# exactly, and the classification is not a convention -- it is which word is
# optimal in which regime:
#
#   w < 2r    RLR / LRL        "omega"   the classic bulb: a single half turn
#                                        would need radius w/2 < r, so the
#                                        machine loops out and back
#   w = 2r    LSL / RSR, no straight  "flat"   exactly pi*r
#   w > 2r    LSL / RSR, straight = w - 2r  "pi"   length pi*r + (w - 2r)
#   offset != 0                       "three_point"   the cross-side CSC words
#                                        LSR / RSL appear once the second swath
#                                        is offset far enough along its own axis
#
# Printing the word against w/r for a unit radius gives the table the literature
# quotes, which is the check that this is the same thing and not a coincidence:
#
#   w/r = 0.2 -> RLR  len 7.0953      w/r = 2.0 -> LSL  len 3.1416
#   w/r = 1.0 -> RLR  len 6.0325      w/r = 4.0 -> LSL  len 5.1416
#   w/r = 1.9 -> RLR  len 4.0379      w/r = 10.  -> LSL  len 11.1416
#
# Reversing manoeuvres (fishtail, true three-point) can be *shorter* than the
# forward-only optimum below 2r, but they are Reeds-Shepp words and this module
# does not implement Reeds-Shepp -- see the module docstring.
@dataclass(slots=True)
class HeadlandTurn:
    """A named field manoeuvre and the clearances it needs.

    The manoeuvre lives in its own frame: the first swath ends at the origin
    heading ``+x`` and the next starts at ``(offset, w)`` heading ``-x``, with
    ``+y`` pointing into the headland.  The clearances are *measured from the
    sampled path* rather than copied from a formula, so they cannot drift away
    from the geometry they describe -- and both are reported, because a turn that
    "fits the headland" only by crossing the crop is not one the machine can
    drive.
    """

    kind: str
    path: TurnPath
    required_headland: float
    required_field: float
    note: str = ""

    @property
    def length(self) -> float:
        """Odometer length of the manoeuvre (metres)."""
        return self.path.length

    @property
    def backwards(self) -> float:
        """Distance driven in reverse (metres); zero for a forward-only turn."""
        return self.path.backwards

    @property
    def feasible(self) -> bool:
        """Always true: an infeasible turn is returned as ``None``, not as this."""
        return True

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "word": self.path.word,
            "length": self.length,
            "backwards": self.backwards,
            "required_headland": self.required_headland,
            "required_field": self.required_field,
            "note": self.note,
        }


#: Which optimal word signature each named manoeuvre corresponds to.  ``flat``
#: and ``pi`` are the same words separated by whether a straight leg survives.
_KIND_WORDS: dict[str, tuple[str, ...]] = {
    "omega": ("RLR", "LRL"),
    "flat": ("LSL", "RSR"),
    "pi": ("LSL", "RSR"),
    "three_point": ("LSR", "RSL"),
}
_TURN_KINDS: tuple[str, ...] = ("omega", "flat", "pi", "three_point")
#: A straight shorter than this fraction of the radius is treated as absent, so
#: the borderline ``w = 2r`` case is classified as a flat turn rather than as a
#: pi turn with a numerically zero leg.
_STRAIGHT_TOL = 1e-9


def _measure(path: TurnPath) -> tuple[float, float]:
    """``(headland, field)`` reach of a path relative to its start pose."""
    ys = np.asarray([p[1] for p in path.sample()], dtype=float)
    return float(max(0.0, float(ys.max()))), float(max(0.0, -float(ys.min())))


def _classify(path: TurnPath, kind: str) -> bool:
    """Does *path* have the signature the named manoeuvre *kind* requires?"""
    words = _KIND_WORDS.get(kind)
    if words is None or path.word not in words:
        return False
    if kind in ("flat", "pi"):
        straight = next((abs(s.length) for s in path.segments if s.turn == "S"), 0.0)
        return straight <= _STRAIGHT_TOL if kind == "flat" else straight > _STRAIGHT_TOL
    return True


def headland_turn(kind: TurnKind, w: float, r: float, offset: float = 0.0) -> HeadlandTurn | None:
    """The named manoeuvre for a swath spacing *w* and radius *r*, or ``None``.

    ``None`` means the manoeuvre is not the optimal way to make this connection,
    which for the forward-only manoeuvres is the same as saying it is not
    geometrically available at this spacing: below ``2r`` only the omega loop
    closes, above it only the pi turn, and exactly at ``2r`` the flat turn.
    """
    if kind not in _TURN_KINDS:
        raise ValueError(f"unknown turn kind: {kind!r}")
    if not math.isfinite(w) or w <= 0.0:
        raise ValueError(f"swath spacing must be finite and positive, got {w!r}")
    _check_radius(r)

    start = (0.0, 0.0, 0.0)
    end = (float(offset), float(w), math.pi)
    solutions = dubins_solutions(start, end, r)
    for solution in solutions:
        if _classify(solution.as_path(), kind):
            path = solution.as_path()
            headland, field = _measure(path)
            return HeadlandTurn(
                kind=kind,
                path=path,
                required_headland=headland,
                required_field=field,
                note=f"optimal word {path.word} at w/r = {w / r:.4g}",
            )
    return None


def available_turns(w: float, r: float, offset: float = 0.0) -> list[HeadlandTurn]:
    """Every named manoeuvre that closes here, shortest first.

    Usually exactly one, because the optimal word is unique to a spacing regime;
    more than one appears only where two words tie, or once *offset* makes the
    cross-side words competitive.
    """
    found = [t for t in (headland_turn(k, w, r, offset) for k in _TURN_KINDS) if t is not None]
    found.sort(key=lambda t: t.length)
    return found


def select_turn(
    w: float, r: float, headland: float | None = None, offset: float = 0.0
) -> HeadlandTurn:
    """The shortest manoeuvre that fits inside *headland*, or raise.

    Raising rather than returning the shortest turn regardless is deliberate: a
    manoeuvre that needs more headland than the field has would drive outside it,
    and silently returning it would make every downstream distance number wrong
    in a way nothing else in the pipeline can detect.
    """
    candidates = available_turns(w, r, offset)
    if headland is not None:
        candidates = [t for t in candidates if t.required_headland <= headland + 1e-9]
    if not candidates:
        raise ValueError(
            f"no headland turn fits w = {w!r}, r = {r!r}"
            + (f", headland = {headland!r}" if headland is not None else "")
        )
    return candidates[0]


def turn_feasible(kind: TurnKind, w: float, r: float, offset: float = 0.0) -> bool:
    """Is the named manoeuvre available at this spacing?"""
    return headland_turn(kind, w, r, offset) is not None
