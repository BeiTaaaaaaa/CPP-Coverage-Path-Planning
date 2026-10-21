"""Experiment 1 -- is the clipping core exact, and is it faster than clipping with GEOS?

Two claims are tested:

**Exactness.**  For every field in the benchmark, every scanline's effective
intervals computed by the edge table must equal the intervals computed by
intersecting a line with the exact free-space polygon via GEOS.  A single
mismatching scanline invalidates the whole approach.

**Speed.**  The edge table answers *all* scanlines from one pass over the edges,
whereas the GEOS route runs a full clipping operation per scanline.  The
comparison is deliberately like-for-like: same scanlines, same region.

Run:  python experiments/exp_clipping.py [--limit N] [--width 6.0]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import environment, print_environment, save_table  # noqa: E402

import numpy as np  # noqa: E402

from cppclip.io_fields import load_benchmark  # noqa: E402
from cppclip.sweep import ScanlineClipper  # noqa: E402


def compare_field(field, width: float, tol: float = 1e-6) -> dict:
    """Compare edge-table intervals against GEOS on every scanline of one field."""
    clip = ScanlineClipper.from_geometry(field.free, width)

    t0 = time.perf_counter()
    fast = clip.all_intervals()
    t_fast = time.perf_counter() - t0

    t0 = time.perf_counter()
    ref = [clip.intervals_geos(i) for i in range(clip.n_scanlines)]
    t_geos = time.perf_counter() - t0

    n_bad = 0
    max_err = 0.0
    for got, want in zip(fast, ref):
        got = sorted(got)
        want = sorted(want)
        if len(got) != len(want):
            n_bad += 1
            continue
        for (a0, a1), (b0, b1) in zip(got, want):
            err = max(abs(a0 - b0), abs(a1 - b1))
            max_err = max(max_err, err)
            if err > tol:
                n_bad += 1
                break

    n_segments = sum(len(line) for line in fast)
    return {
        "field": field.name,
        "country": field.meta.get("country"),
        "area_m2": field.area,
        "n_scanlines": clip.n_scanlines,
        "n_edges": clip.n_edges,
        "n_segments": n_segments,
        "n_mismatched_scanlines": n_bad,
        "max_abs_error": max_err,
        "t_edge_table_s": t_fast,
        "t_geos_s": t_geos,
        "speedup": (t_geos / t_fast) if t_fast > 0 else float("nan"),
        "edge_load_mean": float(clip.edge_load().mean()),
        "edge_load_max": int(clip.edge_load().max()),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="cap the number of fields")
    ap.add_argument("--width", type=float, default=6.0, help="swath width [m]")
    args = ap.parse_args()

    print("Experiment 1: clipping-core exactness and speed")
    print_environment()
    print()

    fields = load_benchmark(limit=args.limit)
    print(f"loaded {len(fields)} real fields, swath width {args.width} m\n")

    rows = []
    for k, field in enumerate(fields, 1):
        rows.append(compare_field(field, args.width))
        if k % 25 == 0:
            print(f"  ... {k}/{len(fields)}")

    df = save_table(rows, "exp1_clipping")

    total_scan = int(df.n_scanlines.sum())
    total_bad = int(df.n_mismatched_scanlines.sum())
    print("\n--- exactness ---")
    print(f"scanlines compared : {total_scan}")
    print(f"mismatched         : {total_bad}")
    print(f"max abs error      : {df.max_abs_error.max():.3e}")
    verdict = "EXACT" if total_bad == 0 else "MISMATCH"
    print(f"verdict            : {verdict}")

    print("\n--- speed (all scanlines of one field) ---")
    print(f"edge table  total  : {df.t_edge_table_s.sum():8.4f} s")
    print(f"GEOS        total  : {df.t_geos_s.sum():8.4f} s")
    print(f"speedup median     : {df.speedup.median():8.2f} x")
    print(f"speedup min/median/max: {df.speedup.min():.2f} / {df.speedup.median():.2f} / {df.speedup.max():.2f}")

    bad = df[df.n_mismatched_scanlines > 0]
    if len(bad):
        print("\nfields with mismatches:")
        print(bad[["field", "n_scanlines", "n_mismatched_scanlines", "max_abs_error"]].to_string(index=False))


if __name__ == "__main__":
    main()
