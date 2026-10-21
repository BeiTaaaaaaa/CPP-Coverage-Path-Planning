"""Reusable read-out widgets: the metric grid and the per-stage timing bar.

Both exist to make the *numbers* as legible as the picture.  A coverage plan that
looks right but took 900 ms to compute is not the same result as one that took
90 ms, and the timing bar is what makes that difference visible at a glance
rather than buried in a table row.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import theme

__all__ = ["MetricGrid", "TimingBar", "LayerPanel"]

#: Stage colours for the timing bar, in pipeline order.  Read left to right in
#: roughly the order the planner executes them.
STAGE_COLOURS = {
    "free": QColor("#4c72b0"),
    "headland": QColor("#55a868"),
    "heading": QColor("#c44e52"),
    "clip": QColor("#8172b2"),
    "route": QColor("#ccb974"),
    "rotate": QColor("#64b5cd"),
    "headland_path": QColor("#8c8c8c"),
}
STAGE_LABELS = {
    "free": "自由空间",
    "headland": "地头内缩",
    "heading": "作业角搜索",
    "clip": "裁剪（核心）",
    "route": "路径排序",
    "rotate": "坐标旋转",
    "headland_path": "地头路径",
}


class MetricGrid(QGroupBox):
    """A two-column label/value read-out that can be rewritten in place."""

    #: Row pitch.  Set as a minimum height so the grid cannot be squeezed by a
    #: scroll area into rows that overlap their own text.
    ROW_HEIGHT = 23

    def __init__(self, title: str = "指标", parent: QWidget | None = None) -> None:
        super().__init__(title, parent)
        self._grid = QGridLayout(self)
        self._grid.setColumnStretch(1, 1)
        self._grid.setVerticalSpacing(4)
        self._grid.setHorizontalSpacing(10)
        self._grid.setContentsMargins(8, 6, 8, 6)
        self._rows: dict[str, QLabel] = {}
        self._row = 0
        self._enforce_height()

    def _enforce_height(self) -> None:
        self.setMinimumHeight(self._row * (self.ROW_HEIGHT + 4) + 26)

    def clear(self) -> None:
        """Drop every row.

        ``deleteLater`` alone is not enough: it schedules destruction but leaves
        the widget parented and *paintable* until the event loop catches up, so
        the previous frame's labels stay on screen and the new ones are drawn
        over them.  Reparenting to ``None`` removes it immediately; the later
        deletion still happens.
        """
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._rows.clear()
        self._row = 0
        self._enforce_height()

    def add(self, key: str, label: str, value: str, colour: str | None = None, bold: bool = False) -> None:
        name = QLabel(label)
        name.setStyleSheet(f"color:{theme.MUTED};")
        val = QLabel(value)
        val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        style = "font-family:Consolas,monospace;"
        if colour:
            style += f"color:{colour};"
        if bold:
            style += "font-weight:600;"
        val.setStyleSheet(style)
        for widget in (name, val):
            widget.setMinimumHeight(self.ROW_HEIGHT - 4)
        self._grid.addWidget(name, self._row, 0)
        self._grid.addWidget(val, self._row, 1)
        self._grid.setRowMinimumHeight(self._row, self.ROW_HEIGHT)
        # Adding a widget back to a layout does not un-hide it, and no new show
        # event reaches a parent that is already visible.  This is the other half
        # of the ``setParent(None)`` in ``clear``: without it the first fill
        # shows and every later one renders as an empty frame.
        name.show()
        val.show()
        self._rows[key] = val
        self._row += 1
        self._enforce_height()

    def set(self, key: str, value: str) -> None:
        if key in self._rows:
            self._rows[key].setText(value)


class TimingBar(QWidget):
    """Stacked bar of the planner's per-stage wall clock.

    Kept separate from :class:`MetricGrid` because the interesting information is
    the *proportion*: on these fields clipping is a rounding error and routing
    dominates, which is the single most surprising thing about the pipeline and
    the one a reader is least likely to believe from a table.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(46)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._timings: dict[str, float] = {}

    def set_timings(self, timings: dict[str, float]) -> None:
        self._timings = {k: float(v) for k, v in timings.items() if v and v > 0}
        self.setToolTip(
            "\n".join(
                f"{STAGE_LABELS.get(k, k)}: {1000 * v:.2f} ms"
                for k, v in sorted(self._timings.items(), key=lambda kv: -kv[1])
            )
            or "尚无计时"
        )
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ANN001 - Qt signature
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        rect = QRectF(4.0, 4.0, self.width() - 8.0, 20.0)
        painter.setPen(QPen(QColor(theme.BORDER)))
        painter.setBrush(QBrush(QColor("#ffffff")))
        painter.drawRect(rect)

        total = sum(self._timings.values())
        if total <= 0:
            painter.setPen(QPen(QColor(theme.MUTED)))
            painter.setFont(QFont("", 8))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "尚未规划")
            painter.end()
            return

        x = rect.left()
        for stage, value in sorted(self._timings.items(), key=lambda kv: -kv[1]):
            width = rect.width() * value / total
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(STAGE_COLOURS.get(stage, QColor("#bbbbbb"))))
            painter.drawRect(QRectF(x, rect.top(), width, rect.height()))
            if width > 46:
                painter.setPen(QPen(QColor("#1a1a1a")))
                painter.setFont(QFont("", 7))
                painter.drawText(
                    QRectF(x, rect.top(), width, rect.height()),
                    Qt.AlignmentFlag.AlignCenter,
                    f"{STAGE_LABELS.get(stage, stage)} {100 * value / total:.0f}%",
                )
            x += width

        painter.setPen(QPen(QColor(theme.BOUNDARY)))
        painter.setFont(QFont("", 8))
        painter.drawText(
            QRectF(4.0, 26.0, self.width() - 8.0, 16.0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"合计 {1000 * total:.1f} ms",
        )
        painter.end()


class LayerPanel(QGroupBox):
    """Check-boxes for every overlay the canvas can draw.

    Shared by the planning and incremental tabs so the two cannot drift: a layer
    added to :class:`~cppclip.gui.field_view.Layer` shows up in both, in the same
    order, with the same default.  Emits :attr:`changed` with the active set.
    """

    changed = Signal(set)
    raster_requested = Signal()

    def __init__(self, default: set[str], parent: QWidget | None = None) -> None:
        from . import theme as _theme
        from .field_view import Layer

        super().__init__("图层", parent)
        self._layer = Layer
        self._boxes: dict[str, object] = {}
        grid = QGridLayout(self)
        grid.setVerticalSpacing(2)
        for k, (key, label) in enumerate(Layer.LABELS):
            box = QCheckBox(label)
            box.setChecked(key in default)
            box.toggled.connect(self._emit)
            if key == Layer.COVERAGE:
                box.toggled.connect(lambda on: self.raster_requested.emit() if on else None)
            grid.addWidget(box, k // 2, k % 2)
            self._boxes[key] = box

        self.by_order = QCheckBox("按行驶顺序给条带着色")
        self.by_order.setToolTip(
            "默认所有作业条带同色，这样「绿色 = 正在割草」始终成立。\n"
            "按顺序着色便于检查路径，但会牺牲这条约定。"
        )
        grid.addWidget(self.by_order, (len(Layer.LABELS) + 1) // 2, 0, 1, 2)
        self.setStyleSheet(f"QGroupBox {{ color: {_theme.BOUNDARY.name()}; }}")

    def active(self) -> set[str]:
        return {k for k, box in self._boxes.items() if box.isChecked()}

    def is_checked(self, key: str) -> bool:
        box = self._boxes.get(key)
        return bool(box is not None and box.isChecked())

    def set_checked(self, key: str, on: bool) -> None:
        box = self._boxes.get(key)
        if box is not None:
            box.setChecked(bool(on))

    def _emit(self) -> None:
        self.changed.emit(self.active())
