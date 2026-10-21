"""Verify the closed-form Dubins solver against an independent numerical search.

The closed forms are only trustworthy if (a) every returned path actually
reaches the requested pose, and (b) no other feasible path is shorter.  (a) is
checkable directly by re-integrating the segments.  (b) needs an independent
optimiser, so each word is also solved by Nelder-Mead from many seeds and the
best numerical length is compared against the closed-form optimum: the closed
form must be *no longer* than anything the search finds.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
from scipy.optimize import minimize

from cppclip.turns import Segment, TurnPath, dubins_length, dubins_path, dubins_solutions

WORDS = ("LSL", "RSR", "LSR", "RSL", "RLR", "LRL")


def endpoint(word, lengths, q0, radius):
    x, y, t = q0
    for ch, ln in zip(word, lengths):
        x, y, t = Segment(ch, ln).endpoint(x, y, t, radius)
    return x, y, t


def pose_error(word, lengths, q0, q1):
    x, y, t = endpoint(word, lengths, q0, radius=1.0)
    dth = (t - q1[2] + math.pi) % (2 * math.pi) - math.pi
    return math.hypot(x - q1[0], y - q1[1]) + abs(dth)


def numerical_best(q0, q1, radius, seeds=12):
    """Best feasible length any word reaches, found by unconstrained search."""
    best = math.inf
    q1n = ((q1[0] - q0[0]), (q1[1] - q0[1]), q1[2] - q0[2])
    # work in the normalised frame (q0 at origin, heading 0), radius 1
    c, s = math.cos(-q0[2]), math.sin(-q0[2])
    x, y = q1n[0] * c - q1n[1] * s, q1n[0] * s + q1n[1] * c
    target = (x / radius, y / radius, q1n[2])
    origin = (0.0, 0.0, 0.0)

    rng = np.random.default_rng(0)
    for word in WORDS:
        for k in range(seeds):
            seed = rng.uniform(0.0, 2 * math.pi, size=3) if k else np.array([1.0, 1.0, 1.0])
            res = minimize(
                lambda z: pose_error(word, z, origin, target),
                seed,
                method="Nelder-Mead",
                options={"xatol": 1e-10, "fatol": 1e-12, "maxiter": 4000, "maxfev": 8000},
            )
            if res.fun < 1e-7:
                lengths = np.abs(res.x)
                if pose_error(word, lengths, origin, target) < 1e-6:
                    best = min(best, float(lengths.sum()) * radius)
    return best


def main() -> None:
    rng = np.random.default_rng(7)
    n = 60
    worst_arrival = 0.0
    worst_symmetry = 0.0
    worse_than_search = 0
    suboptimal_words = 0

    for k in range(n):
        radius = float(rng.uniform(0.5, 12.0))
        q0 = (float(rng.uniform(-50, 50)), float(rng.uniform(-50, 50)), float(rng.uniform(-math.pi, math.pi)))
        q1 = (float(rng.uniform(-50, 50)), float(rng.uniform(-50, 50)), float(rng.uniform(-math.pi, math.pi)))

        path = dubins_path(q0, q1, radius)
        ex, ey, et = path.endpoint()
        err = max(abs(ex - q1[0]), abs(ey - q1[1]),
                  abs((et - q1[2] + math.pi) % (2 * math.pi) - math.pi))
        worst_arrival = max(worst_arrival, err)

        L = dubins_length(q0, q1, radius)
        # Reversal symmetry, stated correctly.  Reversing a Dubins path turns
        # every L arc into an R arc and flips each heading by pi, so the
        # invariant is L(a, b) == L(flip(b), flip(a)) -- NOT L(a, b) == L(b, a),
        # which is false because the two poses' headings are fixed.  A test
        # asserting the wrong one sends you hunting a bug that is not there.
        flip = lambda q: (q[0], q[1], (q[2] + math.pi + math.pi) % (2 * math.pi) - math.pi)
        Lr = dubins_length(flip(q1), flip(q0), radius)
        worst_symmetry = max(worst_symmetry, abs(L - Lr))

        sols = dubins_solutions(q0, q1, radius)
        for s in sols[1:]:
            if s.length < sols[0].length - 1e-9:
                suboptimal_words += 1

        if k < 12:
            num = numerical_best(q0, q1, radius, seeds=8)
            if num < L - 1e-6:
                worse_than_search += 1
                print(f"  CLOSED FORM WORSE: {L:.6f} vs search {num:.6f}  q0={q0} q1={q1} r={radius:.3f}")

    print(f"random pairs                : {n}")
    print(f"max arrival error           : {worst_arrival:.3e} m")
    print(f"max |L(a,b) - L(flip b, flip a)|       : {worst_symmetry:.3e} m")
    print(f"returned path beaten by another returned word: {suboptimal_words}")
    print(f"cases where numerical search found shorter   : {worse_than_search}")

    print("\n--- named cases ---")
    cases = [
        ("straight, aligned", (0, 0, 0), (7, 0, 0), 0.5),
        ("90 deg min radius", (0, 0, 0), (0, 1, math.pi / 2), 1.0),
        ("U-turn in place", (0, 0, 0), (0, 0, math.pi), 1.0),
        ("90 deg, r=6", (0, 0, 0), (0, 6, math.pi / 2), 6.0),
        ("lateral 2r", (0, 0, 0), (0, 2, 0), 1.0),
        ("tight side-step", (0, 0, 0), (0.5, 0.5, 0.3), 3.0),
    ]
    for name, a, b, r in cases:
        p = dubins_path(a, b, r)
        print(f"  {name:22} L={p.length:9.5f}  word={p.word:4}  "
              f"backwards={p.backwards:.3f}  reaches={max(abs(p.endpoint()[0]-b[0]), abs(p.endpoint()[1]-b[1])):.2e}")


if __name__ == "__main__":
    main()
