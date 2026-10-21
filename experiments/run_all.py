"""Run the whole study end to end, in the order the report presents it.

Timing experiments are run **strictly sequentially**.  The numbers in the report
are single-run wall clock, and running two planners at once would make them
meaningless -- so this script never parallelises, however tempting it is.

The Fields2Cover comparison needs the container built by
``tools/setup_fields2cover.sh``; if Docker or the image is unavailable that stage
is skipped with a warning and the cppclip-side tables are still produced.

Run:  python experiments/run_all.py [--skip-container] [--quick]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = sys.executable

STAGES: list[tuple[str, list[str]]] = [
    ("1. clipping exactness and speed", ["exp_clipping.py"]),
    ("2. incremental vs full replanning", ["exp_incremental.py", "--fields", "60", "--changes", "6",
                                           "--min-area-ha", "1.0", "--max-area-ha", "8.0"]),
    ("3. scaling with field size", ["exp_scaling.py", "--scales", "1", "2", "4", "8",
                                    "--source-fields", "2", "--changes", "3"]),
    ("4. ablation: tour re-solve threshold", ["exp_ablation_repair.py", "--fields", "24", "--changes", "5"]),
    ("5. ablation: local repair window", ["exp_ablation_repair.py", "--fields", "20", "--changes", "4",
                                          "--fractions", "0.5", "--windows", "4", "8", "12", "20",
                                          "--tag", "exp_ablation_window"]),
    ("6. cost of kinematically feasible turns", ["exp_turn_radius.py", "--fields", "120"]),
    ("7. export cppclip solutions (Dubins, r = 2 m)", ["export_cppclip.py", "--limit", "400",
                                                       "--min-area-ha", "0.0", "--max-area-ha", "100.0",
                                                       "--turn-radius", "2.0"]),
]

QUICK = {
    "exp_clipping.py": ["--limit", "40"],
    "exp_incremental.py": ["--fields", "12", "--changes", "3"],
    "exp_scaling.py": ["--scales", "1", "4"],
    "exp_ablation_repair.py": ["--fields", "8", "--changes", "3"],
    "exp_turn_radius.py": ["--fields", "20"],
    "export_cppclip.py": ["--limit", "30"],
}

CONTAINER = [
    "docker.exe", "run", "--rm",
    "-v", f"{ROOT}:/work", "-w", "/work",
    "fields2cover:2.1.1", "python3", "-u", "/work/tools/f2c_benchmark.py",
]


def apply_quick(argv: list[str]) -> list[str]:
    """Append the quick overrides rather than replacing the argument list.

    Replacing it silently dropped arguments that are not about sample size --
    the ablation's ``--tag`` and ``--windows`` among them -- which turned the
    second ablation into a copy of the first and quietly produced the wrong
    table.  Argparse takes the last occurrence of a repeated option, so
    appending overrides only what it names.
    """
    overrides = QUICK.get(argv[0])
    return [*argv, *overrides] if overrides else argv


def snapshot_tables() -> Path | None:
    """Move the result tables aside so a smoke run cannot destroy them.

    ``--quick`` writes small-sample tables to the same paths as a real run.  Left
    alone it would silently replace the results the report is built on, and the
    only symptom would be a report whose numbers no longer match its artefacts.
    """
    tables = ROOT / "results" / "tables"
    if not tables.is_dir() or not any(tables.glob("*.csv")):
        return None
    backup = ROOT / "results" / "tables.pre-quick"
    if backup.exists():
        for old in backup.glob("*.csv"):
            old.unlink()
    else:
        backup.mkdir(parents=True)
    for csv in tables.glob("*.csv"):
        csv.rename(backup / csv.name)
    return backup


def restore_tables(backup: Path | None) -> None:
    if backup is None:
        return
    tables = ROOT / "results" / "tables"
    for csv in tables.glob("*.csv"):
        csv.unlink()
    for csv in backup.glob("*.csv"):
        csv.rename(tables / csv.name)
    backup.rmdir()
    print("[quick] real result tables restored")


def run(label: str, cmd: list[str]) -> bool:
    print(f"\n{'=' * 72}\n{label}\n{'=' * 72}", flush=True)
    t0 = time.perf_counter()
    result = subprocess.run(cmd, cwd=HERE)
    print(f"[{label}] exit {result.returncode} in {time.perf_counter() - t0:.1f}s", flush=True)
    return result.returncode == 0


def run_container_stage() -> bool:
    """Run the Fields2Cover sweep, or explain precisely why it cannot run here.

    Docker's CLI talks to the daemon over a Windows named pipe, and a sandboxed
    parent can be denied that pipe even when the same command works from a shell.
    That is an environment boundary, not a defect in the study, so it is detected
    and reported with the exact command to run by hand rather than retried.
    """
    print(f"\n{'=' * 72}\n8. Fields2Cover 2.1.1 sweep (container)\n{'=' * 72}", flush=True)
    try:
        result = subprocess.run(CONTAINER, cwd=ROOT, capture_output=True, text=True)
    except FileNotFoundError:
        print("[skip] docker.exe is not on PATH.")
        print("       Build the image with tools/setup_fields2cover.sh, then run:")
        print("       " + " ".join(CONTAINER))
        return False

    if result.returncode == 0:
        print(result.stdout[-2000:])
        return True

    stderr = (result.stderr or "").strip()
    print(f"[fail] docker exited {result.returncode}")
    if "pipe" in stderr.lower() or "permission denied" in stderr.lower():
        print(f"       {stderr.splitlines()[0] if stderr else ''}")
        print()
        print("       The Docker daemon is reached over a named pipe, which this")
        print("       process is not allowed to open. Run the sweep from a shell")
        print("       instead -- it works there -- and then re-run the comparison:")
        print()
        print("         " + " ".join(CONTAINER))
        print("         python experiments/exp_compare.py")
    elif stderr:
        print(stderr[-2000:])
    return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="small samples, for a smoke run")
    ap.add_argument("--skip-container", action="store_true")
    args = ap.parse_args()

    failures: list[str] = []
    backup = snapshot_tables() if args.quick else None
    if args.quick:
        print("[quick] real result tables moved aside; they will be restored at the end")
    try:
        for label, argv in STAGES:
            if args.quick:
                argv = apply_quick(argv)
            if not run(label, [PY, *argv]):
                failures.append(label)

        if args.skip_container:
            container_ok = False
            print("\n[skip] container stage skipped on request")
        else:
            container_ok = run_container_stage()

        if not container_ok:
            print("\n[warn] the comparison will use whatever Fields2Cover results")
            print("       are already in results/f2c_io/fields2cover/.")
        if not run("9. head-to-head comparison", [PY, "exp_compare.py"]):
            failures.append("head-to-head comparison")

        run("10. figures", [PY, "make_figures.py"])
        run("11. repository consistency", [PY, "verify.py"])
        if args.quick:
            print("\n[quick] skipping the number audit: the tables on disk are the")
            print("        small-sample ones, so a mismatch would be expected and")
            print("        would say nothing about the real run.")
        else:
            run("12. quoted numbers vs tables", [PY, "audit_numbers.py"])
        run("13. Dubins vs numerical search", [PY, str(ROOT / "tools" / "verify_dubins.py")])
    finally:
        restore_tables(backup)

    print(f"\n{'=' * 72}")
    if failures:
        print(f"FAILED STAGES: {failures}")
        sys.exit(1)
    print("all stages completed")


if __name__ == "__main__":
    main()
