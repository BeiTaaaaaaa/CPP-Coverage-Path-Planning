"""Cross-check every headline number in the write-up against the result tables.

The report quotes numbers by hand.  Two incidents in this project showed how
easily that goes wrong -- an ANSI encoding round-trip silently ate digits, and an
earlier draft quoted a run that had since been superseded -- so the numbers are
checked mechanically rather than trusted.

Run:  python experiments/audit_numbers.py
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(Path := __import__("pathlib").Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
TABLES = ROOT / "results" / "tables"


def load(name: str) -> pd.DataFrame:
    return pd.read_csv(TABLES / f"{name}.csv")


def main() -> None:
    report = (ROOT / "REPORT.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    # The Chinese editions quote the same measurements, so they are held to the
    # same standard.  A translation that drifts is worse than no translation:
    # it is the copy a Chinese-reading collaborator will actually check.
    report_zh = (ROOT / "REPORT.zh-CN.md").read_text(encoding="utf-8")
    readme_zh = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")

    e1 = load("exp1_clipping")
    e2 = load("exp2_incremental")
    e3 = load("exp3_scaling").groupby("scale").agg(
        sp_full=("speedup_vs_full", "median"),
        sp_fixed=("speedup_vs_fixed", "median"),
        affected=("affected_fraction", "mean"),
        penalty=("path_penalty", "mean"),
        t_inc=("t_incremental_s", "median"),
        t_full=("t_full_s", "median"),
        t_fixed=("t_full_fixed_s", "median"),
    )
    e4 = load("exp4_compare")
    cp = e4[e4.system == "cppclip"]
    f2 = e4[e4.system == "fields2cover"]
    e5 = load("exp5_turn_radius").groupby("turn_radius").agg(
        path=("path_length", "median"), ratio=("ratio_vs_straight", "median")
    )
    a1 = load("exp_ablation_repair")
    a2 = load("exp_ablation_window")

    ratio = float(
        (cp.set_index("field").total_length / f2.set_index("field").total_length).median()
    )

    # Two kinds of number, audited two ways.
    #
    # **Derived** quantities are functions of the geometry and the fixed seeds:
    # coverage, distances, counts, ratios, affected fractions.  They are
    # reproducible to the last digit, so a mismatch means the document is stale
    # and the check is exact.
    #
    # **Measured** quantities are wall-clock timings and anything computed from
    # them.  They move by tens of percent between runs on a desktop machine, so
    # an exact check would fail on every re-run and teach the reader to ignore
    # it.  Those are checked for being in the right ballpark instead, which still
    # catches a stale table from an earlier configuration.
    derived: list[tuple[str, str, tuple[str, ...]]] = [
        ("E1 scanlines", f"{int(e1.n_scanlines.sum()):,}", ("report", "report_zh")),
        ("E1 max error", f"{e1.max_abs_error.max():.3e}", ("report", "readme", "report_zh", "readme_zh")),
        ("E2 affected median", f"{100 * e2.affected_fraction.median():.1f} %", ("report", "report_zh")),
        ("E2 p90 penalty", f"{100 * e2.path_penalty_vs_fixed.quantile(0.9):+.2f} %", ("report", "report_zh")),
        # The headline coverage average is one number standing in for two
        # behaviours, and for most of this project it concealed a real defect
        # (REPORT.md section 7.1, finding 11).  The per-mode split is what the
        # report now quotes, so the per-mode split is what gets checked.
        ("E2 coverage, plain increments",
         f"{e2[e2['mode'] == 'incremental'].coverage_inc.mean():.4f}", ("report", "report_zh")),
        ("E2 coverage, group merges",
         f"{e2[e2['mode'] == 'group_merge'].coverage_inc.mean():.4f}", ("report", "report_zh")),
        ("E2 mean gap, plain increments",
         f"{100 * (e2[e2['mode'] == 'incremental'].coverage_fixed.mean() - e2[e2['mode'] == 'incremental'].coverage_inc.mean()):+.3f} pp",
         ("report", "report_zh")),
        ("E2 mean gap, group merges",
         f"{100 * (e2[e2['mode'] == 'group_merge'].coverage_fixed.mean() - e2[e2['mode'] == 'group_merge'].coverage_inc.mean()):+.3f} pp",
         ("report", "report_zh")),
        ("E3 x1 affected", f"{100 * e3.affected.iloc[0]:.1f} %", ("report", "readme", "report_zh", "readme_zh")),
        ("E3 x8 affected", f"{100 * e3.affected.iloc[3]:.1f} %", ("report", "readme", "report_zh", "readme_zh")),
        ("E4 cppclip coverage", f"{cp.coverage.median():.4f}", ("report", "readme", "report_zh", "readme_zh")),
        ("E4 f2c coverage", f"{f2.coverage.median():.4f}", ("report", "readme", "report_zh", "readme_zh")),
        ("E4 cppclip distance", f"{cp.total_length.median():.0f} m", ("report", "readme", "report_zh", "readme_zh")),
        ("E4 f2c distance", f"{f2.total_length.median():.0f} m", ("report", "readme", "report_zh", "readme_zh")),
        ("E4 cppclip non-working", f"{100 * cp.non_working_ratio.median():.1f} %", ("report", "readme", "report_zh", "readme_zh")),
        ("E4 f2c non-working", f"{100 * f2.non_working_ratio.median():.1f} %", ("report", "readme", "report_zh", "readme_zh")),
        ("E4 overlap cppclip", f"{100 * cp.overlap.median():.2f} %", ("report", "readme", "report_zh", "readme_zh")),
        ("E4 overlap f2c", f"{100 * f2.overlap.median():.2f} %", ("report", "readme", "report_zh", "readme_zh")),
        ("E4 distance ratio", f"{ratio:.3f}", ("report", "readme", "report_zh", "readme_zh")),
        ("E5 r=1 ratio", f"{e5.ratio.loc[1.0]:.3f}", ("report", "report_zh")),
        ("E5 r=2 ratio", f"{e5.ratio.loc[2.0]:.3f}", ("report", "report_zh")),
        ("E5 r=4 ratio", f"{e5.ratio.loc[4.0]:.3f}", ("report", "report_zh")),
        # The README quotes these as the *percentage* the straight-connector
        # distance understates, not as the ratio, so the two documents express
        # the same measurement in different forms.
        ("E5 r=2 understatement", f"{100 * (e5.ratio.loc[2.0] - 1):.1f} %", ("readme", "readme_zh")),
        ("E5 r=4 understatement", f"{100 * (e5.ratio.loc[4.0] - 1):.1f} %", ("readme", "readme_zh")),
        ("E5 r=2 path", f"{e5.path.loc[2.0]:.0f} m", ("report", "report_zh")),
    ]
    measured: list[tuple[str, float, tuple[str, ...]]] = [
        ("E1 median speed-up", float(e1.speedup.median()), ("report", "readme", "report_zh", "readme_zh")),
        ("E2 speed-up vs full", float(e2.speedup_vs_full.median()), ("report", "report_zh")),
        ("E2 speed-up vs fixed", float(e2.speedup_vs_fixed.median()), ("report", "report_zh")),
        ("E2 incremental ms", 1000 * float(e2.t_incremental_s.median()), ("report", "report_zh")),
        ("E2 full ms", 1000 * float(e2.t_full_s.median()), ("report", "report_zh")),
        ("E2 fixed ms", 1000 * float(e2.t_full_fixed_s.median()), ("report", "report_zh")),
        ("E3 x1 speed-up", float(e3.sp_full.iloc[0]), ("report", "readme", "report_zh", "readme_zh")),
        ("E3 x2 speed-up", float(e3.sp_full.iloc[1]), ("report", "readme", "report_zh", "readme_zh")),
        ("E3 x4 speed-up", float(e3.sp_full.iloc[2]), ("report", "readme", "report_zh", "readme_zh")),
        ("E3 x8 speed-up", float(e3.sp_full.iloc[3]), ("report", "readme", "report_zh", "readme_zh")),
        ("E4 cppclip time", float(cp.time_s.median()), ("report", "readme", "report_zh", "readme_zh")),
        ("E4 f2c time", float(f2.time_s.median()), ("report", "readme", "report_zh", "readme_zh")),
    ]

    # The ablation tables are timing-dominated too, and were the last thing left
    # out of this audit -- which is exactly why they had drifted a full run
    # behind by the time anyone looked.  Every cell of both tables is checked.
    for _, row in a1.iterrows():
        frac = row["global_fraction"]
        measured.append((f"ablation fraction {frac:g} ms", float(row["t_incremental_median_ms"]), ("report", "report_zh")))
        measured.append((f"ablation fraction {frac:g} speed-up", float(row["speedup_vs_fixed_median"]), ("report", "report_zh")))
    for _, row in a2.iterrows():
        window = int(row["repair_window"])
        measured.append((f"ablation window {window} ms", float(row["t_incremental_median_ms"]), ("report", "report_zh")))
        measured.append((f"ablation window {window} speed-up", float(row["speedup_vs_fixed_median"]), ("report", "report_zh")))

    # The share of changes that fell back to a global re-solve is deterministic.
    for _, row in a1.iterrows():
        derived.append(
            (
                f"ablation fraction {row['global_fraction']:g} pct-global",
                f"{100 * row['pct_global']:.0f} %",
                ("report", "report_zh"),
            )
        )

    tolerance = 0.15

    flat = {
        "report": report,
        "readme": readme,
        "report_zh": report_zh,
        "readme_zh": readme_zh,
    }
    bad = 0

    for label, want, where in derived:
        key = _normalise(want)
        missing = [d for d in where if key not in _normalise(flat[d])]
        if missing:
            print(f"  STALE in {', '.join(d.upper() for d in missing):20} {label:24} tables imply {want!r}")
            bad += 1

    for label, value, where in measured:
        for doc in where:
            if not _mentions_within(flat[doc], value, tolerance):
                print(
                    f"  STALE in {doc.upper():20} {label:24} no value within "
                    f"+/-{tolerance:.0%} of {value:.4g}"
                )
                bad += 1

    total = len(derived) + sum(len(w) for _, _, w in measured)
    print(f"\n{total - bad}/{total} table-derived values are current in every document that quotes them")
    if bad:
        print("\nDerived values must match exactly; measured ones are wall-clock and")
        print(f"are accepted within +/-{tolerance:.0%}. Fix the document, not this script.")
        print("\nFor the current value of every quantity, run:")
        print("  python tools/print_numbers.py")
        print("Timings move by ~10% between runs, so after a full re-run the quoted")
        print("figures have to be refreshed by hand; that tool makes it mechanical.")


def _normalise(text: str) -> str:
    return text.replace(" ", "").replace("\u00a0", "").replace("**", "")


def _mentions_within(text: str, value: float, tolerance: float) -> bool:
    """Does *text* contain a number within *tolerance* of *value*?

    Scans every numeric token, so it does not care how the document rounded or
    formatted it -- only that a figure of the right size is present.
    """
    import re

    patterns = [r"-?\d+\.\d+", r"-?\d+"]
    for pattern in patterns:
        for token in re.findall(pattern, text):
            try:
                found = float(token)
            except ValueError:
                continue
            if value == 0:
                if abs(found) < 1e-9:
                    return True
            elif abs(found - value) / abs(value) <= tolerance:
                return True
    return False


if __name__ == "__main__":
    main()
