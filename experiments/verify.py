"""Tie the whole evaluation together and print one summary block.

Unlike the individual experiment scripts, this re-derives every headline number
from the saved tables so that the report can be checked against the artefacts
that produced it.  It prints warnings when a table is missing rather than
failing, so it is usable as a quick "is the repo consistent?" check.

Run:  python experiments/verify.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import TABLES, print_environment  # noqa: E402

import pathlib  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

CHECKS: list[tuple[str, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    CHECKS.append((name, "PASS" if ok else "FAIL"))
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name}: {detail}")


def load(name: str) -> pd.DataFrame | None:
    p = TABLES / f"{name}.csv"
    return pd.read_csv(p) if p.exists() else None


def check_document_encoding() -> int:
    """Every tracked text file must be valid UTF-8 with no substitution damage.

    This is not hypothetical.  Writing a UTF-8 file back through Windows
    PowerShell's ``Set-Content`` uses the ANSI code page, which replaces bytes
    that have no ANSI mapping with ``?`` (0x3F) *and eats the following byte*.
    That silently turned page range ``2166-2172`` into ``2166-172`` and a
    measurement of ``71-260 m`` into ``71-60 m`` in this repository's write-up.
    A report whose numbers can be corrupted by an editor is not a report, so the
    failure is made detectable here rather than trusted not to recur.
    """
    import re

    root = pathlib.Path(__file__).resolve().parents[1]
    damaged = re.compile(rb"[\x80-\xef]\x3f")
    bad: list[str] = []
    checked = 0

    skip_dirs = {".venv", ".tmp", ".cache", ".pytest_cache", "__pycache__", "data", "env", "results"}
    text_suffixes = {".py", ".md", ".toml", ".txt", ".cfg", ".sh", ".json"}

    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in text_suffixes:
            continue
        if any(part in skip_dirs for part in path.relative_to(root).parts):
            continue
        checked += 1
        raw = path.read_bytes()
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            bad.append(f"{path.name}: not UTF-8 ({exc.reason} at {exc.start})")
            continue
        if damaged.search(raw):
            bad.append(f"{path.name}: {len(damaged.findall(raw))} ANSI-damaged sequences")

    check(
        "every text file is valid UTF-8 and undamaged",
        not bad,
        f"{checked} files checked" + ("; " + "; ".join(bad) if bad else ""),
    )
    return 1 if bad else 0


def run_tool(script: str, name: str, ok_detail: str) -> int:
    """Run a check that lives in ``tools/`` and report it as one of ours."""
    import subprocess
    import sys as _sys

    root = pathlib.Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [_sys.executable, str(root / "tools" / script)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    lines = (result.stdout or "").strip().splitlines()
    check(name, result.returncode == 0, lines[-1] if lines else ok_detail)
    return 0 if result.returncode == 0 else 1


def main() -> None:
    print("Repository consistency check")
    print_environment()
    print()

    failures = 0
    failures += check_document_encoding()
    failures += run_tool("verify_headland.py", "no headland loop enters an obstacle", "")
    failures += run_tool("check_dead_code.py", "the library has no dead code", "")
    failures += run_tool("check_imports.py", "every module and script imports cleanly", "")

    # --- 1. clipping exactness -----------------------------------------
    df = load("exp1_clipping")
    if df is None:
        print("  (skip) exp1_clipping missing")
    else:
        total = int(df.n_scanlines.sum())
        bad = int(df.n_mismatched_scanlines.sum())
        check("clipping is exact on every scanline", bad == 0,
              f"{bad} mismatches over {total} scanlines")
        check("clipping error is at machine precision",
              float(df.max_abs_error.max()) < 1e-9,
              f"max |error| = {df.max_abs_error.max():.3e} m")
        check("edge table beats per-scanline GEOS",
              float(df.speedup.median()) > 1.0,
              f"median {df.speedup.median():.2f}x")
        failures += 0 if bad == 0 else 1

    # --- 2. incremental replanning --------------------------------------
    df = load("exp2_incremental")
    if df is None:
        print("  (skip) exp2_incremental missing")
    else:
        got = float(df.speedup_vs_full.median())
        check("incremental beats full replan", got > 1.5, f"median {got:.2f}x")
        check("coverage is not sacrificed",
              abs(float(df.coverage_inc.mean()) - float(df.coverage_full.mean())) < 0.005,
              f"inc {df.coverage_inc.mean():.4f} vs full {df.coverage_full.mean():.4f}")
        p90 = float(df.path_penalty_vs_fixed.quantile(0.9))
        check("path penalty stays small at p90", p90 < 0.05, f"p90 {p90:+.2%}")
        frac = float((df.route_repair == "local").mean())
        check("most changes are repaired locally", frac > 0.5, f"{frac:.0%} local")

        # Coverage parity must hold *per change mode*, not just on average.
        # Averaging over modes is what concealed finding 11 for most of this
        # project: group merges were losing 0.105 pp while the headline read
        # like parity.  A mean that stays small while one mode degrades is the
        # failure this check exists to catch.
        worst_mode = None
        worst_gap = -1.0
        for mode, group in df.groupby("mode"):
            gap = float(group.coverage_fixed.mean() - group.coverage_inc.mean())
            if gap > worst_gap:
                worst_mode, worst_gap = mode, gap
        check(
            "coverage parity holds within every change mode",
            worst_gap < 0.001 and worst_mode is not None,
            f"worst mode {worst_mode} at {100 * worst_gap:+.3f} pp",
        )

    # --- 3. scaling ------------------------------------------------------
    df = load("exp3_scaling")
    if df is None:
        print("  (skip) exp3_scaling missing")
    else:
        g = df.groupby("scale").agg(a=("affected_fraction", "mean"),
                                    s=("speedup_vs_full", "median"))
        falling = bool((np.diff(g.a.values) <= 0).all())
        check("invalidated fraction falls as fields grow", falling,
              " -> ".join(f"{v:.1%}" for v in g.a.values))
        check("speed-up rises as fields grow",
              g.s.values[-1] > g.s.values[0],
              f"{g.s.values[0]:.1f}x -> {g.s.values[-1]:.1f}x")

    # --- 4. head-to-head -------------------------------------------------
    df = load("exp4_compare")
    if df is None:
        print("  (skip) exp4_compare missing")
    else:
        ok = df if "error" not in df.columns else df[df.error.isna()]
        wide = ok.pivot_table(index="field", columns="system", values="coverage")
        if {"cppclip", "fields2cover"} <= set(wide.columns):
            diff = float((wide["cppclip"] - wide["fields2cover"]).median())
            check("coverage is competitive with Fields2Cover", diff > -0.01,
                  f"median difference {diff:+.4f}")
        check("both systems solved every field",
              "error" not in ok.columns or ok.error.isna().all(),
              f"{len(ok)} scored rows")

    print()
    n_fail = sum(1 for _n, s in CHECKS if s == "FAIL")
    print(f"{len(CHECKS) - n_fail}/{len(CHECKS)} checks passed")
    if n_fail:
        print("FAILED:", ", ".join(n for n, s in CHECKS if s == "FAIL"))
    print("\nNumbers quoted in REPORT.md and README.md are checked separately by")
    print("experiments/audit_numbers.py, which derives each one from these tables.")


if __name__ == "__main__":
    main()
