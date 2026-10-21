"""Colours, line styles and metrics shared by the GUI, kept in one place.

The palette follows the conventions the report's figures use, so a screenshot
from the application and a figure from the report look like they came from the
same study -- because they did.  The line styles are fixed here rather than at
each call site for a blunter reason: with seven kinds of line on one canvas, a
reader has to be able to tell them apart without consulting a legend, and that
only works if each kind always looks the same.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPen

# --- scene -----------------------------------------------------------------
CANVAS_BG = QColor("#fbfbfb")
FREE_FILL = QColor("#eef4ee")
BOUNDARY = QColor("#1a1a1a")
OBSTACLE = QColor(192, 57, 43, 150)  # semi-transparent: what is behind matters
INTERVAL = QColor(11, 110, 79, 120)

# --- the kinds of line -----------------------------------------------------
#: Working strokes.  The thickest and the only saturated-bright line, because
#: they are the answer the whole picture exists to show.
SWATH = QColor("#1a9850")
#: Repositioning between strokes, implement up.
TRANSIT = QColor("#8a8f98")
#: Headland loops: the boundary lap and the lap around each obstacle.
HEADLAND = QColor("#1f6f8b")
#: The whole driven polyline, swaths and transit together.  Off by default --
#: drawn over the strokes it hides them, which is the complaint that prompted
#: drawing the transit separately in the first place.
MACHINE_PATH = QColor("#e8590c")

SWATH_WIDTH = 2.6
TRANSIT_WIDTH = 1.0
HEADLAND_WIDTH = 1.8
MACHINE_PATH_WIDTH = 1.4
BOUNDARY_WIDTH = 2.0

SWATH_STYLE = Qt.PenStyle.SolidLine
TRANSIT_STYLE = Qt.PenStyle.DashLine
HEADLAND_STYLE = Qt.PenStyle.DashDotLine
MACHINE_PATH_STYLE = Qt.PenStyle.SolidLine
BOUNDARY_STYLE = Qt.PenStyle.SolidLine

# --- coverage raster -------------------------------------------------------
#: Covered cells.  Deliberately faint.  The raster covers the *whole* field,
#: so at any strength that reads as a fill it competes with the strokes drawn on
#: top of it -- and the strokes are the thing the picture is for.  As a tint it
#: still answers "is this bit cut?" at a glance while leaving the green working
#: lines clearly the brightest thing on screen.
COVERED_FILL = QColor(26, 152, 80, 38)
#: Free cells the plan missed.  Substantially stronger, because unlike the
#: covered wash these are sparse and they are the defect the raster exists to
#: reveal -- a reader should not have to hunt for them.
MISSED_FILL = QColor(214, 39, 40, 165)
#: Cell edges, drawn only when cells are big enough on screen to read as cells.
GRID_LINE = QColor(120, 120, 120, 55)

# --- incremental overlays --------------------------------------------------
#: Bands the incremental planner had to re-clip.
AFFECTED = QColor(243, 156, 18, 90)
AFFECTED_EDGE = QColor("#e67e22")
#: An obstacle added in this session, as opposed to one the field came with.
NEW_OBSTACLE = QColor("#8e44ad")

# --- chrome ----------------------------------------------------------------
PANEL_BG = "#f4f5f7"
BORDER = "#d0d4d9"
MUTED = "#6b7280"
POSITIVE = "#1a7f37"
NEGATIVE = "#b42318"
WARNING = "#b26a00"

#: Swath colour ramp, available as an alternative to the flat green.
SWATH_CMAP = "viridis"

HANDLE_RADIUS = 6.0
MIN_SCALE = 0.02
MAX_SCALE = 40.0


def make_pen(colour: QColor, width: float, style: Qt.PenStyle) -> QPen:
    """A pen with flat caps, so a stroke covers exactly its own length.

    Round caps would add half a line width at each end and make a swath look
    longer than the interval it was clipped from -- which matters when the whole
    argument is that the intervals are exact.
    """
    pen = QPen(colour, width)
    pen.setStyle(style)
    pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    return pen


def swath_pen(index: int, count: int, by_order: bool = False) -> QPen:
    """Pen for working stroke *index* of *count*.

    By default every stroke is the same green.  Colouring by visit order is
    available and is genuinely useful for judging a tour, but as a default it
    turns the picture into a rainbow in which "green means a working stroke" --
    the one thing a reader most needs -- stops being true.
    """
    if not by_order:
        return make_pen(SWATH, SWATH_WIDTH, SWATH_STYLE)
    from matplotlib import colormaps

    cmap = colormaps[SWATH_CMAP]
    n = max(1, count - 1)
    pen = QPen(QColor.fromRgbF(*cmap(index / n)), SWATH_WIDTH)
    pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    return pen
