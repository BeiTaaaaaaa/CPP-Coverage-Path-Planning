"""Investigate the *quality* of incremental plans against from-scratch ones.

Speed is easy to argue about and hard to get wrong; quality is the opposite.  The
interval-level tests prove the clipper is exact, but a plan is more than its
intervals, and a defect can live entirely in what is built from them.  This tool
exists because one did: the headland loops were being drawn around each *group*
of touching obstacles instead of around each obstacle, which cost up to 2.2 pp of
coverage on dense scenes while leaving the swath set bit-identical.

Four questions, one per subcommand:

``gap``
    Sweep field shape and obstacle density; report the coverage difference
    between an incremental plan and a from-scratch plan of the same scene at the
    same frozen heading.
``decompose``
    Split that difference into the part from the working strokes and the part
    from the headland, so the culprit is identified rather than guessed at.
``strokes``
    Compare the two plans' stroke *sets*.  Identical sets with a coverage gap
    means the loss is not in the strokes at all.
``benchmark``
    Apply the same analysis to the recorded experiment tables, split by change
    mode.  An average over modes hides a difference that is present in one and
    absent in the other.

Run:  python tools/diagnose_coverage.py gap
      python tools/diagnose_coverage.py benchmark
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".cache" / "matplotlib"))
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402
from shapely.geometry import LineString, box  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

from cppclip import geometry as G  # noqa: E402
from cppclip.fields import make_field  # noqa: E402
from cppclip.incremental import IncrementalPlanner  # noqa: E402
from cppclip.metrics import band_area, evaluate  # noqa: E402
from cppclip.planner import PlanParams, plan  # noqa: E402

WIDTH = 6.0

SCENARIOS = [
    ("rectilinear", 0, 20_000.0, 6),
    ("rectilinear", 4, 20_000.0, 6),
    ("rectilinear", 10, 20_000.0, 6),
    ("star", 10, 20_000.0, 6),
    ("rect", 20, 40_000.0, 8),
]


def _params(angle: float | None = None) -> PlanParams:
    return PlanParams(
        swath_width=WIDTH, headland_width=6.0, route="optimised",
        min_swath_length=1.5, n_angle_candidates=24, angle=angle,
    )


def _obstacles(field, count: int, half: float = 10.0):  # noqa: ANN001, ANN202
    """Deterministic obstacle boxes spread across the field's bounding box."""
    minx, miny, maxx, maxy = G.bounds_of(field.boundary)
    span = (maxx - minx - 4 * half) / max(1, count)
    for k in range(count):
        cx = minx + 2 * half + span * (k + 0.5)
        cy = miny + (maxy - miny) * (0.2 + 0.6 * ((k * 7) % 5) / 4)
        cand = G.normalise(box(cx - half, cy - half, cx + half, cy + half))
        if field.boundary.contains(cand):
            yield cand


def _pair(kind: str, n_built_in: int, area: float):  # noqa: ANN202
    field = make_field(kind, seed=4, n_obstacles=n_built_in, target_area=area)
    planner = IncrementalPlanner(field, _params(), global_repair_fraction=0.5, repair_window=4)
    return field, planner, _params(planner.angle)


def _stroke_key(s) -> tuple:  # noqa: ANN001
    a = (round(s.p0[0], 6), round(s.p0[1], 6))
    b = (round(s.p1[0], 6), round(s.p1[1], 6))
    return (a, b) if a <= b else (b, a)


def _swept(plan, with_headland: bool):  # noqa: ANN001, ANN202
    bands = [band_area(s, WIDTH) for s in plan.strokes if s.length > 0]
    if with_headland and plan.headland_points and len(plan.headland_points) >= 2:
        bands.append(
            LineString(plan.headland_points).buffer(
                WIDTH / 2.0, cap_style="flat", join_style="round"
            )
        )
    return unary_union(bands) if bands else None


# ---------------------------------------------------------------------------
def cmd_gap(_args) -> None:  # noqa: ANN001
    print("Incremental vs from-scratch plan, same scene, same frozen heading")
    for kind, n, area, changes in SCENARIOS:
        field, planner, frozen = _pair(kind, n, area)
        worst = 0.0
        rows = []
        for k, obs in enumerate(_obstacles(field, changes)):
            _h, rep = planner.add_obstacle(obs)
            scene = planner.current_field()
            mi = evaluate(scene, planner.to_plan())
            mf = evaluate(scene, plan(scene, frozen))
            gap = mf.coverage - mi.coverage
            worst = max(worst, gap)
            rows.append((k + 1, rep.mode, rep.n_affected_scanlines, rep.n_total_scanlines,
                         mi.coverage, mf.coverage, gap))
        print(f"\n{kind} built-in={n} area={area / 10_000:.0f}ha: "
              f"worst gap {100 * worst:+.2f} pp")
        print(f"  {'#':>2}  {'mode':<12} {'affected':>9}  {'inc cov':>8} {'full cov':>8} {'gap pp':>7}")
        for n_, mode, na, nt, ci, cf, gap in rows:
            flag = "  <-- notable" if gap > 0.005 else ""
            print(f"  {n_:>2}  {mode:<12} {na:>4}/{nt:<4}  {ci:>8.4f} {cf:>8.4f} "
                  f"{100 * gap:>+7.2f}{flag}")


def cmd_decompose(_args) -> None:  # noqa: ANN001
    print("Where the coverage difference lives: strokes vs headland")
    for kind, n, area, changes in SCENARIOS[:3]:
        field, planner, frozen = _pair(kind, n, area)
        print(f"\n{kind} built-in={n}")
        for k, obs in enumerate(_obstacles(field, changes)):
            _h, rep = planner.add_obstacle(obs)
            scene = planner.current_field()
            inc, full = planner.to_plan(), plan(scene, frozen)
            free = scene.free
            mi, mf = evaluate(scene, inc), evaluate(scene, full)
            print(f"  change {k + 1}: {rep.mode}  gap {100 * (mf.coverage - mi.coverage):+.2f} pp")
            for tag, p in (("incremental", inc), ("full", full)):
                a1 = _swept(p, False)
                a2 = _swept(p, True)
                s1 = a1.intersection(free).area / free.area if a1 else 0.0
                s2 = a2.intersection(free).area / free.area if a2 else 0.0
                print(f"    {tag:<12} strokes {len(p.strokes):3d}  "
                      f"stroke-only {s1:.4f}  with headland {s2:.4f}  "
                      f"headland adds {100 * (s2 - s1):+.3f} pp")


def cmd_strokes(_args) -> None:  # noqa: ANN001
    print("Stroke sets: incremental vs from-scratch")
    for kind, n, area, changes in SCENARIOS:
        field, planner, frozen = _pair(kind, n, area)
        print(f"\n{kind} built-in={n}")
        for k, obs in enumerate(_obstacles(field, changes)):
            _h, rep = planner.add_obstacle(obs)
            scene = planner.current_field()
            inc, full = planner.to_plan(), plan(scene, frozen)
            si = {_stroke_key(s) for s in inc.strokes}
            sf = {_stroke_key(s) for s in full.strokes}
            free = scene.free
            a1 = _swept(inc, False)
            a2 = _swept(full, False)
            c1 = a1.intersection(free).area / free.area if a1 else 0.0
            c2 = a2.intersection(free).area / free.area if a2 else 0.0
            print(f"  change {k + 1}: inc {len(si):3d} full {len(sf):3d}  "
                  f"only-inc {len(si - sf):2d} only-full {len(sf - si):2d}  "
                  f"stroke-only cov {c1:.4f} vs {c2:.4f} ({100 * (c2 - c1):+.3f} pp)")


def cmd_benchmark(_args) -> None:  # noqa: ANN001
    path = ROOT / "results" / "tables" / "exp2_incremental.csv"
    if not path.exists():
        print(f"missing {path}; run experiments/exp_incremental.py first")
        return
    df = pd.read_csv(path)
    df["gap_pp"] = 100 * (df.coverage_fixed - df.coverage_inc)
    print(f"{len(df)} recorded change events from {path.name}\n")
    print("overall (what a single headline number reports):")
    print(f"  inc {df.coverage_inc.mean():.4f}   fixed {df.coverage_fixed.mean():.4f}   "
          f"mean gap {df.gap_pp.mean():+.3f} pp   max {df.gap_pp.max():+.3f} pp")
    print("\nby change mode (the distinction the headline hides):")
    for mode, g in df.groupby("mode"):
        print(f"  {mode:<12} n={len(g):3d}  inc {g.coverage_inc.mean():.4f}  "
              f"fixed {g.coverage_fixed.mean():.4f}  mean {g.gap_pp.mean():+.3f} pp  "
              f"p90 {g.gap_pp.quantile(0.9):+.3f}  max {g.gap_pp.max():+.3f}")
    print("\nby route repair:")
    for mode, g in df.groupby("route_repair"):
        print(f"  {mode:<8} n={len(g):3d}  mean {g.gap_pp.mean():+.3f} pp  "
              f"max {g.gap_pp.max():+.3f} pp")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn, help_text in (
        ("gap", cmd_gap, "coverage difference by scenario"),
        ("decompose", cmd_decompose, "split it into strokes vs headland"),
        ("strokes", cmd_strokes, "compare the stroke sets"),
        ("benchmark", cmd_benchmark, "the same analysis on the recorded tables"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.set_defaults(func=fn)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
