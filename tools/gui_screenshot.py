"""Render the GUI to PNGs without a display.

A Qt application is hard to review from a terminal, so this drives the real
widgets -- with real plans built by the real library -- and grabs each tab.  It
is how the screenshots in the README are produced, and it doubles as a smoke
test: if a tab raises while being populated, this exits non-zero.

Run:  python tools/gui_screenshot.py [--out DIR]
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".cache" / "matplotlib"))
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from cppclip import geometry as G  # noqa: E402
from cppclip.fields import make_field  # noqa: E402
from cppclip.gui.main_window import MainWindow  # noqa: E402
from cppclip.gui.incremental_tab import IncrementalTab  # noqa: E402
from cppclip.gui.plan_tab import PlanTab  # noqa: E402
from cppclip.metrics import evaluate  # noqa: E402
from cppclip.planner import PlanParams, plan  # noqa: E402


def settle(app: QApplication, rounds: int = 6) -> None:
    for _ in range(rounds):
        app.processEvents()


def shoot(window, app: QApplication, path: Path) -> None:
    settle(app)
    pixmap = window.grab()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not pixmap.save(str(path)):
        raise RuntimeError(f"could not save {path}")
    print(f"  wrote {path}  ({pixmap.width()}x{pixmap.height()})")


def drive_plan_tab(tab: PlanTab, field=None) -> None:
    """Populate the planning tab through its own worker path, synchronously."""
    field = field or make_field("rectilinear", seed=4, n_obstacles=12, target_area=25_000.0)
    tab.source._current = field
    tab._on_field(field)
    payload = tab._solve(field, tab.params(), True, tab.cell_size.value())
    tab._on_planned(payload)


def drive_incremental_tab(tab: IncrementalTab, app: QApplication, clicks: int = 4) -> None:
    """Build the incremental planner through the tab's real async path, then click.

    Driving the widgets rather than calling the worker directly matters: the tab
    starts its build from ``source.rebuild()``, and short-circuiting that would
    leave a second build racing the first and produce a screenshot of a state the
    application never actually reaches.
    """
    tab.source.n_obstacles.setValue(4)
    tab.source.seed.setValue(4)
    tab.source.target_area.setValue(2.5)
    tab.source.kind.setCurrentIndex(4)  # rectilinear
    tab.source.rebuild()

    for _ in range(600):
        app.processEvents()
        if tab._planner is not None and not tab._busy:
            break
        time.sleep(0.02)
    if tab._planner is None:
        raise RuntimeError("the incremental planner never finished building")

    field = tab._field
    minx, miny, maxx, maxy = G.bounds_of(field.boundary)
    half = tab.size.value() / 2.0
    from shapely.geometry import box

    span_x = (maxx - minx - 4 * half) / max(1, clicks + 1)
    for k in range(clicks):
        cx = minx + 2 * half + span_x * (k + 0.5)
        cy = miny + (maxy - miny) * (0.32 + 0.18 * (k % 3))
        obstacle = G.normalise(box(cx - half, cy - half, cx + half, cy + half))
        if not field.boundary.contains(obstacle):
            continue
        # The handle is allocated by the planner, exactly as the click path does
        # it: a caller-chosen counter starting at zero collides with the handles
        # the planner already gave the field's own obstacles.
        change = tab._apply_change(
            tab._planner, obstacle, tab.compare_full.currentIndex() == 1, tab._params()
        )
        tab._on_changed(change)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "results" / "gui"))
    args = ap.parse_args()
    out = Path(args.out)

    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    window.resize(1380, 880)
    window.show()
    settle(app)

    print("rendering tabs:")
    window.tabs.setCurrentIndex(0)
    drive_plan_tab(window.plan_tab)
    shoot(window, app, out / "tab1_planning.png")

    window.tabs.setCurrentIndex(1)
    drive_incremental_tab(window.incremental_tab, app)
    shoot(window, app, out / "tab2_incremental.png")

    window.tabs.setCurrentIndex(2)
    window.results_tab.reload()
    for key in ("scaling", "compare"):
        index = next(i for i in range(window.results_tab.chooser.count())
                     if window.results_tab.chooser.itemData(i) == key)
        window.results_tab.chooser.setCurrentIndex(index)
        settle(app)
        shoot(window, app, out / f"tab3_results_{key}.png")

    print("all tabs rendered")


if __name__ == "__main__":
    main()
