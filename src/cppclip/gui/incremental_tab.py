"""The incremental-replanning tab: the paper's headline experiment, made clickable.

Click anywhere inside the field and an obstacle appears there.  The planner then
does what the incremental algorithm does -- re-clip only the scanlines that
obstacle spans, keep every surviving stroke in place, repair the tour locally --
and the tab reports, side by side and measured live:

* how many of the scanlines had to be recomputed, and which ones (shaded orange),
* how long the incremental update took,
* how long solving the *same* scene from scratch takes,
* and the ratio between them.

That ratio is the whole contribution, so it is shown as a running log rather than
a single number: one lucky change proves nothing, twenty of them do.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
import numpy as np
from shapely.geometry import Point

from .. import geometry as G
from ..incremental import IncrementalPlanner
from ..metrics import coverage_grid, evaluate, swept_geometry
from ..planner import PlanParams, plan
from . import theme
from .field_view import FieldView, Layer
from .panels import LayerPanel, MetricGrid
from .sources import FieldSourcePanel
from .worker import run_async

__all__ = ["IncrementalTab"]

OBSTACLE_SHAPES = [("圆形", "circle"), ("方形", "square")]

COLUMNS = ["#", "操作", "模式", "失效扫描线", "增量 ms", "全量 ms", "加速"]

#: Same defaults as the planning tab, except the raster starts off: on this tab
#: the orange re-clip bands are the thing being shown, and a full-field green
#: wash underneath competes for the same pixels.
DEFAULT_LAYERS = set(Layer.DEFAULT)


class IncrementalTab(QWidget):
    """Interactive demonstration of dynamic incremental replanning."""

    status = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._field = None
        self._planner: IncrementalPlanner | None = None
        self._plan = None
        self._busy = False
        self._changes: list[dict] = []
        self._last_obstacle = None
        self._pending_field = None

        # --- controls ---------------------------------------------------
        self.source = FieldSourcePanel()
        self.source.field_changed.connect(self._on_field)

        setup = QGroupBox("重规划参数")
        sform = QFormLayout(setup)
        self.swath_width = self._spin(1.0, 40.0, 6.0)
        self.headland_width = self._spin(0.0, 40.0, 6.0)
        self.global_fraction = self._spin(0.0, 5.0, 0.5)
        self.global_fraction.setSingleStep(0.05)
        self.global_fraction.setToolTip(
            "插入条带数超过路径规模的这个比例时改为全局重解。\n"
            "消融实验给出的最优点是 0.5：1% 的变更触发全局重解，加速 1.37x。"
        )
        self.repair_window = self._spin(0.0, 40.0, 4.0)
        self.repair_window.setToolTip("扰动附近的 2-opt/Or-opt 窗口；实测 4 是速度与质量的最优点。")
        self.compare_full = QComboBox()
        self.compare_full.addItems(["对照：全量重算（冻结作业角）", "对照：全量重算（含作业角搜索）"])

        sform.addRow("作业幅宽", self.swath_width)
        sform.addRow("地头宽度", self.headland_width)
        sform.addRow("全局重解阈值", self.global_fraction)
        sform.addRow("局部修复窗口", self.repair_window)
        sform.addRow("对照方式", self.compare_full)

        place = QGroupBox("放置障碍（在画布上点击）")
        pform = QFormLayout(place)
        self.shape = QComboBox()
        for value, label in OBSTACLE_SHAPES:
            self.shape.addItem(label, value)
        self.size = self._spin(2.0, 120.0, 16.0)
        self.size.setToolTip("障碍的直径（米）。固定尺寸才能看出失效占比随田地变大而下降。")
        pform.addRow("形状", self.shape)
        pform.addRow("直径", self.size)

        self.undo_button = QPushButton("移除最后一个")
        self.clear_button = QPushButton("清空全部新增")
        self.fit_button = QPushButton("适应窗口")
        self.undo_button.clicked.connect(self._undo)
        self.clear_button.clicked.connect(self._clear)
        self.fit_button.clicked.connect(lambda: self.view.fit())
        for b in (self.undo_button, self.clear_button):
            b.setEnabled(False)

        self.summary = MetricGrid("本次累计")
        self.report = MetricGrid("最近一次变更")
        self.message = QLabel("点击画布放置障碍；橙色带表示本次被重新裁剪的扫描线。")
        self.message.setWordWrap(True)
        self.message.setStyleSheet(f"color:{theme.MUTED}; font-size:11px;")

        self.layers_panel = LayerPanel(DEFAULT_LAYERS)
        self.layers_panel.changed.connect(self._on_layers_changed)
        self.layers_panel.raster_requested.connect(self._refresh_view)
        self.layers_panel.by_order.toggled.connect(self.view_set_swath_order)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setMinimumHeight(160)

        # --- assembly ---------------------------------------------------
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(8)
        lv.addWidget(self.source)
        lv.addWidget(setup)
        lv.addWidget(place)
        row = QHBoxLayout()
        row.addWidget(self.undo_button)
        row.addWidget(self.clear_button)
        lv.addLayout(row)
        lv.addWidget(self.layers_panel)
        lv.addWidget(self.message)
        lv.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidget(left)
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(320)
        scroll.setMaximumWidth(410)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        self.view = FieldView()
        self.view.clicked_world.connect(self._on_click)
        self.view.hovered.connect(self._on_hover)
        self.view.setToolTip("左键点击放置障碍 · 拖动平移 · 滚轮缩放 · 双击适应窗口")

        top = QWidget()
        tl = QVBoxLayout(top)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.addWidget(self.fit_button)
        tl.addWidget(self.view, 1)

        # The read-outs and the log sit under the canvas rather than in the
        # control column: the timing comparison is the point of this tab, and it
        # is worthless if the reader has to scroll to find it.
        readouts = QWidget()
        rl = QHBoxLayout(readouts)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(self.report, 3)
        rl.addWidget(self.summary, 2)

        bottom = QWidget()
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.addWidget(readouts)
        bl.addWidget(QLabel("变更日志（增量与全量在同一进程内背靠背计时）"))
        bl.addWidget(self.table, 1)

        right = QSplitter(Qt.Orientation.Vertical)
        right.addWidget(top)
        right.addWidget(bottom)
        right.setStretchFactor(0, 5)
        right.setStretchFactor(1, 4)
        right.setSizes([470, 360])

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(scroll)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([350, 880])

        outer = QHBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.addWidget(splitter)

        self.source.rebuild()

    # ------------------------------------------------------------------
    @staticmethod
    def _spin(lo: float, hi: float, value: float) -> QDoubleSpinBox:
        box = QDoubleSpinBox()
        box.setRange(lo, hi)
        box.setValue(value)
        box.setDecimals(2)
        box.setSingleStep(0.5)
        return box

    def _params(self, angle: float | None = None) -> PlanParams:
        return PlanParams(
            swath_width=self.swath_width.value(),
            headland_width=self.headland_width.value(),
            angle=angle,
            n_angle_candidates=24,
            route="optimised",
            min_swath_length=1.5,
        )

    def _on_field(self, field) -> None:  # noqa: ANN001 - cppclip Field
        if self._busy:
            # A build is already running.  Queue the request rather than dropping
            # it: silently ignoring the user's field selection leaves the window
            # showing a different field from the one they chose, which is worse
            # than a short delay.
            self._pending_field = field
            self.message.setText(f"已排队：{field.name}（当前构建完成后载入）")
            return
        self._start_build(field)

    def _start_build(self, field) -> None:  # noqa: ANN001 - cppclip Field
        self._pending_field = None
        self._field = field
        self._changes.clear()
        self._last_obstacle = None
        self.table.setRowCount(0)
        self.undo_button.setEnabled(False)
        self.clear_button.setEnabled(False)
        self._busy = True
        self.message.setText(f"正在为 {field.name} 建立增量规划器 …")
        run_async(
            self._build,
            self._on_built,
            self._on_failed,
            field,
            self._params(),
            self.global_fraction.value(),
            int(self.repair_window.value()),
        )

    def _drain_pending(self) -> None:
        """Start the queued field build, if the user asked for one mid-build."""
        pending = self._pending_field
        self._pending_field = None
        if pending is not None:
            self._start_build(pending)

    @staticmethod
    def _build(field, params, global_fraction, repair_window):  # noqa: ANN001 - worker payload
        """Construct the planner and solve the pristine scene.

        Both steps run on the pool: the constructor performs a 24-candidate
        heading search, which on a large field is a second of work, and a second
        of frozen window reads as a crash.
        """
        planner = IncrementalPlanner(
            field,
            params,
            global_repair_fraction=global_fraction,
            repair_window=repair_window,
        )
        frozen = PlanParams(
            swath_width=params.swath_width,
            headland_width=params.headland_width,
            route=params.route,
            min_swath_length=params.min_swath_length,
            n_angle_candidates=params.n_angle_candidates,
            angle=planner.angle,
        )
        return field, planner, plan(field, frozen)

    def _on_built(self, payload) -> None:  # noqa: ANN001 - worker payload
        field, planner, result = payload
        self._planner = planner
        self._plan = result
        self._busy = False
        self._refresh_view()
        self._reset_readouts()
        self.view.fit()
        self.message.setText(
            f"{field.name} · 作业角 {np.degrees(planner.angle):.1f}°（整个会话期间冻结）"
            f" · {planner.clipper.n_scanlines} 条扫描线 · 点击画布放置障碍"
        )
        self.status.emit(f"增量规划器就绪：{field.name}，{planner.clipper.n_scanlines} 条扫描线")
        self._drain_pending()

    def _reset_readouts(self) -> None:
        self.report.clear()
        for key, label in [
            ("affected", "失效扫描线"),
            ("mode", "模式"),
            ("inc", "增量耗时"),
            ("full", "全量耗时"),
            ("speed", "加速比"),
            ("cov", "覆盖率（增量 / 全量）"),
        ]:
            self.report.add(key, label, "—")
        self.summary.clear()
        for key, label in [
            ("n", "变更次数"),
            ("inc", "增量合计"),
            ("full", "全量合计"),
            ("speed", "累计加速"),
        ]:
            self.summary.add(key, label, "—")

    # ------------------------------------------------------------------
    def _on_click(self, wx: float, wy: float) -> None:
        if self._busy or self._planner is None or self._field is None:
            return
        half = self.size.value() / 2.0
        if self.shape.currentData() == "circle":
            obstacle = G.normalise(Point(wx, wy).buffer(half, quad_segs=24))
        else:
            from shapely.geometry import box

            obstacle = G.normalise(box(wx - half, wy - half, wx + half, wy + half))

        if not self._field.boundary.contains(obstacle):
            self.message.setText("障碍必须完全落在田地内部，请换个位置点击。")
            return

        self._busy = True
        self.message.setText("正在增量重算，并与全量重算对比 …")
        run_async(
            self._apply_change,
            self._on_changed,
            self._on_failed,
            self._planner,
            obstacle,
            self.compare_full.currentIndex() == 1,
            self._params(),
        )

    @staticmethod
    def _apply_change(planner, obstacle, compare_with_heading, base_params):
        """Worker: one incremental update, then the same scene solved from scratch.

        Both timings are measured here, in the same process, back to back, so the
        ratio the tab displays is a like-for-like wall-clock comparison rather
        than two numbers from different runs.

        The handle is deliberately *not* chosen by the caller.
        ``IncrementalPlanner`` already numbers the field's own obstacles, and a
        caller starting its own counter at zero hands it a handle that is already
        taken -- which **overwrites** the first built-in obstacle instead of
        adding a new one.  The scene then keeps its original obstacle count while
        the canvas shows a new obstacle and the log claims one was placed.
        """
        import time

        t0 = time.perf_counter()
        handle, report = planner.add_obstacle(obstacle)
        t_inc = time.perf_counter() - t0

        scene = planner.current_field()
        fixed = PlanParams(
            swath_width=base_params.swath_width,
            headland_width=base_params.headland_width,
            route=base_params.route,
            min_swath_length=base_params.min_swath_length,
            n_angle_candidates=base_params.n_angle_candidates,
            angle=None if compare_with_heading else planner.angle,
        )
        t0 = time.perf_counter()
        full = plan(scene, fixed)
        t_full = time.perf_counter() - t0

        inc_plan = planner.to_plan()
        return {
            "handle": handle,
            "report": report,
            "t_inc": t_inc,
            "t_full": t_full,
            "m_inc": evaluate(scene, inc_plan),
            "m_full": evaluate(scene, full),
            "scene": scene,
            "inc_plan": inc_plan,
        }

    def _on_changed(self, payload) -> None:  # noqa: ANN001 - worker payload
        self._busy = False
        self._last_obstacle = payload["handle"]
        self._changes.append(payload)
        self.undo_button.setEnabled(True)
        self.clear_button.setEnabled(True)

        rep = payload["report"]
        t_inc = payload["t_inc"]
        t_full = payload["t_full"]
        speed = t_full / t_inc if t_inc > 0 else float("nan")
        m_inc, m_full = payload["m_inc"], payload["m_full"]

        self._plan = payload["inc_plan"]
        self._refresh_view(affected=rep.affected_lines)

        self.report.clear()
        self.report.add("affected", "失效扫描线",
                        f"{rep.n_affected_scanlines} / {rep.n_total_scanlines}"
                        f"  ({100 * rep.work_fraction:.1f}%)", bold=True)
        self.report.add("mode", "模式",
                        {"incremental": "增量", "group_merge": "分组合并"}.get(rep.mode, rep.mode))
        self.report.add("repair", "路径修复", "局部" if rep.route_repair == "local" else "全局重解",
                        colour=theme.NEGATIVE if rep.route_repair == "global" else theme.POSITIVE)
        self.report.add("inc", "增量耗时", f"{1000 * t_inc:.1f} ms", bold=True)
        self.report.add("full", "全量耗时", f"{1000 * t_full:.1f} ms")
        self.report.add("speed", "加速比", f"{speed:.2f}x",
                        colour=theme.POSITIVE if speed > 1 else theme.NEGATIVE, bold=True)
        self.report.add("cov", "覆盖率 增/全", f"{m_inc.coverage:.4f} / {m_full.coverage:.4f}")
        self.report.add("path", "里程 增/全", f"{m_inc.path_length:,.0f} / {m_full.path_length:,.0f} m")

        inc_total = sum(c["t_inc"] for c in self._changes)
        full_total = sum(c["t_full"] for c in self._changes)
        self.summary.clear()
        self.summary.add("n", "变更次数", str(len(self._changes)))
        self.summary.add("inc", "增量合计", f"{1000 * inc_total:,.0f} ms")
        self.summary.add("full", "全量合计", f"{1000 * full_total:,.0f} ms")
        self.summary.add("speed", "累计加速",
                         f"{full_total / inc_total:.2f}x" if inc_total else "—",
                         colour=theme.POSITIVE, bold=True)

        self._append_row(payload, speed)
        self.message.setText(
            f"第 {len(self._changes)} 次变更：只重算了 {rep.n_affected_scanlines} 条扫描线"
            f"（全场 {rep.n_total_scanlines} 条）。"
        )
        self.status.emit(
            f"增量 {1000 * t_inc:.0f} ms vs 全量 {1000 * t_full:.0f} ms → {speed:.2f}x"
        )

    def _append_row(self, payload, speed: float) -> None:  # noqa: ANN001
        rep = payload["report"]
        row = self.table.rowCount()
        self.table.insertRow(row)
        cells = [
            str(row + 1),
            "移除" if payload.get("removed") else "新增",
            {"incremental": "增量", "group_merge": "分组合并"}.get(rep.mode, rep.mode),
            f"{rep.n_affected_scanlines}/{rep.n_total_scanlines}",
            f"{1000 * payload['t_inc']:.1f}",
            f"{1000 * payload['t_full']:.1f}",
            f"{speed:.2f}x" if speed == speed else "—",
        ]
        for col, text in enumerate(cells):
            item = QTableWidgetItem(text)
            if col >= 4:
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, col, item)
        self.table.scrollToBottom()

    def _refresh_view(self, affected: tuple[int, ...] = ()) -> None:
        """Redraw, rebuilding the coverage raster when that layer is on.

        The raster is rebuilt here rather than cached because every change *is* a
        change to the swept area; a stale raster would show the coverage the plan
        had before the obstacle appeared, which is the one thing this tab exists
        to demonstrate.
        """
        if self._planner is None:
            return
        scene = self._planner.current_field()
        grid = None
        if self._plan is not None and self.layers_panel.is_checked(Layer.COVERAGE):
            try:
                grid = coverage_grid(
                    scene, self._plan, swept=swept_geometry(self._plan)
                )
            except Exception:  # noqa: BLE001 - a raster must not break the demo
                grid = None
        self.view.set_scene(
            field=scene,
            plan=self._plan,
            clipper=self._planner.clipper,
            grid=grid,
            affected=affected,
            pending_obstacles=[],
            autofit=False,
        )

    def _on_layers_changed(self, active: set) -> None:
        self.view.layers = set(active)
        self.view.update()

    def view_set_swath_order(self, enabled: bool) -> None:
        self.view.set_swath_colour_by_order(enabled)

    def _on_hover(self, x: float, y: float, what: str) -> None:
        self.status.emit(f"x {x:.2f}  y {y:.2f}   {what}")

    # ------------------------------------------------------------------
    def _undo(self) -> None:
        if self._busy or self._planner is None or not self._changes:
            return
        handle = self._changes[-1]["handle"]
        self._busy = True
        self.message.setText("正在移除最后一个障碍 …")
        run_async(self._remove, self._on_removed, self._on_failed, self._planner, handle)

    @staticmethod
    def _remove(planner, handle):  # noqa: ANN001 - worker payload
        import time

        t0 = time.perf_counter()
        report = planner.remove_obstacle(handle)
        elapsed = time.perf_counter() - t0
        return {"handle": handle, "report": report, "t_inc": elapsed, "removed": True}

    def _on_removed(self, payload) -> None:  # noqa: ANN001 - worker payload
        self._busy = False
        self._changes = [c for c in self._changes if c["handle"] != payload["handle"]]
        self._last_obstacle = self._changes[-1]["handle"] if self._changes else None
        self.undo_button.setEnabled(bool(self._changes))
        self.clear_button.setEnabled(bool(self._changes))
        self._plan = self._planner.to_plan()
        self._refresh_view(affected=payload["report"].affected_lines)
        self.message.setText(
            f"已移除障碍：失效 {payload['report'].n_affected_scanlines} 条扫描线，"
            f"耗时 {1000 * payload['t_inc']:.1f} ms"
        )
        self.status.emit("已移除最后一个障碍")

    def _clear(self) -> None:
        if self._busy or self._planner is None or not self._changes:
            return
        if QMessageBox.question(
            self, "确认", f"移除全部 {len(self._changes)} 个新增障碍？"
        ) != QMessageBox.StandardButton.Yes:
            return
        self._busy = True
        self.message.setText("正在清空 …")
        run_async(self._clear_all, self._on_cleared, self._on_failed, self._planner)

    @staticmethod
    def _clear_all(planner):  # noqa: ANN001 - worker payload
        import time

        t0 = time.perf_counter()
        handles = list(planner._handle_group)
        for h in handles:
            planner.remove_obstacle(h)
        return time.perf_counter() - t0

    def _on_cleared(self, elapsed: float) -> None:  # noqa: ANN001 - worker payload
        self._busy = False
        self._changes.clear()
        self.table.setRowCount(0)
        self.undo_button.setEnabled(False)
        self.clear_button.setEnabled(False)
        self._plan = self._planner.to_plan()
        self._refresh_view()
        self._reset_readouts()
        self.message.setText(f"已清空全部新增障碍，耗时 {1000 * elapsed:.1f} ms。")

    def _on_failed(self, trace: str) -> None:
        self._busy = False
        last = trace.strip().splitlines()[-1] if trace.strip() else "未知错误"
        self.message.setText(f"失败：{last}")
        self.status.emit(f"失败：{last}")
        self._drain_pending()
