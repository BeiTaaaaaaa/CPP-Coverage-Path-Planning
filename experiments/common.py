"""Shared plumbing for the experiment scripts."""

from __future__ import annotations

import os
import platform
import sys
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path

_HERE = Path(__file__).resolve().parent
ROOT = _HERE.parent

# Keep matplotlib's cache inside the repo: reproducible, and it avoids fighting
# over (or being blocked from) the user profile directory.
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".cache" / "matplotlib"))

RESULTS = ROOT / "results"
TABLES = RESULTS / "tables"
FIGURES = RESULTS / "figures"

__all__ = ["ROOT", "RESULTS", "TABLES", "FIGURES", "ensure_dirs", "save_table", "environment"]


def ensure_dirs() -> None:
    for d in (RESULTS, TABLES, FIGURES):
        d.mkdir(parents=True, exist_ok=True)


def save_table(rows, name: str):
    """Write a list of dicts (or dataclasses) to CSV and return the DataFrame."""
    import pandas as pd

    ensure_dirs()
    records = [asdict(r) if is_dataclass(r) else dict(r) for r in rows]
    df = pd.DataFrame.from_records(records)
    path = TABLES / f"{name}.csv"
    df.to_csv(path, index=False)
    print(f"[table] {path}  ({len(df)} rows x {len(df.columns)} cols)")
    return df


def environment() -> dict:
    """Versions of everything that could affect a timing number."""
    import numpy
    import pandas
    import shapely

    try:
        import matplotlib

        mpl = matplotlib.__version__
    except Exception:  # noqa: BLE001
        mpl = "absent"

    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "processor": platform.processor(),
        "numpy": numpy.__version__,
        "shapely": shapely.__version__,
        "geos": shapely.geos_version_string,
        "pandas": pandas.__version__,
        "matplotlib": mpl,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def print_environment() -> None:
    for k, v in environment().items():
        print(f"  {k:<12} {v}")
