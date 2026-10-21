"""The planning tab: pick a field, set the parameters, see the plan and its cost.

Laid out as a control column on the left and the canvas on the right, with the
metric read-out along the bottom.  Planning runs on the worker pool, so the
window stays live while a large field is being solved.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..metrics import coverage_grid, evaluate, swept_geometry
from ..planner import PlanParams, plan
from . import theme
from .field_view import FieldView, Layer
from .panels import LayerPanel, MetricGrid, TimingBar
from .sources import FieldSourcePanel
from .worker import run_async

__all__ = ["PlanTab"]

ROUTES = [
    ("optimised", "优化（贪心 + 2-opt + Or-opt）"),
    ("boustrophedon", "牛耕（经典基线）"),
    ("greedy", "仅贪心"),
]

#: On when the tab opens.  The raster answers "where did it cut?", which is the
#: first question anyone asks of a coverage plan, so it starts visible even
#: though it sits on top of the strokes.
DEFAULT_LAYERS = set(Layer.DEFAULT) | {Layer.COVERAGE}


class PlanTab(QWidget):
    """Single-shot planning: one field, one parameter set, one plan."""

    status = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._field = None
        self._plan = None
        self._grid = None
        self._busy = False

        # --- controls ---------------------------------------------------
        self.source = FieldSourcePanel()
        self.source.field_changed.connect(self._on_field)

        params = QGroupBox("规划参数")
        form = QFormLayout(params)
        self.swath_width = self._spin(0.5, 40.0, 6.0, " m", 2)
        self.headland_width = self._spin(0.0, 40.0, 6.0, " m", 2)
        self.turn_radius = self._spin(0.0, 30.0, 0.0, " m", 2)
        self.turn_radius.setToolTip(
            "0 表示用直线连接条带（忽略曲率）；\n"
            "大于 0 时用 Dubins 曲线连接，与 Fields2Cover 的对比需要设为 2.0。"
        )
        self.route = QComboBox()
        for value, label in ROUTES:
            self.route.addItem(label, value)
        self.angle_candidates = self._spin(0, 180, 24, " 个", 0)
        self.angle_candidates.setToolTip("作业角搜索的候选数量；0 表示固定为 0°，跳过搜索。")
        self.min_swath = self._spin(0.0, 200.0, 1.5, " m", 2)
        self.min_swath.setToolTip("短于该长度的条带会被丢弃：一次地头转弯换不来这点覆盖。")

        form.addRow("作业幅宽", self.swath_width)
        form.addRow("地头宽度", self.headland_width)
        form.addRow("最小转弯半径", self.turn_radius)
        form.addRow("排序策略", self.route)
        form.addRow("作业角候选数", self.angle_candidates)
        form.addRow("最短条带", self.min_swath)

        raster = QGroupBox("覆盖栅格")
        rform = QFormLayout(raster)
        self.cell_size = self._spin(0.25, 20.0, 3.0, " m", 2)
        self.cell_size.setToolTip(
            "栅格单元边长。默认取作业幅宽的一半 —— 这是还能分辨出\n"
            "「相邻两条作业带之间是否有缝」的最粗尺度。单元越小越精确，也越慢。"
        )
        self.cell_size.valueChanged.connect(self._recompute_grid)
        self.cell_note = QLabel("")
        self.cell_note.setWordWrap(True)
        self.cell_note.setStyleSheet(f"color:{theme.MUTED}; font-size:11px;")
        rform.addRow("单元边长", self.cell_size)
        rform.addRow(self.cell_note)

        self.layers_panel = LayerPanel(DEFAULT_LAYERS)
        self.layers_panel.changed.connect(self._on_layers_changed)
        self.layers_panel.raster_requested.connect(self._on_coverage_toggled)
        self.layers_panel.by_order.toggled.connect(self.view_set_swath_order)

        self.run_button = QPushButton("规划")
        self.run_button.setMinimumHeight(30)
        self.run_button.clicked.connect(self.run_plan)
        self.fit_button = QPushButton("适应窗口")
        self.fit_button.clicked.connect(lambda: self.view.fit())

        # --- read-out ---------------------------------------------------
        self.metrics = MetricGrid("规划结果")
        self.timings = TimingBar()
        timing_box = QGroupBox("各阶段耗时")
        tbox = QVBoxLayout(timing_box)
        tbox.addWidget(self.timings)

        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.message.setStyleSheet(f"color:{theme.MUTED}; font-size:11px;")

        # --- assembly ---------------------------------------------------
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(8)
        lv.addWidget(self.source)
        lv.addWidget(params)
        lv.addWidget(raster)
        lv.addWidget(self.layers_panel)
        row = QHBoxLayout()
        row.addWidget(self.run_button, 2)
        row.addWidget(self.fit_button, 1)
        lv.addLayout(row)
        lv.addWidget(self.message)
        lv.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidget(left)
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(320)
        scroll.setMaximumWidth(430)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        self.view = FieldView()
        self.view.hovered.connect(self._on_hover)

        bottom = QWidget()
        bl = QHBoxLayout(bottom)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.addWidget(self.metrics, 3)
        bl.addWidget(timing_box, 2)
        bottom.setMaximumHeight(390)

        right = QSplitter(Qt.Orientation.Vertical)
        right.addWidget(self.view)
        right.addWidget(bottom)
        right.setStretchFactor(0, 5)
        right.setStretchFactor(1, 3)
        right.setSizes([500, 360])

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(scroll)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([360, 900])

        outer = QHBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.addWidget(splitter)

        self._on_layers_changed(self.layers_panel.active())
        self._show_empty_metrics()
        self.source.rebuild()

    # ------------------------------------------------------------------
    @staticmethod
    def _spin(lo: float, hi: float, value: float, suffix: str, decimals: int) -> QDoubleSpinBox:
        box = QDoubleSpinBox()
        box.setRange(lo, hi)
        box.setValue(value)
        box.setSuffix(suffix)
        box.setDecimals(decimals)
        box.setSingleStep(0.5 if decimals else 1.0)
        return box

    def _on_layers_changed(self, active: set) -> None:
        self.view.layers = set(active)
        self.view.update()

    def view_set_swath_order(self, enabled: bool) -> None:
        self.view.set_swath_colour_by_order(enabled)

    def _on_coverage_toggled(self, on: bool) -> None:
        """Build the raster the first time it is asked for, then keep it."""
        if on and self._grid is None and self._plan is not None:
            self._recompute_grid()

    def _on_hover(self, x: float, y: float, what: str) -> None:
        self.status.emit(f"x {x:.2f}  y {y:.2f}   {what}")

    def _show_empty_metrics(self) -> None:
        self.metrics.clear()
        for key, label in [
            ("coverage", "覆盖率"),
            ("overlap", "重叠率"),
            ("path", "总里程"),
            ("turns", "转弯次数"),
            ("time", "规划耗时"),
        ]:
            self.metrics.add(key, label, "—")
        self.timings.set_timings({})
        self.cell_note.setText("")

    def _on_field(self, field) -> None:  # noqa: ANN001 - cppclip Field
        self._field = field
        self._plan = None
        self._grid = None
        self.view.set_scene(field=field, plan=None, affected=(), autofit=True)
        self.view.fit()
        self._show_empty_metrics()
        self.message.setText("点击「规划」开始。")

    def params(self) -> PlanParams:
        candidates = int(self.angle_candidates.value())
        return PlanParams(
            swath_width=self.swath_width.value(),
            headland_width=self.headland_width.value(),
            turn_radius=self.turn_radius.value(),
            route=self.route.currentData(),
            n_angle_candidates=max(1, candidates),
            angle=0.0 if candidates == 0 else None,
            min_swath_length=self.min_swath.value(),
        )

    # ------------------------------------------------------------------
    def run_plan(self) -> None:
        if self._busy or self._field is None:
            return
        params = self.params()
        field = self._field
        want_raster = self.layers_panel.is_checked(Layer.COVERAGE)
        cell = self.cell_size.value()
        self._busy = True
        self.run_button.setEnabled(False)
        self.run_button.setText("规划中…")
        self.message.setText(f"正在规划 {field.name} …")
        run_async(
            self._solve, self._on_planned, self._on_failed, field, params, want_raster, cell
        )

    @staticmethod
    def _solve(field, params, want_raster: bool, cell: float):  # noqa: ANN001 - worker payload
        """Run on the pool thread: planning, its metrics, and the raster.

        The swept union is built once and handed to both the scalar coverage and
        the raster.  Rebuilding it would roughly double the cost and, worse, give
        the picture and the number two chances to disagree.
        """
        result = plan(field, params)
        metrics = evaluate(field, result)
        grid = None
        if want_raster:
            grid = coverage_grid(
                field, result, cell=cell, swept=swept_geometry(result)
            )
        return field, params, result, metrics, grid

    def _on_planned(self, payload) -> None:  # noqa: ANN001 - worker payload
        field, params, result, metrics, grid = payload
        self._plan = result
        self._grid = grid
        self._busy = False
        self.run_button.setEnabled(True)
        self.run_button.setText("规划")

        self.view.set_scene(field=field, plan=result, grid=grid, affected=(), autofit=False)
        self.view.fit()

        cov = metrics.coverage
        self.metrics.clear()
        self.metrics.add(
            "coverage", "覆盖率", f"{cov:.4f}",
            colour=theme.POSITIVE if cov >= 0.99 else None, bold=True,
        )
        self.metrics.add("missed", "未覆盖", f"{metrics.missed:.4f}")
        self.metrics.add("overlap", "重叠率", f"{metrics.overlap:.4f}")
        self.metrics.add("spillage", "外溢率", f"{metrics.spillage:.4f}")
        self.metrics.add("path", "总里程", f"{metrics.path_length:,.0f} m", bold=True)
        self.metrics.add("working", "作业里程", f"{metrics.working_length:,.0f} m")
        self.metrics.add("transit", "空走里程", f"{metrics.transit_length:,.0f} m")
        self.metrics.add(
            "nonworking", "空走率", f"{100 * metrics.non_working_ratio:.1f} %",
            colour=theme.NEGATIVE if metrics.non_working_ratio > 0.2 else None,
        )
        self.metrics.add("strokes", "作业条带数", f"{metrics.n_strokes}")
        self.metrics.add("turns", "转弯次数", f"{metrics.n_turns}")
        self.metrics.add("angle", "作业角", f"{metrics.angle_deg:.1f}°")
        self.metrics.add("time", "规划耗时", f"{1000 * metrics.plan_time:.1f} ms", bold=True)

        self.timings.set_timings(result.timings)
        self._describe_grid(grid)
        self.message.setText(
            f"{field.name} · 幅宽 {params.swath_width:g} m · "
            f"地头 {params.headland_width:g} m · "
            f"转弯半径 {'直线' if params.turn_radius <= 0 else f'{params.turn_radius:g} m'} · "
            f"策略 {params.route} · 地头环 {len(result.headland_loops)} 个"
        )
        self.status.emit(
            f"规划完成：覆盖率 {cov:.4f}，里程 {metrics.path_length:,.0f} m，"
            f"耗时 {1000 * metrics.plan_time:.0f} ms"
        )

    def _describe_grid(self, grid) -> None:  # noqa: ANN001
        """State the raster's own error rather than implying it is exact."""
        if grid is None:
            self.cell_note.setText("（未计算覆盖栅格）")
            return
        self.cell_note.setText(
            f"{grid.nx} × {grid.ny} 单元 @ {grid.cell:g} m\n"
            f"栅格估计 {grid.coverage:.4f} / 精确 {grid.exact_coverage:.4f}"
            f"（差 {100 * grid.difference:+.3f} pp）\n"
            f"{int(grid.free.sum())} 个自由单元中 {int(grid.missed.sum())} 个漏割"
            f"（约 {grid.missed_area():,.0f} m²）"
        )

    def _recompute_grid(self) -> None:
        """Rebuild the raster for the current plan, without replanning."""
        if self._plan is None or self._field is None or self._busy:
            return
        try:
            self._grid = coverage_grid(
                self._field,
                self._plan,
                cell=self.cell_size.value(),
                swept=swept_geometry(self._plan),
            )
        except Exception as exc:  # noqa: BLE001 - report, never crash the window
            self.message.setText(f"覆盖栅格计算失败：{exc}")
            return
        self.view.set_scene(field=self._field, plan=self._plan, grid=self._grid, autofit=False)
        self._describe_grid(self._grid)

    def _on_failed(self, trace: str) -> None:
        self._busy = False
        self.run_button.setEnabled(True)
        self.run_button.setText("规划")
        last = trace.strip().splitlines()[-1] if trace.strip() else "未知错误"
        self.message.setText(f"规划失败：{last}")
        self.status.emit(f"规划失败：{last}")
