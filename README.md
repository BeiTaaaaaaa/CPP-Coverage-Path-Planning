# cppclip

> 中文版：[README.zh-CN.md](README.zh-CN.md) · [中文研究报告](REPORT.zh-CN.md)

Coverage path planning for agricultural machinery, formulated as a **geometric
clipping** problem instead of a cell-decomposition problem, with **incremental
replanning** when the environment changes.

The whole approach rests on one observation: the classic scanline *active edge
table* from computer-graphics polygon fill is, unchanged, the right data
structure for coverage planning. Each swath is the intersection of a scanline
with the drivable area, and because every polygon edge is indexed by the `y`
span it covers, an obstacle that appears mid-operation invalidates only the
scanlines inside its own span.

```
field + obstacles
      |
      +-- erode boundary by the headland width ------> headland loops
      |
      +-- scanline edge table --> effective intervals --> swath strokes
                                        |
                                        +-- ordering --> coverage path
```

There is **no cell decomposition anywhere in this pipeline**. Concavity and
in-field holes fall out of the even-odd parity rule.

---

## Quick start

```bash
# 1. install; the [gui] extra pulls in PySide6 for the viewer
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[gui]"      # Windows
# .venv/bin/python -m pip install -e ".[gui]"        # macOS / Linux

# 2. open the viewer (a window, not a web page)
.venv\Scripts\python -m cppclip.gui
# .venv/bin/python -m cppclip.gui

# 3. or run the study from the command line
.venv\Scripts\python -m pytest tests/ -q              # 145 tests
.venv\Scripts\python examples\quickstart.py           # guided tour, writes two figures

.venv\Scripts\python experiments/run_all.py           # the whole study, ~50 min
.venv\Scripts\python experiments/run_all.py --quick   # same pipeline on small samples

.venv\Scripts\python experiments/verify.py            # repository self-consistency (16 checks)
.venv\Scripts\python experiments/audit_numbers.py     # every number in the write-up vs the tables
.venv\Scripts\python tools/verify_dubins.py           # Dubins vs an independent numerical search
.venv\Scripts\python tools/verify_headland.py         # no headland drives through an obstacle
.venv\Scripts\python tools/check_dead_code.py
.venv\Scripts\python tools/check_imports.py
```

Every command above calls the virtual environment's interpreter by its path, so
there is nothing to activate first — run them from the repository root as
written. Dropping the `[gui]` extra still installs the library and every
experiment; only the viewer needs it. If a shell objects to the brackets, quote
them (`".[gui]"`); they work unquoted in PowerShell 7 and bash.

`run_all.py --quick` moves the real result tables aside and restores them
afterwards, so a smoke run cannot silently replace the artefacts the report is
built on. It also skips the number audit, because during a quick run the tables
on disk are deliberately not the real ones.

## Running the viewer

Two equivalent ways to start it, once the `[gui]` extra is installed:

```bash
.venv\Scripts\python -m cppclip.gui        # Windows
.venv\Scripts\cppclip-gui                  # the console script pip installed
# .venv/bin/python -m cppclip.gui          # macOS / Linux
# .venv/bin/cppclip-gui
```

A window opens with three tabs: **田地规划**, **增量重算（核心实验）**, **实验结果**.
There is no server and no browser — if nothing appears, the process exited on
startup and the traceback is in the terminal you launched it from.

Typical first session, about two minutes:

1. **田地规划** tab — the field panel already holds a 2 ha synthetic field. Press
   **规划**. You should see green working strokes, blue dash-dot headland loops
   around the boundary and each obstacle, grey dashed transit legs, and a faint
   green coverage raster with any missed cells in red.
2. Untick **覆盖栅格** and the strokes underneath become obvious; tick **割草机路径**
   to overlay the whole driven polyline in orange.
3. **增量重算** tab — click anywhere inside the field. An obstacle appears, the
   scanlines that had to be re-clipped are shaded orange, and the panel reports
   the incremental update against a from-scratch solve of the same scene, timed
   back to back in the same process.
4. **实验结果** tab — pick an experiment from the dropdown; the chart is redrawn
   from `results/tables/*.csv` with the raw table underneath.

### If it does not start

| symptom | cause and fix |
|---|---|
| `ModuleNotFoundError: No module named 'PySide6'` | the extra was not installed. Re-run `pip install -e ".[gui]"`, quoted. |
| `pip` says `Invalid requirement: .[gui]` or matches nothing | the shell ate the brackets. Quote it: `".[gui]"`. |
| `Could not find the Qt platform plugin "windows"` | two Qt bindings in one environment, usually PyQt5 plus PySide6. Use a clean venv for this project. |
| Charts show empty boxes where Chinese text should be | no CJK font on the system. The viewer auto-selects one from Microsoft YaHei / SimHei / Noto Sans CJK / PingFang; on a machine with none installed, install one or the chart labels will be blank. |
| The window opens but the canvas is blank | press the field panel's **载入 / 更新田地**, then **规划**. |

On a headless machine (CI, a container) there is nothing to show a window on; set
`QT_QPA_PLATFORM=offscreen` and use `tools/gui_screenshot.py`, which drives the
real widgets and writes PNGs without a display.

```python
from cppclip.fields import make_field
from cppclip.planner import PlanParams, plan
from cppclip.metrics import evaluate

field  = make_field("star", seed=1, n_obstacles=12, target_area=20_000.0)
params = PlanParams(swath_width=6.0, headland_width=6.0)

p = plan(field, params)
m = evaluate(field, p)

print(f"coverage {m.coverage:.4f}   path {m.path_length:.0f} m   "
      f"non-working {100*m.non_working_ratio:.1f} %   {1000*m.plan_time:.0f} ms")
```

---

## What is here

| Module | Role |
|---|---|
| `sweep.py` | **The core.** Edge table + active-edge test, effective intervals per scanline, incremental insert/remove of obstacles |
| `geometry.py` | Polygon conventions and primitives over Shapely/GEOS |
| `swaths.py` | Intervals to working strokes; the rotated planning frame; swath-heading search |
| `routing.py` | Stroke ordering (boustrophedon baseline, greedy, 2-opt, Or-opt) and route to polyline |
| `planner.py` | The end-to-end pipeline, with per-stage timings |
| `incremental.py` | **The contribution.** Dynamic replanning under obstacle arrival and removal |
| `metrics.py` | Coverage, overlap, spillage, path length, non-working ratio, defined explicitly |
| `fields.py` | Synthetic scene generators (rectilinear, L, U, star, random obstacles) |
| `io_fields.py` | Real field loading: WGS84 WKT to a local metric tangent plane |
| `turns.py` | Dubins paths and agricultural headland turn manoeuvres |
| `viz.py` | Plotting |
| `gui/` | The Qt viewer: `python -m cppclip.gui` |

## What the viewer shows

Three tabs:

* **Field planning** — pick a synthetic field or one of the 350 real ones, set the
  swath width, headland width, turning radius and route strategy, and see the
  swaths, headland loops, transit legs and every metric, with a per-stage timing
  bar.
* **Incremental replanning** — click anywhere in the field and an obstacle appears
  there. The planner re-clips only the scanlines that obstacle spans (shaded
  orange), keeps the surviving strokes in place and repairs the tour locally, and
  the tab reports that against solving the same scene from scratch, measured back
  to back in one process. This is the paper's headline experiment, interactively.
* **Results** — the five experiments, re-plotted from `results/tables/*.csv`, with
  the raw table underneath.

It is a *view*: it computes nothing the library does not already compute, and it
never reports a number it did not obtain from the library. It is also how several
of the defects in the report were found — see section 7.1 of
[REPORT.md](REPORT.md) — which is the argument for building one.

### Reading the picture

Seven kinds of line share one canvas, so each kind always looks the same and the
legend repeats the line style rather than showing only a colour:

| element | rendering |
|---|---|
| working strokes | thick solid **green** — the implement is down |
| transit legs | thin dashed **grey** — the implement is up |
| headland loops | dash-dot **blue**, one polyline per loop |
| obstacles | semi-transparent **red** fill, so what is behind stays visible |
| field boundary | solid **black** |
| full machine path | thick **orange**, off by default |
| coverage raster | faint **green** tint, with missed cells in **red** |

Every element has its own layer switch, so a reader can isolate one question at a
time: the strokes alone, the headland alone, the raster alone.

### The coverage raster

The raster answers the question a path drawing cannot — *where did it actually
cut?* — by sampling the same swept geometry the scalar coverage is measured from
onto a lattice, through `metrics.coverage_grid`:

```python
from cppclip.metrics import coverage_grid, swept_geometry

grid = coverage_grid(field, plan, cell=3.0, swept=swept_geometry(plan))
print(grid.coverage, grid.exact_coverage, grid.missed_area())
```

The default cell is half the swath width, which is the coarsest spacing that can
still show a gap between two adjacent swaths. Pass `swept` to reuse a union you
already have: building it dominates the cost (about 33 ms on a 2.5 ha field,
against under 3 ms for the sampling).

**The raster is an estimate and the window says so.** Centre sampling errs by
roughly the covered perimeter times half a cell, and because the lattice is
anchored to the bounding box the sign of that error flips as the cell size
changes — so the panel prints the raster figure, the exact figure and the gap
between them rather than implying they agree. The exact `metrics.evaluate`
number remains the one to quote.

![Planning tab](results/gui/tab1_planning.png)

![Incremental replanning tab](results/gui/tab2_incremental.png)

## The two claims, and how they are tested

### 1. The edge table reproduces exact clipping

Every scanline's intervals are compared against intersecting a line with the
exact free-space polygon via GEOS. Across the whole benchmark the two agree to
machine precision with zero mismatching scanlines, while being roughly ten times
faster than a per-scanline GEOS clip:

```
fields             : 350
scanlines compared : 14,387
mismatched         : 0
max abs error      : 2.274e-13 m
speed-up median    : 9.71x   (min 4.74x, max 32.35x)
```

Run `python experiments/exp_clipping.py` to reproduce.

The even-odd rule is exact only for a well-formed ring set (disjoint shells,
holes strictly inside and not overlapping). `check_rings()` detects the
pathologies that would break it, and `IncrementalPlanner` merges obstacles whose
dilated shapes touch rather than silently producing a wrong answer.

### 2. Incremental replanning is much cheaper than replanning from scratch

After any sequence of obstacle insertions, removals, group merges and group
splits, the incremental clipper is asserted to produce **bit-identical**
intervals to a from-scratch build of the same scene
(`tests/test_incremental.py`). That equivalence is what licenses the speed claim.

Measured on real fields, with a 20 m obstacle appearing on a field scaled up by
a range of factors:

| field size | scanlines | scanlines invalidated | speed-up vs full replan | path-length penalty |
|---|---|---|---|---|
| 2.4 ha | 28 | 19.7 % | 2.9x | -0.2 % |
| 9.7 ha | 58 | 10.3 % | 16.1x | +0.2 % |
| 39 ha | 118 | 4.8 % | 18.2x | +0.2 % |
| 156 ha | 238 | 2.6 % | 34.4x | 0.0 % |

The advantage grows with field size, because a fixed-size obstacle spans a
roughly fixed *number* of scanlines while the tour that must be re-ordered grows
with the field. On the small Fields2Benchmark fields (median 2.1 ha, about 25
strokes) the same measurement gives a 4.2x median speed-up against a full
replan, or 2.5x against a full replan whose heading is already frozen.

Run `python experiments/exp_scaling.py` and `python experiments/exp_incremental.py`.

## Head-to-head against Fields2Cover

`experiments/exp_compare.py` scores both planners with **one** piece of code
(`metrics.score_solution`) on identical projected geometry, so no difference can
come from two libraries defining "coverage" differently. **All 350 real fields**,
6 m swath, 6 m headland, and **matched turn kinematics**: both sides use a 2.0 m
minimum turning radius. Medians:

| | cppclip | Fields2Cover 2.1.1 (snake) |
|---|---|---|
| coverage | **0.9868** | 0.9847 |
| total driven distance | **4016 m** | 4338 m |
| non-working ratio | **8.1 %** | 16.1 % |
| overlap | 3.35 % | **1.69 %** |
| planning time | **0.133 s** | 0.211 s |

Distance ratio cppclip / Fields2Cover: median **0.937** (p10 0.834, p90 0.986).

Matching the turn model matters: straight transit connectors understate the
driven distance by **1.8 %** at a 2 m radius and 6.9 % at 4 m
(`experiments/exp_turn_radius.py`). Before that correction the ratio reads 0.922
instead of 0.937. The only metric Fields2Cover wins is overlap, on which it
double-covers the seams between passes less than this planner's tightly clipped
strokes and concentric headland loops do.

## Reproducing the comparison

Fields2Cover does not install on Windows from PyPI (sdist only, Linux/macOS
classifiers) and needs GDAL/GEOS/Eigen/Boost/TBB/OR-Tools. The container route
that works on this machine:

```bash
bash tools/setup_fields2cover.sh                     # one-time, idempotent
python experiments/export_cppclip.py --limit 400 --min-area-ha 0.0
docker.exe run --rm -v "C:\Users\666\Desktop\CPP:/work" -w /work \
    fields2cover:2.1.1 python3 -u /work/tools/f2c_benchmark.py
python experiments/exp_compare.py
```

See `tools/README_fields2cover.md` for the details and the traps.

## Data

`data/fields2benchmark/` holds the **350 real fields** of Fields2Benchmark
(Mier et al., 2025), Zenodo DOI
[10.5281/zenodo.14524734](https://doi.org/10.5281/zenodo.14524734) - plain WKT
in EPSG:4326, 140 Dutch / 113 Lithuanian / 97 Estonian, 49 of them with genuine
interior rings. `io_fields.py` projects each field into a local tangent plane
(metres per degree from the WGS84 series expansion) so that no pyproj/GDAL
dependency is needed. See `data/DATASETS.md` for provenance, licences and the
other datasets that were retrieved.

**Licence note:** the Zenodo deposit is CC BY 4.0, but the dataset's own README
records mixed upstream terms. The 113 `lt_` fields are *non-commercial use only*.
The clean subset is `nl_` plus `ee_`.

## Calibrated parameters

Two knobs in `IncrementalPlanner` were chosen by measurement, not by taste
(`experiments/exp_ablation_repair.py`):

* `global_repair_fraction = 0.5` - above this fraction of inserted strokes the
  tour is re-solved globally. Ablation: 0.0 gives 100 % global re-solves and no
  speed-up at all (1.07x); 0.5 gives 1 % global re-solves and a 1.46x speed-up
  at a path penalty of -0.02 %.
* `repair_window = 4` - the 2-opt/Or-opt window around a perturbation.
  4 gives 2.00x speed-up at +0.12 % median path penalty; 20 gives 1.30x at
  -0.02 %. Beyond 8 the extra quality stops paying for the time.

## Limitations

* **Turn kinematics: forward-only.** `turns.py` solves Dubins in closed form and
  every path is verified to reach its goal (5e-14 m) and to be no longer than
  any rival word. **Reeds-Shepp is not implemented**, deliberately: a subset of
  the 48 words is an upper bound, not an approximation of the optimum. The
  concrete cost is that below `w = 2r` a fishtail or three-point turn can beat
  the omega loop this module reports, so turn lengths in that regime are an
  upper bound.
* **Non-overlapping obstacle assumption.** The even-odd fast path is exact only
  for ring sets whose rings do not cross. Dilated obstacles that touch are
  merged into groups to preserve this; genuinely self-overlapping input must be
  normalised (GEOS `make_valid`) first.
* **Percolation.** When in-field obstacles are closer together than twice the
  headland inset, their dilated shapes merge into one component and later
  arrivals touching that component cost more than isolated ones would.
* **Single vehicle.** No multi-robot partitioning, no refill or capacity
  constraints.
* Coverage is about 0.98 rather than 1.0 on non-convex fields; the residual sits
  in the reflex corners that axis-aligned swaths plus concentric offsets do not
  reach.

## References

The verified bibliography, including corrections to several widely repeated
citations, is in [`notes/LITERATURE.md`](notes/LITERATURE.md). Key sources:

* Mier, G., Valente, J., & de Bruin, S. (2023). *Fields2Cover: An Open-Source
  Coverage Path Planning Library for Unmanned Agricultural Vehicles.* IEEE RA-L
  8(4), 2166-2172. [10.1109/LRA.2023.3248439](https://doi.org/10.1109/LRA.2023.3248439)
* Mier, G., Casado Fauli, A. M., Valente, J., & de Bruin, S. (2025).
  *Fields2Benchmark.* Smart Agricultural Technology 12, 101156.
  [10.1016/j.atech.2025.101156](https://doi.org/10.1016/j.atech.2025.101156)
* Jayalakshmi, K. P., Nair, V. G., & Sathish, D. (2025). *A Comprehensive Survey
  on Coverage Path Planning for Mobile Robots in Dynamic Environments.* IEEE
  Access 13, 60158-60185. [10.1109/ACCESS.2025.3556446](https://doi.org/10.1109/ACCESS.2025.3556446)
* Choset, H. (2000). *Coverage for robotics: a survey of recent results.*
  Annals of Mathematics and Artificial Intelligence 31, 113-126.
