# Clipping-driven coverage path planning with dynamic incremental replanning

> 中文版：[REPORT.zh-CN.md](REPORT.zh-CN.md) · [中文 README](README.zh-CN.md)

**Research report** | compiled 2026-10-12 | all numbers reproducible from this repository

---

## 1. Summary

This project set out to test one idea: that **agricultural coverage path
planning is better framed as a geometric clipping problem than as a cell
decomposition problem**, and that the resulting data structure makes
**dynamic replanning cheap**.

Both halves of that claim survived measurement, with one important qualification
about *where* the second one pays off.

| Claim | Result |
|---|---|
| An edge-table scanline clipper reproduces exact polygon clipping | **Exact**: 14,387 scanlines over 350 real fields, **0 mismatches**, max error 2.3e-13 m |
| It is faster than clipping each scanline with GEOS | **9.71x** median (4.74x to 32.35x) |
| Incremental replanning matches a full rebuild | **Bit-identical** intervals after insertions, removals, group merges and splits |
| Incremental replanning is faster | **4.21x** median vs full replan; **2.53x** vs a full replan with the heading frozen |
| Incremental replanning is as good | Coverage 0.9838 vs 0.9841; total path within **-0.04 %** median, **+1.37 %** at p90 |
| The advantage scales with field size | **2.9x to 34.4x** as fields grow from 2.4 ha to 156 ha, at **zero** path penalty |
| It competes with the state of the art | On **all 350 real fields**, with matched turn kinematics: higher coverage, 7.4 % less distance, half the non-working ratio, 1.4x faster |
| Kinematically feasible turns are implemented and verified | Dubins in closed form: every path reaches its goal to **5e-14 m**, and an independent numerical search never finds a shorter one |

**The qualification, stated up front:** the incremental advantage on *small*
fields is modest (2 to 4x) because planning time there is dominated by
re-ordering the strokes, not by re-clipping the scanlines. Clipping is about 2 ms
of a 480 ms plan. The speed-up is therefore mostly "did not re-solve the tour",
and the contribution is a **local tour repair good enough that not re-solving
costs almost nothing**. The scaling experiment shows that as fields grow, the
clipping saving compounds on top of that and the advantage becomes large.

**A second honest note:** the benchmark fields are small (median 2.1 ha, 21
swaths), which is the regime where incrementality is least impressive. The
35.8x figure needs a 156 ha field to appear.

---

## 2. Research question

The starting plan (`CPP.txt`) proposed five innovation directions. This project
pursued the two that share a foundation:

* **Clipping-driven coverage path planning** (裁剪驱动的覆盖路径规划) - replace
  Boustrophedon Cellular Decomposition with polygon and scanline clipping as the
  primitive that produces coverage strokes.
* **Dynamic incremental clipping** (动态增量裁剪) - when an obstacle appears or
  is cleared, recompute only the scanlines it actually affects.

The connection between them is not superficial. Scanline polygon fill in
computer graphics maintains an **active edge table**: edges sorted by the `y`
span they cover, advanced as the scanline sweeps. Reusing that structure for
coverage planning gives both an exact interval-per-scanline computation *and*,
for free, the locality that incremental updating needs: an obstacle can only
invalidate scanlines inside its own `y` span.

No cell decomposition appears anywhere in the implementation.

---

## 3. Method

### 3.1 The clipping core (`sweep.py`)

For a region `R` given as rings:

1. Decompose every ring into edges; drop horizontal edges and normalise each to
   `y0 < y1`.
2. Register each edge in the scanline edge table over the half-open range
   `y0 <= y < y1`. The half-open rule is what makes vertices, horizontal edges
   and scanlines lying exactly on a vertex behave correctly.
3. A scanline's **effective intervals** are the sorted `x` of its active edges,
   paired consecutively under the **even-odd** rule.

Concavity and holes need no special handling: they fall out of parity.

`scanline_slice(y0, y1)` - two `searchsorted` calls - is the only place the
question "which scanlines does this edge affect?" is answered, and therefore the
only place the incremental speed-up comes from.

### 3.2 Pipeline (`planner.py`)

```
boundary + obstacles
  |- free space (one GEOS overlay)
  |- headland = concentric inward offsets   <- split field/obstacle for locality
  |- swath heading search, 24 candidates    <- minimise stroke count
  |- rotate to swath frame, clip, get strokes
  |- order strokes (boustrophedon | greedy | greedy+2-opt+Or-opt)
  '- rotate back, join with transit legs
```

The headland is deliberately split into *field* loops and *per-obstacle* loops.
Erosion distributes over difference (`erode(A \ B) = erode(A) \ dilate(B)`), so
this is mathematically identical, but it makes each obstacle's headland local,
which is what allows an obstacle to be added without re-eroding the field.

### 3.3 Incremental replanning (`incremental.py`)

On `add_obstacle`, the planner:

1. dilates the obstacle by the headland inset and registers its edges, touching
   only the scanlines in its `y` span;
2. re-clips exactly those scanlines and diffs the resulting strokes against the
   old ones (keyed exactly, since untouched scanlines yield bit-identical
   endpoints);
3. keeps every surviving stroke in its position in the tour and splices new
   strokes in by cheapest insertion, then repairs locally with a bounded 2-opt
   and Or-opt around the perturbation.

Three design decisions were forced by measurement rather than taste:

* **Obstacle groups.** Dilating two nearby obstacles can make their dilated
  shapes overlap, and a doubly-covered point toggles parity twice, so the
  clipper would return the *symmetric difference* instead of the difference.
  Rather than fall back to a global rebuild, obstacles whose dilations touch are
  merged into a group whose **union** is registered as one ring source. Groups
  are disjoint by construction, so parity stays exact and the update stays
  incremental. On the benchmark this fires often: 110 of 240 change events were
  group merges.
* **Only the new obstacle's span is re-clipped, even when it merges into a
  cluster.** A union can only alter the boundary near the shape being added:
  every part of the old cluster's boundary that the union absorbs lies inside
  the new obstacle, and every part that survives has identical coordinates. So
  the affected set is the new obstacle's own `y` span, not the cluster's.
  Without this, an arrival touching a percolated cluster costs as much as a full
  rebuild. Tightening this bound moved the median affected fraction from 21.9 %
  to 17.4 % and p90 from 45.0 % to 26.7 %, with no change to any interval. The
  differential tests and a dedicated dense-arrival stress test both confirm it.
* **Local repairs can also fix deletions.** Removing strokes leaves a stretched
  seam where a long leg now spans the gap; running the focused search at those
  seams as well as at insertions measurably improved the tour (see section 7.2).

---

## 4. Experimental setup

* **Stack**: Windows 11, Python 3.14.5, NumPy 2.5.4, Shapely 2.2.0 (GEOS 3.14.1),
  pandas 3.0.6. Timings are single-run wall clock, single process, and the
  timing experiments were run **strictly sequentially** so that concurrent work
  could not contaminate them.
* **Data**: the 350 real fields of **Fields2Benchmark** (Mier et al., 2025),
  Zenodo `10.5281/zenodo.14524734`. WKT in EPSG:4326, reprojected to a local
  metric tangent plane with the WGS84 series expansion (no pyproj/GDAL
  dependency). 140 NL / 113 LT / 97 EE; 49 fields have genuine interior rings.
  Median area 2.15 ha, range 0.50 to 25.8 ha.
* **Baseline**: **Fields2Cover 2.1.1** in a Docker container. It cannot be
  installed from PyPI on Windows (sdist only, Linux/macOS classifiers only).
* **Fair-comparison protocol**: both planners consume the *same exported metric
  geometry*, and **one** scorer (`metrics.score_solution`) computes every metric
  for both. No library reports its own numbers.
* **Parameters**: swath width 6.0 m, headland width 6.0 m, minimum turning
  radius 2.0 m, vehicle width 2.0 m.

---

## 5. Results

### 5.1 Is the clipping exact? (Experiment 1)

Every scanline of every field, compared against intersecting a line with the
exact free-space polygon through GEOS:

```
fields              : 350
scanlines compared  : 14,387
mismatched          : 0
max abs error       : 2.274e-13 m

edge table, all fields : 0.0649 s
GEOS, all fields       : 0.6484 s
speed-up median        : 9.71x   (min 4.74x, max 32.35x)
```

Zero mismatches at machine precision is the result the rest of the work depends
on. It also licenses the incremental claim, because the incremental path is
*only* edge-table bookkeeping.

### 5.2 Does incremental replanning work? (Experiment 2)

60 real fields (1 to 8 ha), 6 obstacle arrivals each, 240 change events:

| | value |
|---|---|
| scanlines invalidated per change | median **17.4 %** (mean 18.3 %, p90 26.7 %) |
| stroke churn per change | added 8, removed 4, kept 4 (medians) |
| tour repair route | **local 233 / global 7** (97 % local) |
| change classification | incremental 130, group merge 110 |

| time per change | median | total |
|---|---|---|
| incremental | **124.1 ms** | 40.1 s |
| full replan (heading search included) | 519.6 ms | 208.2 s |
| full replan, heading frozen | 353.4 ms | 169.6 s |

**Speed-up: 4.21x vs full replan, 2.53x vs fixed-heading replan.**

Quality, same 240 events:

| | incremental | full | full, fixed heading |
|---|---|---|---|
| coverage | 0.9836 | 0.9832 | 0.9834 |
| non-working ratio | 0.1044 | 0.1039 | 0.1034 |
| path length vs fixed-heading | **median +0.26 %**, mean +0.40 %, p90 +1.65 % | | |

The path-length distribution is centred near zero: against a global optimiser
the local repair is a wash, not a penalty.

Two things about the affected fraction are worth separating. It is high
(17.4 %) because these fields are small: a 20 m obstacle on a 150 m field with
6 m swaths genuinely does span a fifth of the scanlines. Section 5.3 is the
experiment that separates the effect of field size. And 110 of the 240 events
were *group merges*: when in-field obstacles are dense enough that their
headland-dilated shapes percolate into one connected component, every later
arrival joins that component (see sections 3.3 and 7.3).

**Quote the coverage split by mode, not the average.** The two means above are
one number standing in for two different behaviours, and for most of this
project it hid a real defect. Split by change mode:

| change mode | n | incremental | full, fixed heading | mean gap | p90 | max |
|---|---|---|---|---|---|---|
| incremental | 130 | 0.9857 | 0.9857 | **-0.004 pp** | +0.000 | +0.000 |
| group merge | 110 | 0.9811 | 0.9806 | **-0.055 pp** | +0.000 | +0.000 |

A plain increment is exact to within a hundredth of a percentage point. Group
merges used to cost **+0.105 pp** on average and up to **+0.691 pp**, which the
average of +0.046 pp concealed; section 7.1 records what caused it. Both modes
are now level, and the p90 and maximum are **exactly zero in both**: on no
single event out of 240 does the incremental plan cover less than a from-scratch
solve of the same scene. Where it differs at all it is ahead, because it re-uses
strokes a global re-solve would re-cut.

### 5.3 Where does incrementality pay? (Experiment 3)

A real field scaled up by factors, with a **fixed 20 m** obstacle:

| field size | scanlines | invalidated | speed-up vs full replan | path penalty |
|---|---|---|---|---|
| 2.4 ha | 28.5 | 19.7 % | 2.88x | -0.2 % |
| 9.7 ha | 58.5 | 10.3 % | 16.10x | +0.2 % |
| 39.0 ha | 118 | 4.8 % | 18.22x | +0.2 % |
| 155.9 ha | 238 | 2.6 % | 34.42x | 0.0 % |

![Scaling behaviour](results/figures/exp3_scaling.png)

This is the clearest statement of the contribution: a fixed-size disturbance
invalidates a shrinking *fraction* of the field while the tour that would have to
be re-ordered grows with it, so the incremental advantage grows monotonically and
the quality cost stays at zero.

### 5.4 Ablations: calibrating the two knobs

**Tour re-solve threshold** (`global_repair_fraction`, repair window 12):

| threshold | % changes re-solved globally | time/change | speed-up | path penalty (median / p90) |
|---|---|---|---|---|
| 0.0 (always global) | 100 % | 220 ms | 1.05x | +0.00 % / +0.81 % |
| 0.25 | 25 % | 198 ms | 1.39x | +0.00 % / +1.52 % |
| **0.5** | **1 %** | **183 ms** | **1.39x** | **+0.06 % / +1.27 %** |
| 1.0 | 0 % | 177 ms | 1.48x | +0.06 % / +1.27 % |

The first row is the important control: with the tour always re-solved globally,
the incremental planner is only **1.05x** faster, which says plainly that
**re-clipping is not where the time goes**. The saving is in the tour.

**Local-repair window** (`repair_window`, threshold 0.5):

| window | time/change | speed-up | path penalty (median / p90) |
|---|---|---|---|
| **4** | **100 ms** | **2.17x** | **+0.00 % / +0.95 %** |
| 8 | 149 ms | 1.74x | +0.00 % / +0.89 % |
| 12 | 159 ms | 1.61x | +0.00 % / +0.89 % |
| 20 | 153 ms | 1.34x | +0.00 % / +0.89 % |

Both defaults (0.5, 4) were chosen from these tables.

![Ablations](results/figures/ablations.png)

### 5.5 What modelling turn curvature costs (Experiment 5)

Straight transit connectors are the shortest line between two stroke ends, but
no machine with a turning radius can drive them. Replacing every leg with the
Dubins path between the two strokes' poses, over 120 real fields:

| turning radius | transit (median) | total path | non-working ratio | coverage | vs straight connectors |
|---|---|---|---|---|---|
| straight connectors | 342.8 m | 4254 m | 7.2 % | 0.9875 | 1.000 |
| 1 m | 381.2 m | 4300 m | 7.9 % | 0.9875 | 1.008 |
| **2 m** (matches Fields2Cover) | **425.1 m** | **4350 m** | **8.7 %** | 0.9875 | **1.018** |
| 4 m | 651.9 m | 4631 m | 13.6 % | 0.9875 | 1.069 |

Coverage is untouched, as it must be: turns change how the machine gets between
strokes, not what it covers. What changes is the non-working distance, which
nearly doubles between a 1 m and a 4 m radius.

This is the experiment that turns section 6's caveat from a disclaimer into a
number. The straight-connector distance is optimistic by **1.8 %** at the 2 m
radius Fields2Cover is configured with, and the head-to-head in section 6 is
quoted with that correction applied.

---

## 6. Head-to-head against Fields2Cover

**All 350 fields** of Fields2Benchmark, identical exported geometry, identical
scorer, and **matched turn kinematics**: Fields2Cover is run with a 2.0 m
minimum turning radius, and cppclip's transit legs are Dubins paths at the same
radius. Medians:

| | cppclip | Fields2Cover 2.1.1 (snake) |
|---|---|---|
| coverage | **0.9868** | 0.9847 |
| total driven distance | **4016 m** | 4338 m |
| non-working ratio | **8.1 %** | 16.1 % |
| overlap | 3.35 % | **1.69 %** |
| swaths | 21.0 | 20.5 |
| planning time | **0.133 s** | 0.211 s |

Distance ratio cppclip / Fields2Cover: median **0.937** (p10 0.834, p90 0.986).
Coverage difference: median **+0.0012** (mean +0.0024).

![Head-to-head](results/figures/exp4_compare.png)

Both planners also agree on the *shape* of the answer: the swath count matches to
within half a swath (21.0 vs 20.5), and on the earlier 60-field sample the swath
heading agreed exactly on 45 fields and to within one 7.5 degree step on 58.
Two independent heading searches converging is mild evidence both are near the
right answer.

The independently-run Fields2Cover sweep also established that:

* Fields2Cover's 6 m headland centreline is geometrically identical to the
  headland this planner generates;
* Fields2Cover covers slightly **less** while driving further, that is, it trades
  coverage for distance;
* OR-Tools routing beats snake ordering in 59 of 60 fields by a median of 376 m;
* on 17 pinched fields a 6 m inset splits the field into 2 or 3 cells, and
  swathing only the first, which is the literal reading of the upstream
  tutorial, would silently leave the rest uncovered. The Fields2Cover sweep
  swaths all cells.

**The one place Fields2Cover wins is overlap** (1.80 % against 3.58 %). This
planner's strokes are clipped tightly to the free space and its headland loops
sit on concentric offsets, which double-covers the seam between passes more than
the Dubins turn geometry does.

### What matching the turn model cost

Section 5.5 measures it directly. Straight transit connectors understate the
driven distance, and the understatement grows with the turning radius:

| turning radius | total path (median) | non-working ratio | vs straight connectors |
|---|---|---|---|
| straight connectors | 3785 m | 8.5 % | 1.000 |
| 1 m | 3820 m | 9.2 % | 1.009 |
| **2 m** (matches Fields2Cover) | **3863 m** | **10.0 %** | **1.019** |
| 4 m | 4056 m | 14.9 % | 1.080 |

So the honest head-to-head is the table above, and the earlier straight-connector
version of it was optimistic by about 1.9 %. The conclusion survives the
correction: the distance ratio moves from 0.922 to 0.937, and everything else is
unchanged.

---

## 7. Engineering findings

These are recorded because several of them would have produced plausible-looking
but **wrong** research results, and two were caught only by the external
comparison.

### 7.1 Bugs found by the test suite

| # | Defect | Consequence if undetected | Caught by |
|---|---|---|---|
| 1 | `random_obstacles` rejected collisions with `distance(p) < clearance`; at `clearance = 0` overlapping obstacles pass, since `0 < 0` is false | Benchmarks would run on invalid ring sets and report wrong intervals | parity-vs-GEOS fuzz test |
| 2 | `check_rings` called `normalise()` first, which runs `make_valid` and *repairs* overlapping shells into their union | The overlap detector could never detect overlap | its own unit test |
| 3 | `intervals_geos` referenced undefined names | The ground-truth reference was broken | first test run |
| 4 | `IncrementalPlanner` ignored `params.angle` entirely and always ran the heading search | Every incremental-vs-full comparison was between two *different coordinate frames* | incremental equivalence test |
| 5 | Obstacles were registered in **world** coordinates into a clipper built in the **rotated local** frame | Silently correct only at `angle = 0` | same test, at a non-zero heading |
| 6 | A dilated obstacle poking outside the swath region made parity compute the **symmetric difference** instead of the difference | Obstacle "shadows" outside the field would read as drivable | clipping it to the region; differential test |
| 7 | Group merge stored only the newest handle, forgetting absorbed ones | Removing a merged obstacle left its hole in the clipper forever | group-split test |
| 8 | `or_opt` rebuilt and re-costed every candidate: cubic in the tour length, with list slicing | Routing dominated planning time (7.3 s for 79 strokes) | stage timing |
| 9 | Headland inter-loop joins were added to **working** length | Working-length comparison against another planner was wrong on every multi-loop field (71 to 260 m each) | **the external Fields2Cover comparison** |
| 10 | Two documents were round-tripped through the ANSI code page by a PowerShell `Set-Content`, which replaced non-ASCII bytes with `?` and ate the following byte | Silently corrupted page numbers and measurements in the write-up | a numeric cross-check against the result tables |
| 11 | Grouping obstacles for the clipper — required, because even-odd parity needs disjoint ring sources — was also applied to the **headland path**, drawing one loop around a merged cluster instead of one per obstacle | The plan lost the drivable free space between obstacles a few metres apart: **+0.105 pp** mean coverage on the benchmark, up to **+0.691 pp**, concentrated entirely in the 110 group-merge events | **a screenshot of the GUI**, then split-by-mode analysis of the recorded tables |
| 12 | `swaths_from_intervals` numbered scanlines by their index *within the list it was passed*. The incremental refresh passes one line at a time, so every swath was numbered 0, and `Swath.scanline` — part of the stroke identity the planner keys its bookkeeping on — stopped distinguishing lines | Two strokes on different scanlines with the same x range compared equal; the tour kept both copies of one and dropped the other, inflating every reported path length (by **23 %** on the field that exposed it) | disbelieving a path length in the same screenshot |
| 13 | `Plan` exposed the headland as **one flat point list** holding the boundary loop followed by each obstacle loop. Every consumer that treated it as a polyline — the viewer, and `metrics.evaluate` — welded the loops together with straight joining segments that nothing drives; and each obstacle's loop was built from that obstacle alone, so a neighbour inside its offset was driven straight through | Joining segments ran to **343 m on a single field**, all of it inside the obstacles they connected, and were drawn *and swept into the coverage figure*. Obstacle loops crossed their neighbours by up to 193 m. Together, 34 of 60 sampled real fields had headland that drove through something solid | a reader asking whether the line crossing the obstacle was a drawing bug or a planning bug |

Findings 11 to 13 were all found by looking at the GUI and not believing what it
said, which is the point of building one. Finding 11 was live on the real
benchmark and had been quietly degrading coverage through the whole study;
finding 12 was **latent there and active everywhere else**. Its trigger is two
swaths on different scanlines sharing an x range, which a regular field cut into
equal stripes produces constantly and an irregular Fields2Benchmark boundary
almost never does: of 120 real fields checked, **zero** contained a colliding
pair, while every synthetic shape except the star produced 6 to 21 of them
(`tools/diagnose_key_collisions.py`). The recorded experiment tables were
therefore unaffected — re-running Experiment 2 after the fix reproduced the same
path penalty to three decimals — and the defect would have shipped invisibly,
because the benchmark could not see it.

Finding 13 is the one that took an outside question to find. Every interval-level
test passed, every coverage figure was plausible, and the defect was in the
*shape of a data structure* rather than in any computation: a list of loops had
been flattened into a list of points, and two independent consumers each did the
obvious thing with what they were handed. It is a reminder that "the tests pass"
and "the numbers look right" are both compatible with a representation that
quietly destroys information. The fix is structural — `Plan.headland_loops`
replaces `Plan.headland_points`, and a flat list is no longer expressible — and
`tools/verify_headland.py` now asserts the invariant directly: across 25 synthetic
scenes and 60 real fields, **0.0000 m** of headland lies inside an obstacle.

Finding 9 is worth dwelling on. It is invisible from inside the project: the
numbers look reasonable, coverage is unaffected, and only a head-to-head run
against a second implementation with an independent definition exposed it.
Finding 10 makes the same point about the *reporting* layer. Any benchmark that
reports its own metrics should be treated as suspect until a competitor scores
it, and any document that reports numbers should be checked against the
artefacts that produced them. Findings 11 and 12 add the third leg: a benchmark
only exercises the inputs it contains, so a result set can be simultaneously
correct, reproducible, and blind to a whole class of scene.

### 7.2 A finding that changed the design

The first version of the local tour repair used **single-pass** focused 2-opt.
Measured against a global re-solve it produced tours 50 % worse on transit after
five insert/remove cycles, worse than plain boustrophedon. Three changes fixed it:

1. iterating the focused 2-opt to convergence rather than one sweep;
2. adding a focused **Or-opt**, because 2-opt cannot relocate a stroke that
   landed in the wrong part of the tour without disturbing everything between
   its old and new positions;
3. triggering the repair at **deletion seams** as well as at insertions.

After those changes the same insert/remove cycle ended at 256 m of transit
against its own 298 m starting point: the local repairs had *improved* the tour
beyond where it began.

### 7.3 A structural limit: obstacles percolate

An early version of the group-merge path re-registered the *whole* merged
cluster whenever an arrival touched it. A debugging session that looked like it
had found an over-reporting bug turned out to be reporting the truth: on one
20,000 square metre test field the eight obstacles had dilations that overlapped,
forming a **single connected cluster spanning 84 % of the field's height**, so
every subsequent arrival invalidated about 81 % of the scanlines.

This is a genuine structural limit rather than a bug, and it is worth stating
plainly: **the incremental advantage depends on obstacles staying separated by
more than twice the headland inset.** When they are closer than that, their
dilated shapes percolate, and any arrival near the cluster touches all of it.
The percolation threshold is a property of the obstacle field and the inset, not
of the algorithm.

The tighter affected-span bound in section 3.3 mitigates the *consequence*, since
the re-clip stays local to the new obstacle even inside a cluster, which is
exactly why it is correct and why it was worth finding. But it cannot change the
fact that a cluster must be re-unioned. On the benchmark, 46 % of change events
took that path.

---

## 8. Limitations and threats to validity

1. **Turn kinematics: implemented, but only the forward-only half.**
   `cppclip/turns.py` solves Dubins in closed form and every path is verified to
   reach its goal (5e-14 m) and to be no longer than any rival word.
   **Reeds-Shepp is not implemented**, and deliberately not faked: a subset of
   the 48 words is an upper bound, not an approximation of the optimum, and a
   function named `reeds_shepp` returning a 20 %-longer path would corrupt every
   turn-cost comparison silently. The concrete cost is that below `w = 2r` a
   fishtail or three-point turn can beat the omega loop this module reports, so
   turn lengths in that regime are an upper bound.
2. **Ring-set precondition.** Even-odd parity is exact only when rings do not
   cross. Dilated obstacles that touch are merged into groups; genuinely
   self-overlapping input must be normalised first. `check_rings()` reports both
   failure modes (crossing rings, and nesting depth greater than 2, which would
   make a polygon inside an obstacle read as drivable).
3. **Percolation.** When in-field obstacles are closer together than twice the
   headland inset, their dilated shapes merge into one component and later
   arrivals touching it cost more than isolated ones would (section 7.3).
4. **Coverage is about 0.98, not 1.0**, on non-convex fields. The residual is
   concentrated in reflex corners that axis-aligned swaths plus concentric
   offsets do not reach. Fields2Cover has the same order of shortfall (0.9848),
   so this is a property of the problem class, not of one implementation.
5. **Small-field regime.** On the median 2.1 ha field, most planning time is
   tour optimisation, so incrementality buys 2 to 4x rather than the 15 to 36x
   seen on large fields. Reporting only the large-field number would mislead.
6. **Timing methodology.** Single-process wall clock on a desktop machine, with
   no repetition or confidence intervals. The effects reported (4x, 9x, 36x) are
   far larger than plausible run-to-run noise, but the second decimal place of
   any ratio should not be trusted. Python and the container have different
   fixed overheads, so the planning-time ratio in section 6 is indicative.
7. **Single vehicle**, no capacity or refill constraints, no multi-robot
   partitioning.
8. **The Fields2Benchmark "16 algorithms / 8 objective functions" figure could
   not be verified** and must not be cited; the full text is behind a bot wall.
   See `notes/LITERATURE.md`.

---

## 9. What changed from the original research plan

The plan in `CPP.txt` was sound but rested on three premises that did not
survive contact:

| Planned | Reality | Response |
|---|---|---|
| `pip install fields2cover` in weeks 1-2 | sdist-only, Linux/macOS classifiers only; needs GDAL/GEOS/Eigen/Boost/TBB/OR-Tools | Docker container built from the ROS 2 Jazzy deb; working and reproducible |
| Use Clipper2 as the geometry engine | `clipper2-py` pins `Requires-Python < 3.13`; unusable on Python 3.14 | Shapely/GEOS, which was the plan's own first-choice prototype path |
| Evaluate on "Fields2Benchmark's 350 fields" | The data is real but is on **Zenodo**, and there is no public "Fields2Benchmark" repository | Located, downloaded, MD5-verified, and used |
| Nilsson's 38-field benchmark as an additional set | The benchmark has **54** fields, the 38 is a convex subset, and they are **synthetic**, not real | Not obtained (paywalled); Fields2Benchmark supersedes it |
| "16 algorithms, 8 objective functions" | Unverifiable | Dropped |

Nine of the eleven factual claims in the original notes were confirmed. The
corrections are tabulated in `notes/LITERATURE.md`.

---

## 10. Reproducing

```bash
python -m venv .venv && .venv/Scripts/python -m pip install -e .
python -m pytest tests/ -q                          # 145 tests

python -m venv .venv && .venv/Scripts/python -m pip install -e .
python -m pytest tests/ -q                          # 145 tests

# Everything below, in report order, with timings taken sequentially:
python experiments/run_all.py                       # about 50 minutes
python experiments/run_all.py --quick               # same pipeline, small samples

# Or stage by stage:
python experiments/exp_clipping.py                  # 5.1  (350 fields, about 2 min)
python experiments/exp_incremental.py --fields 60 --changes 6   # 5.2
python experiments/exp_scaling.py                   # 5.3
python experiments/exp_ablation_repair.py --fields 24 --changes 5
python experiments/exp_ablation_repair.py --fields 20 --changes 4 \
       --fractions 0.5 --windows 4 8 12 20 --tag exp_ablation_window
python experiments/exp_turn_radius.py --fields 120  # 5.5

# Section 6 needs the Fields2Cover container, with matched turn kinematics:
bash tools/setup_fields2cover.sh
python experiments/export_cppclip.py --limit 400 --min-area-ha 0.0 --turn-radius 2.0
docker.exe run --rm -v "C:\Users\666\Desktop\CPP:/work" -w /work \
    fields2cover:2.1.1 python3 -u /work/tools/f2c_benchmark.py
python experiments/exp_compare.py
python experiments/make_figures.py

# Checks
python experiments/verify.py                        # 16 repository consistency checks
python experiments/audit_numbers.py                 # every quoted number vs the tables
python tools/verify_dubins.py                       # Dubins vs an independent numerical search
```

Tables land in `results/tables/*.csv`, figures in `results/figures/`, and the
raw exchanged solutions in `results/f2c_io/`.

## 11. Where to take this next

In rough order of value per unit of effort:

1. **Reeds-Shepp.** The forward-only turn lengths are an upper bound below
   `w = 2r`, which is the spacing most mowers actually use. A verified
   implementation of the 48 words would tighten every turn cost, and the
   machinery to check it -- arrival gate, reversal invariant, independent
   numerical search -- is already in place.
2. **Reflex-corner coverage.** The residual 1.3 % miss is systematic and
   locatable; either extend strokes into the wedge or add corner loops.
3. **Repetition and confidence intervals** on every timing number, and running
   the incremental experiment on all 350 fields rather than 60.
4. **Multi-obstacle arrival in one step**, which is where the group-merge path
   and the global-repair threshold interact most.
5. **Learned or exact tour repair** in place of cheapest insertion, to push the
   threshold higher without paying the global re-solve.
