"""Results browser: the experiment charts and the raw tables behind them.

The charts are re-drawn from ``results/tables/*.csv`` rather than loaded as
images, so what the window shows is by construction what the report is built on.
Below each chart sits the table itself, because a chart is an argument and the
table is the evidence.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
import pandas as pd
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .charts import CHARTS, draw_chart

matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

__all__ = ["ResultsTab"]

ROOT = Path(__file__).resolve().parents[3]
TABLES = ROOT / "results" / "tables"
FIGURES = ROOT / "results" / "figures"


class TableModel(QAbstractTableModel):
    """A thin read-only view over a DataFrame.

    A model rather than a populated ``QTableWidget`` because ``exp4_compare``
    has 700 rows across 21 columns; filling widgets for that is slow and wasteful
    when only a screenful is ever visible.
    """

    def __init__(self, df: pd.DataFrame | None = None) -> None:
        super().__init__()
        self._df = df if df is not None else pd.DataFrame()

    def set_frame(self, df: pd.DataFrame) -> None:
        self.beginResetModel()
        self._df = df
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: ANN001, B008
        return 0 if parent.isValid() else len(self._df)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: ANN001, B008
        return 0 if parent.isValid() else len(self._df.columns)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):  # noqa: ANN201
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        value = self._df.iat[index.row(), index.column()]
        if isinstance(value, float):
            if value != value:  # NaN
                return "—"
            return f"{value:,.4g}"
        return str(value)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):  # noqa: ANN201
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return str(self._df.columns[section])
        return str(section + 1)


class ResultsTab(QWidget):
    """Browse the measured results: chart on top, the table underneath."""

    status = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tables: dict[str, pd.DataFrame] = {}

        self.chooser = QComboBox()
        for key, (_file, title, _fn, _extra) in CHARTS.items():
            self.chooser.addItem(title, key)
        self.reload_button = QPushButton("重新载入结果表")
        self.reload_button.clicked.connect(self.reload)
        self.save_button = QPushButton("保存当前图表…")
        self.save_button.clicked.connect(self._save_current)

        self.hint = QLabel("")
        self.hint.setStyleSheet(f"color:{theme.MUTED}; font-size:11px;")
        self.hint.setWordWrap(True)

        top = QHBoxLayout()
        top.addWidget(QLabel("图表"))
        top.addWidget(self.chooser, 1)
        top.addWidget(self.reload_button)
        top.addWidget(self.save_button)

        self.figure = Figure(figsize=(11, 4.2), dpi=100)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setMinimumHeight(300)

        self.model = TableModel()
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.setSortingEnabled(False)

        splitter = QSplitter(Qt.Orientation.Vertical)
        canvas_holder = QWidget()
        ch = QVBoxLayout(canvas_holder)
        ch.setContentsMargins(0, 0, 0, 0)
        ch.addLayout(top)
        ch.addWidget(self.canvas, 1)
        ch.addWidget(self.hint)
        splitter.addWidget(canvas_holder)
        splitter.addWidget(self.table)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(splitter)

        self.chooser.currentIndexChanged.connect(self._redraw)
        self.reload()

    # ------------------------------------------------------------------
    def reload(self) -> None:
        """Read every result table that exists; report the ones that do not."""
        self._tables.clear()
        missing: list[str] = []
        wanted = {f for f, _t, _fn, _e in CHARTS.values()} | {
            e for _f, _t, _fn, e in CHARTS.values() if e
        }
        wanted |= {"exp1_clipping"}
        for name in sorted(wanted):
            path = TABLES / f"{name}.csv"
            if path.exists():
                try:
                    self._tables[name] = pd.read_csv(path)
                except Exception:  # noqa: BLE001 - a bad file must not kill the tab
                    missing.append(f"{name}（读取失败）")
            else:
                missing.append(name)
        if missing:
            self.hint.setText(
                "缺少结果表：" + "、".join(missing)
                + "。运行 experiments/run_all.py 生成（或先跑单个实验脚本）。"
            )
        else:
            self.hint.setText(
                f"已载入 {len(self._tables)} 张结果表，来自 {TABLES}。"
                "图表由这些 CSV 实时重绘，因此与报告所用的数据必然一致。"
            )
        self._redraw()

    def _redraw(self) -> None:
        key = self.chooser.currentData()
        if not key:
            return
        try:
            draw_chart(key, self._tables, self.figure)
            self.canvas.draw_idle()
        except Exception as exc:  # noqa: BLE001 - show, do not crash
            self.figure.clear()
            ax = self.figure.subplots(1, 1)
            ax.text(0.5, 0.5, f"绘图失败：{exc}", ha="center", transform=ax.transAxes)
            ax.axis("off")
            self.canvas.draw_idle()

        _file, _title, _fn, _extra = CHARTS[key]
        df = self._tables.get(_file)
        self.model.set_frame(df if df is not None else pd.DataFrame())
        self.table.resizeColumnsToContents()
        self.status.emit(f"{_title}：{0 if df is None else len(df)} 行")

    def _save_current(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        key = self.chooser.currentData()
        title = CHARTS[key][1] if key in CHARTS else "chart"
        path, _ = QFileDialog.getSaveFileName(
            self, "保存图表", str(FIGURES / f"{key}.png"), "PNG 图片 (*.png)"
        )
        if path:
            self.figure.savefig(path, bbox_inches="tight", dpi=140)
            self.status.emit(f"已保存：{path}")
