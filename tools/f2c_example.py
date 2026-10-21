#!/usr/bin/env python3
# =============================================================================
# Fields2Cover proof-of-life / reference baseline example  (CPP research project)
# =============================================================================
# Minimal but complete coverage-path-planning chain - self-contained, no data
# files required:
#
#   A. single-cell field (60 m x 60 m with two obstacle rings)
#        1. generate headlands        f2c.HG_Const_gen
#        2. generate swaths           f2c.SG_BruteForce
#        3. order the swaths          f2c.RP_Snake
#        4. plan the drivable path    f2c.PP_PathPlanning + PP_DubinsCurves
#   B. two-cell field
#        5. optimise the order in which swath blocks are driven with the
#           OR-Tools backed route planner  f2c.RP_RoutePlannerBase.genRoute
#   C. write a PNG picture of the result (f2c.Visualizer, matplotlib Agg)
#
# Usage (inside the container):
#     python3 /work/f2c_example.py [output_dir]
# =============================================================================

import math
import os
import sys

import fields2cover as f2c

OUT_DIR = sys.argv[1] if len(sys.argv) > 1 else "/work/out"
os.makedirs(OUT_DIR, exist_ok=True)


def show(label, thunk):
    """Print a metric if the wrapped call works; never abort the example."""
    try:
        print("%-34s: %s" % (label, thunk()))
    except Exception as exc:                       # pragma: no cover
        print("%-34s: <%s: %s>" % (label, type(exc).__name__, exc))


def ring(points):
    return f2c.LinearRing(f2c.VectorPoint([f2c.Point(x, y) for x, y in points]))


print("=" * 72)
print("Fields2Cover proof-of-life")
print("=" * 72)
print("%-34s: %s" % ("python", sys.version.split()[0]))
print("%-34s: %s" % ("fields2cover module", f2c.__file__))
show("fields2cover __version__", lambda: f2c.__version__)
print()

# =============================================================================
# A. Single-cell field: headlands -> swaths -> ordering -> path
# =============================================================================
print("-" * 72)
print("A. field -> headlands -> swaths -> path")
print("-" * 72)

# 60 m x 60 m field with two obstacle rings (same geometry as the official
# Fields2Cover tutorial 5 "route planning" example)
cells = f2c.Cells(f2c.Cell(ring([
    (0, 0), (60, 0), (60, 60), (0, 60), (0, 0)])))
cells.addRing(0, ring([(12, 12), (12, 18), (18, 18), (18, 12), (12, 12)]))
cells.addRing(0, ring([(36, 36), (36, 48), (48, 48), (48, 36), (36, 36)]))

robot = f2c.Robot(2.0, 6.0)        # Robot(<width>, <coverage width>) in metres
robot.setMinTurningRadius(2.0)
robot.setMaxDiffCurv(0.1)          # 1/m^2

# 1. headland (a 3 x robot-width border that is driven around the field)
no_hl = f2c.HG_Const_gen().generateHeadlands(cells, 3.0 * robot.getWidth())

# 2. swaths: parallel work rows inside the headland, at 90 deg to the x-axis.
#    NOTE: passing a *Cell* returns F2CSwaths; passing *Cells* returns
#    F2CSwathsByCells (one swath group per cell) - a classic API trap.
bf = f2c.SG_BruteForce()
swaths = bf.generateSwaths(math.pi / 2.0, robot.getCovWidth(), no_hl.getGeometry(0))

# 3. swath ordering: snake (boustrophedon) order
swaths_ordered = f2c.RP_Snake().genSortedSwaths(swaths)

# 4. path planning: connect the swaths with Dubins curves
path = f2c.PP_PathPlanning().planPath(
    robot, swaths_ordered, f2c.PP_DubinsCurves())

show("field area [m^2]", lambda: cells.area())
show("area w/o headland [m^2]", lambda: no_hl.area())
show("robot width [m]", lambda: robot.getWidth())
show("robot coverage width [m]", lambda: robot.getCovWidth())
show("min turning radius [m]", lambda: robot.getMinTurningRadius())
show("swaths generated", lambda: swaths.size())
show("swaths after snake ordering", lambda: swaths_ordered.size())
show("path points (states)", lambda: path.size())
show("path length [m]", lambda: path.length())

# =============================================================================
# B. Two-cell field: OR-Tools backed route planning (swath-block ordering)
# =============================================================================
print()
print("-" * 72)
print("B. OR-Tools route planning over two cells")
print("-" * 72)

two = f2c.Cells(f2c.Cell(ring([(0, 0), (40, 0), (40, 40), (0, 40), (0, 0)])))
two.addGeometry(f2c.Cell(ring([(60, 0), (100, 0), (100, 40), (60, 40), (60, 0)])))
two_hl = f2c.HG_Const_gen().generateHeadlands(two, 3.0 * robot.getWidth())

# Cells -> F2CSwathsByCells (one swath group per cell): what genRoute expects
swaths_by_cells = bf.generateSwaths(math.pi / 2.0, robot.getCovWidth(), two_hl)
show("cells in field", lambda: two.size())
show("swath groups (per cell)", lambda: swaths_by_cells.size())

route = f2c.RP_RoutePlannerBase().genRoute(two_hl, swaths_by_cells)
show("route swath groups", lambda: route.sizeVectorSwaths())
show("route connections", lambda: route.sizeConnections())
show("route length (OR-Tools TSP) [m]", lambda: route.length())

# =============================================================================
# C. Visualisation
# =============================================================================
print()
print("-" * 72)
print("C. figure")
print("-" * 72)

png = os.path.join(OUT_DIR, "f2c_example.png")
try:
    f2c.Visualizer.figure()
    f2c.Visualizer.plot(cells)
    f2c.Visualizer.plot(no_hl)
    f2c.Visualizer.plot(swaths_ordered)
    f2c.Visualizer.plot(path)
    f2c.Visualizer.save(png)
    print("%-34s: %s" % ("saved figure (f2c.Visualizer)", png))
except Exception as exc:
    print("%-34s: <%s: %s>" % ("f2c.Visualizer failed", type(exc).__name__, exc))
    try:                                        # fall back to plain matplotlib
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        xs = [path.getState(i).point.getX() for i in range(path.size())]
        ys = [path.getState(i).point.getY() for i in range(path.size())]
        plt.figure(figsize=(6, 6))
        plt.plot(xs, ys, "-")
        plt.axis("equal")
        plt.savefig(png, dpi=110)
        print("%-34s: %s" % ("saved figure (fallback)", png))
    except Exception as exc2:
        print("%-34s: <%s: %s>" % ("plotting failed", type(exc2).__name__, exc2))

print()
print("=" * 72)
print("OK: field -> headlands -> swaths -> route -> path all completed")
print("=" * 72)
