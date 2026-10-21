"""Experiment 4 -- cppclip versus Fields2Cover on identical real-field geometry.

Both systems are handed the same metric field outlines, the same 6 m swath
width and the same 6 m headland, and each writes back its working strokes, its
headland loops and its full driven polyline.  **One** scorer
(:func:`cppclip.metrics.score_solution`) then computes every metric for both, so
no difference can come from two libraries defining "coverage" differently.

Run:  python experiments/exp_compare.py
(after `export_cppclip.py` and the Fields2Cover sweep have both populated
`results/f2c_io/`)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import print_environment, save_table  # noqa: E402
from f2c_io import IO_DIR  # noqa: E402

import numpy as np  # noqa: E402

from cppclip.io_fields import load_benchmark  # noqa: E402
from cppclip.metrics import score_solution  # noqa: E402

WIDTH = 6.0


def load_solutions(system: str) -> dict[str, dict]:
    d = IO_DIR / system
    if not d.is_dir():
        return {}
    out = {}
    for p in sorted(d.glob("*.json")):
        try:
            out[p.stem] = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            print(f"  ! could not read {p.name}: {exc}")
    return out


def main() -> None:
    print("Experiment 4: cppclip vs Fields2Cover")
    print_environment()
    print()

    # Must match the filter used by `export_cppclip.py`, otherwise fields that
    # were planned and scored simply never appear in the comparison.
    fields = {f.name: f for f in load_benchmark(min_area_ha=0.0, max_area_ha=100.0)}
    mine = load_solutions("cppclip")
    theirs = load_solutions("fields2cover")
    print(f"fields in benchmark index : {len(fields)}")
    print(f"cppclip solutions         : {len(mine)}")
    print(f"fields2cover solutions    : {len(theirs)}")

    if not theirs:
        print("\nNo Fields2Cover solutions found. Run the container sweep first;")
        print(f"expected them under {IO_DIR / 'fields2cover'}")
        return

    common = sorted(set(mine) & set(theirs))
    print(f"comparable fields         : {len(common)}\n")

    rows = []
    for name in common:
        field = fields.get(name)
        if field is None:
            continue
        for system, sol in (("cppclip", mine[name]), ("fields2cover", theirs[name])):
            if sol.get("error"):
                rows.append({"field": name, "system": system, "error": str(sol["error"])})
                continue
            try:
                scored = score_solution(
                    field,
                    swaths=[(tuple(s[0]), tuple(s[1])) for s in sol["swaths"]],
                    # One entry per loop.  Flattening them here would weld the
                    # loops together with joining segments that are then swept
                    # and measured as work, on both sides of the comparison.
                    headland=[
                        [tuple(p) for p in loop] for loop in sol.get("headland_loops", [])
                    ],
                    path=[tuple(p) for p in sol.get("path", [])],
                    width=WIDTH,
                    # Both systems track this exactly in their own planner, and
                    # both were asked to export it.  Passing it through keeps the
                    # odometer split in the units each planner actually uses.
                    working_length=sol.get("working_length"),
                    transit_length=sol.get("transit_length"),
                    total_length=sol.get("total_length"),
                )
            except Exception as exc:  # noqa: BLE001
                rows.append({"field": name, "system": system, "error": f"{type(exc).__name__}: {exc}"})
                continue
            scored.update(
                {
                    "system": system,
                    "area_m2": field.area,
                    "area_ha": field.area / 10_000.0,
                    "time_s": float(sol.get("time_s", float("nan"))),
                    "country": field.meta.get("country"),
                    "n_vertices": field.meta.get("n_vertices"),
                    "route": sol.get("route", "cppclip-optimised"),
                }
            )
            rows.append(scored)

    df = save_table(rows, "exp4_compare")

    ok = df[~df.get("error", False).fillna(False)] if "error" in df.columns else df
    failed = df[df.get("error", False).notna()] if "error" in df.columns else df.iloc[0:0]
    if len(failed):
        print(f"\nfailed/errored rows: {len(failed)}")
        print(failed[["field", "system", "error"]].head(20).to_string(index=False))

    print("\n--- headline (median over comparable fields) ---")
    summary = ok.groupby("system").agg(
        n=("field", "count"),
        coverage=("coverage", "median"),
        missed=("missed", "median"),
        overlap=("overlap", "median"),
        spillage=("spillage", "median"),
        total_length=("total_length", "median"),
        non_working=("non_working_ratio", "median"),
        n_swaths=("n_swaths", "median"),
        time_s=("time_s", "median"),
    )
    print(summary.to_string(float_format=lambda v: f"{v:10.4f}"))

    wide = ok.pivot_table(index="field", columns="system",
                          values=["coverage", "total_length", "non_working_ratio", "time_s"])
    try:
        ratio = (
            wide[("total_length", "cppclip")] / wide[("total_length", "fields2cover")]
        ).dropna()
        print(f"\ntotal-length ratio cppclip/fields2cover: "
              f"median {ratio.median():.4f}  mean {ratio.mean():.4f}  "
              f"p10 {ratio.quantile(0.1):.4f}  p90 {ratio.quantile(0.9):.4f}")
        cov = wide[("coverage", "cppclip")] - wide[("coverage", "fields2cover")]
        cov = cov.dropna()
        print(f"coverage difference (cppclip - fields2cover): "
              f"median {cov.median():+.4f}  mean {cov.mean():+.4f}")
    except KeyError:
        pass


if __name__ == "__main__":
    main()
