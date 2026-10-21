"""The interactive canvas: world geometry in metres, screen in pixels.

A :class:`FieldView` owns a *scene* -- a field, optionally a plan, optionally the
coverage raster -- and draws it with ``QPainter``.  Everything is re-projected on
every repaint rather than cached in screen space: a field has tens of polygons
and a plan has tens of strokes, so the transform costs nothing measurable and
caching would be one more thing to invalidate correctly.

Drawing order is fixed and deliberate, back to front:

1. free-space fill, so the field is visibly a region and not just an outline;
2. the coverage raster, which belongs *under* the lines -- it answers "did this
   get cut?", and the lines answer "how?", so the how has to stay legible;
3. headland loops, transit legs, then working strokes, thickest last;
4. the optional full machine path over the top;
5. obstacles and the boundary outline, so the field's own edges are never
   obscured by what is inside it;
6. the re-clip highlight, scale bar, legend and hover readout.

The widget is deliberately usable on its own: :meth:`set_scene` takes plain
cppclip objects, and the class knows nothing about the rest of the GUI.
"""

from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import QSizePolicy, QWidget
from shapely import contains_xy

from .. import geometry as G
from ..fields import Field
from ..metrics import CoverageGrid
from ..planner import Plan
from ..sweep import ScanlineClipper
from . import theme

__all__ = ["FieldView", "Layer"]


class Layer:
    """Which overlays are drawn.  A plain namespace of string keys."""

    FREE = "free"
    COVERAGE = "coverage"
    BOUNDARY = "boundary"
    OBSTACLES = "obstacles"
    HEADLAND = "headland"
    SWATHS = "swaths"
    TRANSIT = "transit"
    MACHINE_PATH = "machine_path"
    INTERVALS = "intervals"
    AFFECTED = "affected"
    GRID = "grid"
    LEGEND = "legend"
    SCALE = "scale"

    ALL = (
        FREE, COVERAGE, BOUNDARY, OBSTACLES, HEADLAND, SWATHS, TRANSIT,
        MACHINE_PATH, INTERVALS, AFFECTED, GRID, LEGEND, SCALE,
    )
    #: What a fresh view shows: everything that was true of the field before the
    #: plan, plus the three line kinds that make up the plan.  The raster, the
    #: raw intervals and the full machine path are opt-in, because each of them
    #: obscures something the defaults keep visible.
    DEFAULT = (FREE, BOUNDARY, OBSTACLES, HEADLAND, SWATHS, TRANSIT, SCALE, LEGEND)

    #: Human labels, in the order the controls should present them.
    LABELS = [
        (BOUNDARY, "田地边界"),
        (FREE, "自由空间填充"),
        (OBSTACLES, "障碍物"),
        (HEADLAND, "地头线"),
        (SWATHS, "作业条带"),
        (TRANSIT, "空走段"),
        (MACHINE_PATH, "割草机路径"),
        (COVERAGE, "覆盖栅格"),
        (INTERVALS, "有效区间"),
        (AFFECTED, "本次重算扫描线"),
        (GRID, "米制网格"),
        (LEGEND, "图例"),
        (SCALE, "比例尺"),
    ]


class FieldView(QWidget):
    """Pan/zoom canvas for a coverage scene.

    Interaction
    -----------
    * left-drag pans, wheel zooms about the cursor, double-click fits the scene
    * a plain left-click (no drag) emits :attr:`clicked_world`, which the
      incremental tab uses to drop an obstacle
    * hovering emits :attr:`hovered` with the world point and what is there
    """

    clicked_world = Signal(float, float)
    hovered = Signal(float, float, str)
    view_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(420, 320)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._field: Field | None = None
        self._plan: Plan | None = None
        self._clipper: ScanlineClipper | None = None
        self._grid: CoverageGrid | None = None
        self._affected: tuple[int, ...] = ()
        self._pending_obstacles: list = []
        self.layers: set[str] = set(Layer.DEFAULT)

        self._scale = 1.0
        self._offset = QPointF(0.0, 0.0)  # world point at the widget's centre
        self._drag_from: QPointF | None = None
        self._drag_moved = False
        self._hover: tuple[float, float] | None = None
        self._fitted_once = False
        self._swath_by_order = False

    # ------------------------------------------------------------------
    # scene
    # ------------------------------------------------------------------
    def set_scene(
        self,
        field: Field | None = None,
        plan: Plan | None = None,
        clipper: ScanlineClipper | None = None,
        grid: CoverageGrid | None = None,
        affected: tuple[int, ...] = (),
        pending_obstacles: list | None = None,
        autofit: bool = True,
    ) -> None:
        self._field = field
        self._plan = plan
        self._clipper = clipper
        self._grid = grid
        self._affected = tuple(affected)
        self._pending_obstacles = list(pending_obstacles or [])
        if affected and Layer.AFFECTED not in self.layers:
            # Showing a re-clip highlight only makes sense if it is on screen;
            # the caller asked for it explicitly, so honour that rather than
            # silently dropping it because the layer was off.
            self.layers = self.layers | {Layer.AFFECTED}
        if autofit and field is not None and not self._fitted_once:
            self.fit()
        self.update()

    def set_swath_colour_by_order(self, enabled: bool) -> None:
        self._swath_by_order = bool(enabled)
        self.update()

    def fit(self) -> None:
        """Frame the current scene with a small margin."""
        box = self._scene_bounds()
        if box is None:
            return
        minx, miny, maxx, maxy = box
        w = max(maxx - minx, 1e-6)
        h = max(maxy - miny, 1e-6)
        sx = (self.width() - 40) / w
        sy = (self.height() - 40) / h
        self._scale = max(theme.MIN_SCALE, min(theme.MAX_SCALE, min(sx, sy)))
        self._offset = QPointF((minx + maxx) / 2.0, (miny + maxy) / 2.0)
        self._fitted_once = True
        self.view_changed.emit()
        self.update()

    def _scene_bounds(self) -> tuple[float, float, float, float] | None:
        boxes = []
        if self._field is not None:
            boxes.append(G.bounds_of(self._field.boundary))
        if self._plan is not None and self._plan.headland_loops:
            pts = [p for loop in self._plan.headland_loops for p in loop]
            if pts:
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                boxes.append((min(xs), min(ys), max(xs), max(ys)))
        for obs in self._pending_obstacles:
            boxes.append(G.bounds_of(obs))
        if not boxes:
            return None
        return (
            min(b[0] for b in boxes),
            min(b[1] for b in boxes),
            max(b[2] for b in boxes),
            max(b[3] for b in boxes),
        )

    # ------------------------------------------------------------------
    # transform
    # ------------------------------------------------------------------
    def world_to_screen(self, x: float, y: float) -> QPointF:
        cx, cy = self.width() / 2.0, self.height() / 2.0
        return QPointF(
            cx + (x - self._offset.x()) * self._scale,
            cy - (y - self._offset.y()) * self._scale,
        )

    def screen_to_world(self, px: float, py: float) -> tuple[float, float]:
        cx, cy = self.width() / 2.0, self.height() / 2.0
        return (
            self._offset.x() + (px - cx) / self._scale,
            self._offset.y() - (py - cy) / self._scale,
        )

    def metres_per_pixel(self) -> float:
        return 1.0 / self._scale if self._scale > 0 else math.inf

    # ------------------------------------------------------------------
    # interaction
    # ------------------------------------------------------------------
    def wheelEvent(self, event) -> None:  # noqa: ANN001 - Qt signature
        if self._field is None:
            return
        steps = event.angleDelta().y() / 120.0
        if not steps:
            return
        before = self.screen_to_world(event.position().x(), event.position().y())
        factor = 1.18 ** steps
        self._scale = max(theme.MIN_SCALE, min(theme.MAX_SCALE, self._scale * factor))
        after = self.screen_to_world(event.position().x(), event.position().y())
        # Keep the world point under the cursor pinned to the cursor.
        self._offset += QPointF(before[0] - after[0], before[1] - after[1])
        self.view_changed.emit()
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: ANN001 - Qt signature
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_from = event.position()
            self._drag_moved = False

    def mouseMoveEvent(self, event) -> None:  # noqa: ANN001 - Qt signature
        wx, wy = self.screen_to_world(event.position().x(), event.position().y())
        self._hover = (wx, wy)
        self.hovered.emit(wx, wy, self.describe_point(wx, wy))
        if self._drag_from is not None:
            delta = event.position() - self._drag_from
            if abs(delta.x()) + abs(delta.y()) > 3:
                self._drag_moved = True
            self._offset -= QPointF(delta.x() / self._scale, -delta.y() / self._scale)
            self._drag_from = event.position()
            self.view_changed.emit()
            self.update()
        else:
            self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: ANN001 - Qt signature
        if event.button() == Qt.MouseButton.LeftButton and self._drag_from is not None:
            if not self._drag_moved:
                wx, wy = self.screen_to_world(event.position().x(), event.position().y())
                self.clicked_world.emit(wx, wy)
            self._drag_from = None

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: ANN001 - Qt signature
        self.fit()

    def leaveEvent(self, event) -> None:  # noqa: ANN001 - Qt signature
        self._hover = None
        self.update()

    def describe_point(self, x: float, y: float) -> str:
        """What is at this world point, for the hover readout.

        Answers the question a raster always provokes -- "is *this* spot cut?" --
        without making the reader infer it from a colour.
        """
        if self._field is None:
            return ""
        try:
            if not bool(contains_xy(self._field.free, x, y)):
                return "障碍物 / 田外"
            grid = self._grid
            if grid is not None and Layer.COVERAGE in self.layers and grid.nx:
                i = int((x - grid.x_edges[0]) // grid.cell)
                j = int((y - grid.y_edges[0]) // grid.cell)
                if 0 <= i < grid.nx and 0 <= j < grid.ny:
                    return "已覆盖" if grid.covered[j, i] else "漏割"
            return "自由空间"
        except Exception:  # noqa: BLE001 - a hover readout must never throw
            return ""

    # ------------------------------------------------------------------
    # painting
    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: ANN001 - Qt signature
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.fillRect(self.rect(), theme.CANVAS_BG)

            if self._field is None:
                self._draw_placeholder(painter)
                return

            # 1. the field as a region
            if Layer.FREE in self.layers:
                self._fill_geometry(painter, self._field.free, theme.FREE_FILL)
            if Layer.GRID in self.layers:
                self._draw_metric_grid(painter)
            # 2. coverage, under everything else
            if Layer.COVERAGE in self.layers and self._grid is not None:
                self._draw_coverage(painter)
            if Layer.INTERVALS in self.layers and self._clipper is not None:
                self._draw_intervals(painter)
            # 3. the plan, thin lines first
            if Layer.HEADLAND in self.layers and self._plan is not None:
                self._draw_headland(painter)
            if Layer.TRANSIT in self.layers and self._plan is not None:
                self._draw_transit(painter)
            if Layer.SWATHS in self.layers and self._plan is not None:
                self._draw_swaths(painter)
            # 4. the full driven path, opt-in
            if Layer.MACHINE_PATH in self.layers and self._plan is not None:
                self._draw_machine_path(painter)
            # 5. the field's own edges, never obscured
            if Layer.OBSTACLES in self.layers:
                for obs in self._field.obstacles:
                    self._fill_geometry(painter, obs, theme.OBSTACLE)
            for obs in self._pending_obstacles:
                self._draw_outline(painter, obs, theme.NEW_OBSTACLE, width=2.0, dashed=True)
            if Layer.BOUNDARY in self.layers:
                self._draw_outline(
                    painter,
                    self._field.boundary,
                    theme.BOUNDARY,
                    width=theme.BOUNDARY_WIDTH,
                    style=theme.BOUNDARY_STYLE,
                )
            # 6. overlays
            if Layer.AFFECTED in self.layers and self._affected and self._clipper is not None:
                self._draw_affected(painter)
            if Layer.SCALE in self.layers:
                self._draw_scale_bar(painter)
            if Layer.LEGEND in self.layers:
                self._draw_legend(painter)
            self._draw_hover(painter)
        finally:
            # A painter that outlives its paintEvent corrupts the backing store
            # and leaves Qt emitting "endPaint() called with active painter"
            # forever after.  An exception above must not be allowed to do that.
            painter.end()

    def _draw_placeholder(self, painter: QPainter) -> None:
        painter.setPen(QPen(QColor(theme.MUTED)))
        font = QFont()
        font.setPointSize(11)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "选择一块田地并点击「规划」")

    # -- primitives -----------------------------------------------------
    def _polygon(self, ring) -> QPolygonF:  # noqa: ANN001
        return QPolygonF([self.world_to_screen(x, y) for x, y in ring])

    def _fill_geometry(self, painter: QPainter, geom, colour: QColor) -> None:  # noqa: ANN001
        path = QPainterPath()
        for poly in G.iter_polygons(geom):
            path.addPolygon(self._polygon(poly.exterior.coords))
            path.closeSubpath()
            for interior in poly.interiors:
                path.addPolygon(self._polygon(interior.coords))
                path.closeSubpath()
        path.setFillRule(Qt.FillRule.OddEvenFill)
        painter.fillPath(path, QBrush(colour))

    def _draw_outline(
        self,
        painter: QPainter,
        geom,  # noqa: ANN001
        colour: QColor,
        width: float = 1.4,
        dashed: bool = False,
        style: Qt.PenStyle | None = None,
    ) -> None:
        pen = QPen(colour, width)
        if style is not None:
            pen.setStyle(style)
        else:
            pen.setStyle(Qt.PenStyle.DashLine if dashed else Qt.PenStyle.SolidLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for poly in G.iter_polygons(geom):
            painter.drawPolygon(self._polygon(poly.exterior.coords))
            for interior in poly.interiors:
                painter.drawPolygon(self._polygon(interior.coords))

    def _draw_run(self, painter: QPainter, pts) -> None:  # noqa: ANN001
        if len(pts) >= 2:
            painter.drawPolyline(QPolygonF([self.world_to_screen(x, y) for x, y in pts]))

    # -- layers ---------------------------------------------------------
    def _draw_headland(self, painter: QPainter) -> None:
        """One polyline per loop.

        Never the loops concatenated: joining them draws a straight segment from
        the end of each loop to the start of the next, which the machine does not
        drive and which cuts through whatever lies between the two.
        """
        painter.setPen(
            theme.make_pen(theme.HEADLAND, theme.HEADLAND_WIDTH, theme.HEADLAND_STYLE)
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for loop in self._plan.headland_loops:
            self._draw_run(painter, loop)

    def _draw_transit(self, painter: QPainter) -> None:
        painter.setPen(theme.make_pen(theme.TRANSIT, theme.TRANSIT_WIDTH, theme.TRANSIT_STYLE))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for leg in self._plan.transit_legs:
            self._draw_run(painter, leg)

    def _draw_swaths(self, painter: QPainter) -> None:
        strokes = self._plan.strokes
        if not strokes:
            return
        width = theme.SWATH_WIDTH if self._scale > 0.4 else 1.2
        for k, s in enumerate(strokes):
            pen = theme.swath_pen(k, len(strokes), self._swath_by_order)
            pen.setWidthF(width)
            painter.setPen(pen)
            painter.drawLine(self.world_to_screen(*s.p0), self.world_to_screen(*s.p1))

    def _draw_machine_path(self, painter: QPainter) -> None:
        points = self._plan.path
        if not points or len(points) < 2:
            return
        painter.setPen(
            theme.make_pen(
                theme.MACHINE_PATH, theme.MACHINE_PATH_WIDTH, theme.MACHINE_PATH_STYLE
            )
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        pts = np.asarray(points, dtype=float)
        # Break where consecutive samples are far apart: those are separate legs,
        # not one straight drive, and joining them invents transit.
        step = np.hypot(np.diff(pts[:, 0]), np.diff(pts[:, 1]))
        jump = max(50.0, 20.0 * float(np.median(step)) if len(step) else 50.0)
        start = 0
        for i, d in enumerate(step, 1):
            if d > jump:
                self._draw_run(painter, pts[start:i])
                start = i
        self._draw_run(painter, pts[start:])

    def _draw_intervals(self, painter: QPainter) -> None:
        painter.setPen(QPen(theme.INTERVAL, 1.0))
        for i in range(self._clipper.n_scanlines):
            y = float(self._clipper.ys[i])
            for x0, x1 in self._clipper.intervals_at(i):
                painter.drawLine(self.world_to_screen(x0, y), self.world_to_screen(x1, y))

    def _draw_coverage(self, painter: QPainter) -> None:
        """The coverage raster, as one image scaled onto the world rectangle.

        One ``QImage`` rather than a rectangle per cell: a 3 m cell over a 20 ha
        field is twenty-odd thousand rectangles, slow to draw and slow to scroll,
        and none of that detail survives at screen resolution anyway.  Smooth
        scaling is switched off so the cells stay visibly cells -- a smoothed
        raster reads as a heat map, which is a different and stronger claim.
        """
        grid = self._grid
        if grid.nx == 0 or grid.ny == 0:
            return
        rgba = np.zeros((grid.ny, grid.nx, 4), dtype=np.uint8)
        rgba[grid.covered & grid.free] = (
            theme.COVERED_FILL.red(),
            theme.COVERED_FILL.green(),
            theme.COVERED_FILL.blue(),
            theme.COVERED_FILL.alpha(),
        )
        rgba[grid.missed] = (
            theme.MISSED_FILL.red(),
            theme.MISSED_FILL.green(),
            theme.MISSED_FILL.blue(),
            theme.MISSED_FILL.alpha(),
        )
        # QImage rows run top-down and world y runs bottom-up.
        rgba = np.ascontiguousarray(rgba[::-1])
        image = QImage(rgba.data, grid.nx, grid.ny, grid.nx * 4, QImage.Format.Format_RGBA8888)

        top_left = self.world_to_screen(float(grid.x_edges[0]), float(grid.y_edges[-1]))
        bottom_right = self.world_to_screen(float(grid.x_edges[-1]), float(grid.y_edges[0]))
        target = QRectF(top_left, bottom_right).normalized()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.drawImage(target, image)
        painter.restore()

        # Cell edges, only when a cell is big enough on screen to be a cell.
        cell_px = grid.cell * self._scale
        if 12.0 <= cell_px <= 220.0:
            painter.setPen(QPen(theme.GRID_LINE, 0.6))
            for x in grid.x_edges:
                painter.drawLine(
                    self.world_to_screen(float(x), float(grid.y_edges[0])),
                    self.world_to_screen(float(x), float(grid.y_edges[-1])),
                )
            for y in grid.y_edges:
                painter.drawLine(
                    self.world_to_screen(float(grid.x_edges[0]), float(y)),
                    self.world_to_screen(float(grid.x_edges[-1]), float(y)),
                )

    def _draw_metric_grid(self, painter: QPainter) -> None:
        """A faint metre grid whose spacing is a round number at this zoom."""
        step = _nice_step(120.0 * self.metres_per_pixel())
        if step <= 0:
            return
        minx, miny, maxx, maxy = G.bounds_of(self._field.boundary)
        painter.setPen(QPen(theme.GRID_LINE, 0.7))
        x = math.floor(minx / step) * step
        while x <= maxx:
            painter.drawLine(self.world_to_screen(x, miny), self.world_to_screen(x, maxy))
            x += step
        y = math.floor(miny / step) * step
        while y <= maxy:
            painter.drawLine(self.world_to_screen(minx, y), self.world_to_screen(maxx, y))
            y += step

    def _draw_affected(self, painter: QPainter) -> None:
        """Shade the scanlines the last change had to re-clip.

        The band spans the field's bounding box, not the widget: drawn edge to
        edge it reads as a page-wide highlight rather than as a property of these
        particular swaths, and it buries the field boundary under it.
        """
        minx, miny, maxx, maxy = G.bounds_of(self._field.boundary)
        left = self.world_to_screen(minx, 0.0).x()
        right = self.world_to_screen(maxx, 0.0).x()
        band = max(2.0, float(np.median(np.diff(self._clipper.ys))) * self._scale) * 0.9
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(theme.AFFECTED))
        for i in self._affected:
            if not (0 <= i < self._clipper.n_scanlines):
                continue
            y = self.world_to_screen(0.0, float(self._clipper.ys[i])).y()
            painter.drawRect(QRectF(left, y - band / 2.0, right - left, band))

    # -- overlays -------------------------------------------------------
    def _draw_scale_bar(self, painter: QPainter) -> None:
        """A metre scale bar: without it no screenshot of this canvas is readable."""
        nice = _nice_step(120.0 * self.metres_per_pixel())
        if nice <= 0:
            return
        length_px = nice / self.metres_per_pixel()
        x0 = 16.0
        y0 = self.height() - 22.0
        painter.setPen(QPen(theme.BOUNDARY, 1.6))
        painter.drawLine(QPointF(x0, y0), QPointF(x0 + length_px, y0))
        painter.drawLine(QPointF(x0, y0 - 4), QPointF(x0, y0 + 4))
        painter.drawLine(QPointF(x0 + length_px, y0 - 4), QPointF(x0 + length_px, y0 + 4))
        painter.setPen(QPen(theme.BOUNDARY))
        painter.setFont(QFont("", 8))
        painter.drawText(QPointF(x0, y0 - 7), f"{nice:g} m")

    def _draw_legend(self, painter: QPainter) -> None:
        """A legend built from the layers that are actually on screen.

        Each entry carries its line style rather than a colour swatch, because
        telling the strokes from the headland is a matter of dash pattern as much
        as of hue.
        """
        entries: list[tuple[QColor, Qt.PenStyle, float, str]] = []
        if Layer.SWATHS in self.layers and self._plan is not None and self._plan.strokes:
            entries.append((theme.SWATH, theme.SWATH_STYLE, 2.6, "作业条带（割草）"))
        if Layer.TRANSIT in self.layers and self._plan is not None and self._plan.transit_legs:
            entries.append((theme.TRANSIT, theme.TRANSIT_STYLE, 1.6, "空走段（抬机具）"))
        if Layer.HEADLAND in self.layers and self._plan is not None and self._plan.headland_loops:
            entries.append((theme.HEADLAND, theme.HEADLAND_STYLE, 1.8, "地头环"))
        if Layer.MACHINE_PATH in self.layers and self._plan is not None:
            entries.append((theme.MACHINE_PATH, theme.MACHINE_PATH_STYLE, 1.6, "割草机完整路径"))
        if Layer.COVERAGE in self.layers and self._grid is not None:
            entries.append((theme.COVERED_FILL, Qt.PenStyle.SolidLine, 6.0, "已覆盖"))
            entries.append((theme.MISSED_FILL, Qt.PenStyle.SolidLine, 6.0, "漏割"))
        if Layer.OBSTACLES in self.layers and self._field.obstacles:
            entries.append((theme.OBSTACLE, Qt.PenStyle.SolidLine, 6.0, "障碍物"))
        if Layer.AFFECTED in self.layers and self._affected:
            entries.append(
                (
                    theme.AFFECTED_EDGE,
                    Qt.PenStyle.SolidLine,
                    6.0,
                    f"本次重算 {len(self._affected)} 条扫描线",
                )
            )
        if not entries:
            return

        painter.setFont(QFont("", 8))
        metrics = QFontMetrics(painter.font())
        text_w = max(metrics.horizontalAdvance(e[3]) for e in entries)
        box_w = 44.0 + text_w + 12.0
        box_h = len(entries) * 17.0 + 10.0
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(255, 255, 255, 205)))
        painter.drawRoundedRect(QRectF(8.0, 8.0, box_w, box_h), 4.0, 4.0)
        painter.setPen(QPen(QColor(theme.BORDER)))
        painter.drawRoundedRect(QRectF(8.0, 8.0, box_w, box_h), 4.0, 4.0)

        y = 8.0 + 12.0
        for colour, style, width, label in entries:
            pen = QPen(colour, width)
            pen.setStyle(style)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            painter.setPen(pen)
            painter.drawLine(QPointF(15.0, y - 4.0), QPointF(38.0, y - 4.0))
            painter.setPen(QPen(theme.BOUNDARY))
            painter.drawText(QPointF(44.0, y), label)
            y += 17.0

    def _draw_hover(self, painter: QPainter) -> None:
        if self._hover is None or self._field is None:
            return
        x, y = self._hover
        p = self.world_to_screen(x, y)
        painter.setPen(QPen(QColor(0, 0, 0, 60), 1.0, Qt.PenStyle.DotLine))
        painter.drawLine(QPointF(0.0, p.y()), QPointF(float(self.width()), p.y()))
        painter.drawLine(QPointF(p.x(), 0.0), QPointF(p.x(), float(self.height())))
        painter.setPen(QPen(QColor(0, 0, 0, 140), 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(p, 4.0, 4.0)


def _nice_step(raw: float) -> float:
    """Round *raw* up to the nearest 1, 2 or 5 times a power of ten."""
    if not np.isfinite(raw) or raw <= 0:
        return 0.0
    magnitude = 10.0 ** math.floor(math.log10(raw))
    for mult in (1.0, 2.0, 5.0, 10.0):
        nice = magnitude * mult
        if nice >= raw:
            return nice
    return magnitude * 10.0
