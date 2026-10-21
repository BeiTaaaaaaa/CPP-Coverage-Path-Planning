"""Interactive viewer for the coverage-planning results.

Run it with::

    python -m cppclip.gui

Three tabs:

``田地规划``
    Pick a field (synthetic, or one of the 350 real Fields2Benchmark fields),
    set the planning parameters, and see the swaths, headland, transit path and
    every metric.
``增量重算``
    Click on the canvas to drop an obstacle.  The planner re-clips only the
    scanlines that obstacle spans, keeps the surviving strokes in place and
    repairs the tour locally, and the tab reports that against solving the same
    scene from scratch -- the paper's headline experiment, interactively.
``实验结果``
    The five experiments, re-plotted from ``results/tables/*.csv``, with the raw
    table underneath.

The GUI is a *view*: it computes nothing that the library does not already
compute, and it never reports a number it did not obtain from the library.
"""

from __future__ import annotations

__all__ = ["run", "MainWindow"]


def run() -> int:
    """Start the application and return the process exit code."""
    import os
    import sys
    from pathlib import Path

    # Keep matplotlib's cache inside the repository, like every other entry
    # point here: reproducible, and it avoids fighting over the user profile.
    root = Path(__file__).resolve().parents[3]
    os.environ.setdefault("MPLCONFIGDIR", str(root / ".cache" / "matplotlib"))

    from PySide6.QtWidgets import QApplication

    from .main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("cppclip")
    app.setApplicationDisplayName("cppclip 结果查看器")

    window = MainWindow()
    window.show()
    return int(app.exec())

