#!/usr/bin/env python3
# =============================================================================
# f2c_benchmark.py - Fields2Cover side of the CPP head-to-head benchmark
# =============================================================================
# Runs the standard Fields2Cover complete coverage flow on every field of
# results/f2c_io/fields.json and writes one JSON per field (plus a summary) in
# the same schema as results/f2c_io/cppclip/<name>.json.
#
# Pipeline per field (all coordinates are metres; nothing is reprojected):
#   1. f2c.Cells from "outer" rings + "holes" (a hole is added to the outer ring
#      that contains it; all 60 fields have exactly one outer ring)
#   2. headland      : no_hl = f2c.HG_Const_gen().generateHeadlands(cells, 6.0)
#   3. headland cover: f2c.HG_Const_gen().generateHeadlandSwaths(
#                        cells, 6.0, 1, True)[0]
#      -> the 6 m headland band as one ring; its loops are the centre lines the
#      robot drives (a 6 m implement on that line covers 0..6 m).  For the
#      single-ring benchmark fields this loop is byte-identical to the
#      "headland" polygon cppclip reports.
#   4. mainland swaths: f2c.SG_BruteForce().generateSwaths(angle, 6.0, cell)
#      with the angle from computeBestAngle(OBJ_NSwath, 6.0, cell) - i.e. the
#      same objective and the same 7.5 deg grid cppclip's angle_deg uses.
#      If the 6 m inset splits the field into several cells, every cell is
#      swathed and the angle that minimises the TOTAL swath count is used.
#   5. two orderings over exactly the same strokes (only the order differs):
#        "snake"   : headland laps + f2c.RP_Snake().genSortedSwaths(...)
#        "ortools" : headland laps + OR-Tools order from
#                    f2c.RP_RoutePlannerBase().genRoute(headland_ring, swaths)
#   6. path: f2c.PP_PathPlanning().planPath(robot, swaths, PP_DubinsCurves())
#      with robot = f2c.Robot(2.0, 6.0), setMinTurningRadius(2.0)
#
# Working vs transit comes from the path itself: every PathState carries
# type in {SWATH=1, TURN=2, HL_SWATH=3} plus its own length, so
#     working = sum(len | type in {1,3})    transit = sum(len | type == 2)
#
# ROBUSTNESS: each field is processed in a child process (--only NAME), because
# Fields2Cover 2.1.1 can segfault on degenerate geometry; a crashing field is
# recorded as a failure instead of killing the sweep.
#
# Usage: python3 /work/tools/f2c_benchmark.py [--limit N] [--fields N1 N2 ...]
#        python3 /work/tools/f2c_benchmark.py --only NAME --record FILE   (child)
# Set F2C_TRACE=1 for step-by-step tracing.
# =============================================================================

import argparse
import io
import json
import math
import os
import statistics
import subprocess
import sys
import time
import traceback

import fields2cover as f2c

BASE_DIR = "/work/results/f2c_io"
FIELDS_JSON = os.path.join(BASE_DIR, "fields.json")
OUT_DIR = os.path.join(BASE_DIR, "fields2cover")
SUMMARY_JSON = os.path.join(BASE_DIR, "fields2cover_summary.json")

SWATH_WIDTH = 6.0          # m, implement working width (same as cppclip)
HEADLAND_WIDTH = 6.0       # m, headland band to cover (same as cppclip)
ROBOT_WIDTH = 2.0          # m
MIN_TURN_RADIUS = 2.0      # m (as in the upstream complete-flow tutorial)
ANGLE_STEP_DEG = 7.5       # same angle grid as cppclip's angle_deg values
VARIANTS = ("snake", "ortools")
CHILD_TIMEOUT_S = 600      # per-field wall clock for the isolated child

TRACE = os.environ.get("F2C_TRACE") == "1"


def trace(*args):
    if TRACE:
        print("    [trace]", *args, flush=True)


# ---------------------------------------------------------------------------
# geometry helpers
# ---------------------------------------------------------------------------
def build_cells(fdef):
    """Fields2Cover Cells from the benchmark schema (metres, no reprojection)."""
    cells = f2c.Cells()
    outer_rings = fdef["outer"]
    for ring in outer_rings:
        cells.addGeometry(f2c.Cell(f2c.LinearRing(
            f2c.VectorPoint([f2c.Point(x, y) for x, y in ring]))))

    for hole in (fdef.get("holes") or []):
        hx, hy = hole[0]
        target = None
        for i, ring in enumerate(outer_rings):
            inside = False
            for a in range(len(ring) - 1):
                (x1, y1), (x2, y2) = ring[a], ring[a + 1]
                if (y1 > hy) != (y2 > hy):
                    xin = x1 + (hy - y1) * (x2 - x1) / (y2 - y1)
                    if hx < xin:
                        inside = not inside
            if inside:
                target = i
                break
        if target is None:
            raise ValueError("hole ring not contained in any outer ring")
        cells.addRing(target, f2c.LinearRing(
            f2c.VectorPoint([f2c.Point(x, y) for x, y in hole])))
    return cells


def ring_points(ring):
    return [(ring.getX(i), ring.getY(i)) for i in range(ring.size())]


def cell_loops(cell):
    """All rings of a Cell as point lists: exterior first, then the holes."""
    loops = [ring_points(cell.getExteriorRing())]
    for j in range(cell.size() - 1):
        loops.append(ring_points(cell.getInteriorRing(j)))
    return loops


def make_lap_swath(points, lap_id):
    """A closed headland loop driven as a single (headland type) swath."""
    ring = f2c.LinearRing(f2c.VectorPoint([f2c.Point(x, y) for x, y in points]))
    return f2c.Swath(f2c.LineString(ring), SWATH_WIDTH, lap_id,
                     f2c.SwathType_HEADLAND)


def swath_segment(swath):
    a, b = swath.startPoint(), swath.endPoint()
    return [[a.getX(), a.getY()], [b.getX(), b.getY()]]


def path_metrics(path):
    """Working / transit split straight from the PathState types."""
    work = transit = 0.0
    for i in range(path.size()):
        st = path.getState(i)
        if int(st.type) == 2:            # PathSectionType::TURN
            transit += st.len
        else:                            # SWATH == 1, HL_SWATH == 3
            work += st.len
    return work, transit, path.size()


def path_polyline(path):
    ls = path.toLineString()
    return [[ls.getX(i), ls.getY(i)] for i in range(ls.size())]


def coverage_fraction(swath_objs, field_cells):
    """Fraction of the field covered by the driven strokes (incl. headland)."""
    union = None
    for sw in swath_objs:
        cov = sw.areaCovered(field_cells)
        union = cov if union is None else union.unionOp(cov)
    if union is None:
        return 0.0
    return union.area() / field_cells.area()


def choose_angle(bf, no_hl):
    """Swath angle minimising the number of swaths (cppclip's 7.5 deg grid)."""
    if no_hl.isEmpty():
        return 0.0, 0
    if no_hl.size() == 1:
        ang = bf.computeBestAngle(f2c.OBJ_NSwath(), SWATH_WIDTH,
                                  no_hl.getGeometry(0))
        n = bf.generateSwaths(ang, SWATH_WIDTH, no_hl.getGeometry(0)).size()
        return ang, n
    # multi-cell mainland (a pinched field): minimise the total swath count
    best_angle, best_total = 0.0, None
    for k in range(int(round(180.0 / ANGLE_STEP_DEG))):
        cand = math.radians(k * ANGLE_STEP_DEG)
        total = sum(bf.generateSwaths(cand, SWATH_WIDTH, no_hl.getGeometry(i)).size()
                    for i in range(no_hl.size()))
        if best_total is None or total < best_total:
            best_angle, best_total = cand, total
    return best_angle, best_total


def generate_mainland(bf, no_hl, angle):
    """Mainland swaths for every cell of no_hl: (Swaths, SwathsByCells)."""
    mainland = f2c.Swaths()
    keep_alive = []
    for i in range(no_hl.size()):
        part = bf.generateSwaths(angle, SWATH_WIDTH, no_hl.getGeometry(i))
        keep_alive.append(part)                     # keep proxies alive
        for k in range(part.size()):
            mainland.push_back(part.at(k))
    by_cells = bf.generateSwaths(angle, SWATH_WIDTH, no_hl)
    return mainland, by_cells, keep_alive


# ---------------------------------------------------------------------------
# per-field benchmark
# ---------------------------------------------------------------------------
def run_field(name, fdef):
    """Returns (results_by_variant, notes)."""
    notes = []
    t_field0 = time.perf_counter()

    cells = build_cells(fdef)
    field_area = cells.area()
    trace("cells", cells.size(), "area %.1f" % field_area)
    if cells.isEmpty() or field_area <= 0.0:
        raise ValueError("empty or zero-area field geometry")

    const_hl = f2c.HG_Const_gen()
    robot = f2c.Robot(ROBOT_WIDTH, SWATH_WIDTH)
    robot.setMinTurningRadius(MIN_TURN_RADIUS)

    no_hl = const_hl.generateHeadlands(cells, HEADLAND_WIDTH)
    trace("no_hl cells %d area %.1f" % (no_hl.size(), no_hl.area()))
    if no_hl.size() > 1:
        notes.append("6 m inset split the field into %d cells; all are swathed "
                     "and the angle minimising the total swath count is used"
                     % no_hl.size())

    # headland band = one 6 m swath ring; its loops are the driven centre lines
    hl_cells = const_hl.generateHeadlandSwaths(cells, HEADLAND_WIDTH, 1, True)
    if not hl_cells:
        raise RuntimeError("generateHeadlandSwaths returned no ring")
    hl_ring = hl_cells[0]
    lap_loops = []
    for i in range(hl_ring.size()):
        lap_loops.extend(cell_loops(hl_ring.getGeometry(i)))
    trace("headland loops", [len(l) for l in lap_loops])
    if not lap_loops:
        raise RuntimeError("headland ring has no loop")
    lap_swaths = [make_lap_swath(pts, i) for i, pts in enumerate(lap_loops)]

    # mainland swaths (same objective and angle grid as cppclip)
    bf = f2c.SG_BruteForce()
    bf.setStepAngle(math.radians(ANGLE_STEP_DEG))
    t_angle0 = time.perf_counter()
    angle, n_candidate = choose_angle(bf, no_hl)
    mainland, mainland_by_cells, _keep = generate_mainland(bf, no_hl, angle)
    t_angle = time.perf_counter() - t_angle0
    trace("angle %.3f deg, mainland swaths %d" % (math.degrees(angle), mainland.size()))

    t_prep = time.perf_counter() - t_field0

    headland_len = sum(sw.length() for sw in lap_swaths)
    n_mainland = mainland.size()
    if n_mainland == 1:
        notes.append("RP_Snake skipped: Fields2Cover 2.1.1 segfaults in "
                     "genSortedSwaths() when given exactly one swath")

    results = {}
    for variant in VARIANTS:
        trace("variant", variant, "start")
        t0 = time.perf_counter()
        ordered = f2c.Swaths()
        for sw in lap_swaths:
            ordered.push_back(sw)

        route_line_len = None
        if n_mainland <= 1:
            driven_mainland = [f2c.Swath(mainland.at(i)) for i in range(n_mainland)]
        elif variant == "snake":
            sorted_swaths = f2c.RP_Snake().genSortedSwaths(mainland)
            driven_mainland = [f2c.Swath(sorted_swaths.at(i))
                               for i in range(sorted_swaths.size())]
        else:
            route = f2c.RP_RoutePlannerBase().genRoute(hl_ring, mainland_by_cells)
            trace("route groups", route.sizeVectorSwaths())
            route_line_len = route.asLineString().length()
            groups = route.getVectorSwaths()        # keep the proxy alive
            driven_mainland = []
            for gi in range(len(groups)):
                group = groups[gi]
                for i in range(group.size()):
                    driven_mainland.append(f2c.Swath(group.at(i)))
        for sw in driven_mainland:
            ordered.push_back(sw)
        trace("ordered swaths", ordered.size())
        ordered_all = [f2c.Swath(ordered.at(i)) for i in range(ordered.size())]

        plan_t = time.perf_counter()
        path = f2c.PP_PathPlanning().planPath(robot, ordered, f2c.PP_DubinsCurves())
        plan_t = time.perf_counter() - plan_t
        plan_s = time.perf_counter() - t0
        trace("path states", path.size(), "len %.2f" % path.length())

        work, transit, n_states = path_metrics(path)
        path_len = path.length()

        try:
            cov = coverage_fraction(lap_swaths + driven_mainland, cells)
        except Exception as exc:
            cov = None
            notes.append("coverage computation failed: %s: %s" % (type(exc).__name__, exc))

        results[variant] = dict(
            system="fields2cover",
            field=name,
            route=variant,
            swaths=[swath_segment(sw) for sw in driven_mainland],
            headland=[pt for loop in lap_loops for pt in loop],
            headland_loops=lap_loops,
            path=path_polyline(path),
            # sparse polyline: stroke end points joined by straight connectors.
            # cppclip's "path" key holds exactly this, so the two systems can be
            # compared like for like; use "path" above for the real driven line.
            route_polyline=[pt for sw in ordered_all for pt in
                            (swath_segment(sw)[0], swath_segment(sw)[1])],
            time_s=t_prep + plan_s,
            time_breakdown_s=dict(geometry_and_angle=t_prep,
                                  angle_search=t_angle,
                                  ordering_and_path=plan_s,
                                  path_planning_only=plan_t),
            n_swaths=len(driven_mainland),
            n_headland_laps=len(lap_swaths),
            turn_radius=MIN_TURN_RADIUS,
            swath_angle_deg=math.degrees(angle),
            angle_deg=math.degrees(angle),
            area_m2=field_area,
            no_headland_area_m2=no_hl.area(),
            path_length=path_len,
            working_length=work,
            transit_length=transit,
            non_working_ratio=(transit / path_len) if path_len else 0.0,
            mainland_swath_length=sum(sw.length() for sw in driven_mainland),
            headland_length=headland_len,
            n_path_states=n_states,
            coverage=cov,
            route_polyline_length=route_line_len,
            notes=list(notes),
        )
    return results, notes


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------
RECORD_KEYS = ("time_s", "n_swaths", "path_length", "working_length",
               "transit_length", "non_working_ratio", "coverage",
               "swath_angle_deg", "mainland_swath_length", "headland_length",
               "n_headland_laps", "n_path_states", "route_polyline_length")


def field_record(name, fdef, results):
    rec = dict(field=name, ok=True, error=None,
               area_m2=results["snake"]["area_m2"],
               n_vertices=fdef.get("n_vertices"),
               has_holes=bool(fdef.get("holes")),
               notes=results["snake"]["notes"])
    for variant, res in results.items():
        rec[variant] = {k: res[k] for k in RECORD_KEYS}
    return rec


def write_field_outputs(name, fdef, results, out_dir):
    for variant, res in results.items():
        suffix = "" if variant == "snake" else ".ortools"
        with io.open(os.path.join(out_dir, name + suffix + ".json"), "w",
                     encoding="utf-8") as fh:
            json.dump(res, fh)


def write_error_output(name, message, out_dir):
    with io.open(os.path.join(out_dir, name + ".json"), "w", encoding="utf-8") as fh:
        json.dump(dict(system="fields2cover", field=name, error=message), fh)


def run_child(name, fields, out_dir, record_path):
    """One field, in this process (so a segfault only kills this field)."""
    try:
        results, _notes = run_field(name, fields[name])
        write_field_outputs(name, fields[name], results, out_dir)
        rec = field_record(name, fields[name], results)
        rc = 0
    except Exception as exc:
        message = "%s: %s" % (type(exc).__name__, exc)
        write_error_output(name, message, out_dir)
        rec = dict(field=name, ok=False, error=message)
        traceback.print_exc()
        rc = 1
    with io.open(record_path, "w", encoding="utf-8") as fh:
        json.dump(rec, fh)
    return rc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fields", nargs="*", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out-dir", default=OUT_DIR)
    ap.add_argument("--only", default=None, help="run a single field (child mode)")
    ap.add_argument("--record", default=None, help="where the child writes its record")
    args = ap.parse_args()

    with io.open(FIELDS_JSON, encoding="utf-8") as fh:
        fields = json.load(fh)

    os.makedirs(args.out_dir, exist_ok=True)

    # ---------------- child mode: exactly one field ----------------
    if args.only:
        return run_child(args.only, fields, args.out_dir, args.record)

    # ---------------- parent mode: one subprocess per field ----------------
    names = args.fields if args.fields else list(fields.keys())
    if args.limit:
        names = names[:args.limit]

    print("=" * 78)
    print("Fields2Cover benchmark - %d fields (one subprocess per field)" % len(names))
    print("  image: fields2cover:2.1.1 | python %s | f2c %s"
          % (sys.version.split()[0], getattr(f2c, "__version__", "?")))
    print("  swath %.1f m | headland %.1f m | robot (%.1f, %.1f) | R_min %.1f m"
          % (SWATH_WIDTH, HEADLAND_WIDTH, ROBOT_WIDTH, SWATH_WIDTH,
             MIN_TURN_RADIUS))
    print("  angle: OBJ_NSwath on a %.1f deg grid | variants: %s"
          % (ANGLE_STEP_DEG, ", ".join(VARIANTS)))
    print("=" * 78)

    summary = []
    n_ok = n_fail = 0
    for k, name in enumerate(names, 1):
        record_path = os.path.join(args.out_dir, "." + name + ".record.json")
        cmd = [sys.executable, "-u", os.path.abspath(__file__),
               "--only", name, "--out-dir", args.out_dir,
               "--record", record_path]
        t0 = time.perf_counter()
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=CHILD_TIMEOUT_S)
            rc, out, err = proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired:
            rc, out, err = "timeout", "", "exceeded %d s" % CHILD_TIMEOUT_S
        wall = time.perf_counter() - t0

        rec = None
        if os.path.exists(record_path):
            try:
                with io.open(record_path, encoding="utf-8") as fh:
                    rec = json.load(fh)
            except Exception:
                rec = None
            os.remove(record_path)

        if rc == 0 and rec and rec.get("ok"):
            n_ok += 1
            summary.append(rec)
            print("[%2d/%2d] OK   %-14s n_sw=%3d ang=%6.2f  snake %8.1f m/%5.3f s"
                  "  ortools %8.1f m/%5.3f s  cov=%.4f  (%.1fs wall)"
                  % (k, len(names), name, rec["snake"]["n_swaths"],
                     rec["snake"]["swath_angle_deg"],
                     rec["snake"]["path_length"], rec["snake"]["time_s"],
                     rec["ortools"]["path_length"], rec["ortools"]["time_s"],
                     rec["snake"]["coverage"] if rec["snake"]["coverage"] is not None
                     else float("nan"), wall))
        else:
            n_fail += 1
            if rc == 0:
                message = (rec or {}).get("error", "child failed without a record")
            elif rc == "timeout":
                message = "timeout after %d s" % CHILD_TIMEOUT_S
            elif rc is not None and isinstance(rc, int) and rc < 0:
                message = "child killed by signal %d (segfault/abort in the " \
                          "Fields2Cover C++ library)" % -rc
            else:
                message = "child exited with code %s" % rc
            if err.strip():
                message += " | stderr tail: " + err.strip().splitlines()[-1][:300]
            write_error_output(name, message, args.out_dir)
            summary.append(dict(field=name, ok=False, error=message))
            print("[%2d/%2d] FAIL %-14s %s" % (k, len(names), name, message))

    with io.open(SUMMARY_JSON, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=1)

    # ---------------- final table ----------------
    def vals(key, variant):
        out = []
        for r in summary:
            if r.get("ok") and r.get(variant) and r[variant].get(key) is not None:
                out.append(r[variant][key])
        return out

    print()
    print("=" * 78)
    print("SUMMARY   fields attempted: %d   OK: %d   failed: %d"
          % (len(names), n_ok, n_fail))
    print("%-26s %14s %14s" % ("metric", "snake", "ortools"))
    for key in ("time_s", "n_swaths", "path_length", "working_length",
                "transit_length", "non_working_ratio", "coverage"):
        vs, vo = vals(key, "snake"), vals(key, "ortools")
        print("%-26s %14.4f %14.4f"
              % ("median " + key,
                 statistics.median(vs) if vs else float("nan"),
                 statistics.median(vo) if vo else float("nan")))
    for key in ("time_s", "n_swaths", "path_length", "coverage"):
        vs, vo = vals(key, "snake"), vals(key, "ortools")
        print("%-26s %14.4f %14.4f"
              % ("mean " + key,
                 statistics.fmean(vs) if vs else float("nan"),
                 statistics.fmean(vo) if vo else float("nan")))
    if n_fail:
        print("\nfailed fields:")
        for r in summary:
            if not r.get("ok"):
                print("  %-14s %s" % (r["field"], r["error"]))
    noted = [r for r in summary if r.get("ok") and r.get("notes")]
    if noted:
        print("\nfields with notes:")
        for r in noted:
            print("  %-14s %s" % (r["field"], "; ".join(r["notes"])))
    print("=" * 78)
    print("per-field JSON : %s" % args.out_dir)
    print("summary JSON   : %s" % SUMMARY_JSON)
    return 0 if n_fail == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
