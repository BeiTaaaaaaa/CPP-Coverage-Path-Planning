# Fields2Cover side of the CPP head-to-head benchmark

Runner: `tools/f2c_benchmark.py`, executed inside the `fields2cover:2.1.1`
container. Results: `results/f2c_io/fields2cover/` (60 × 2 JSON) +
`results/f2c_io/fields2cover_summary.json`.

## Exact command

```powershell
& 'C:\Program Files\Docker\Docker\resources\bin\docker.exe' run --rm `
    -v 'C:\Users\666\Desktop\CPP:/work' -w /work fields2cover:2.1.1 `
    python3 -u /work/tools/f2c_benchmark.py
```

## What is computed per field

| step | call |
| --- | --- |
| field | `f2c.Cells` from `outer` + `holes` (metres, no reprojection) |
| headland | `HG_Const_gen().generateHeadlands(cells, 6.0)` |
| headland cover | `HG_Const_gen().generateHeadlandSwaths(cells, 6.0, 1, True)[0]` — the 6 m band as one ring; its loops are the driven centre lines |
| swath angle | `computeBestAngle(OBJ_NSwath, 6.0, cell)` on a 7.5° grid (same objective/grid as cppclip's `angle_deg`) |
| mainland swaths | `SG_BruteForce().generateSwaths(angle, 6.0, cell)`, every cell of the 6 m inset |
| ordering A | headland lap + `RP_Snake().genSortedSwaths(...)` → `route: "snake"` |
| ordering B | headland lap + OR-Tools order from `RP_RoutePlannerBase().genRoute(headland_ring, swaths)` → `route: "ortools"` |
| path | `PP_PathPlanning().planPath(robot, swaths, PP_DubinsCurves())`, `Robot(2.0, 6.0)`, `setMinTurningRadius(2.0)` |
| working/transit | from `PathState.type` (`SWATH=1`, `TURN=2`, `HL_SWATH=3`) and `PathState.len` |
| coverage | union of `Swath.areaCovered(field)` over the driven strokes / field area |

Output files: `<name>.json` = snake, `<name>.ortools.json` = OR-Tools.
`path` is the full dense driven polyline; `route_polyline` is the sparse
stroke-endpoint polyline that mirrors what cppclip's `path` key contains.

## Result of the sweep

* 60 fields attempted, **60 OK, 0 failed**; every field solved by both orderings.
* 7 fields have a 6 m inset that splits into 2–4 cells; all cells are swathed
  (recorded in `notes`).

| median | cppclip | f2c snake | f2c ortools |
| --- | --- | --- | --- |
| working length [m] | 3437.8 | 3411.7 | 3411.7 |
| coverage | 0.9867 | 0.9849 | 0.9849 |
| n_swaths | 25 | 25 | 25 |
| planning time [s] | 0.103 | 0.247 | 0.280 |
| full path [m] | — | 4351.5 | 3995.2 |
| transit [m] | — | 891.2 (19.9 %) | 547.5 (11.6 %) |

Working length is 1.8 % shorter than cppclip's overall (median ratio 0.9817,
shorter in 58/60); swinging the swath angle agrees exactly in 45/60 fields and
within one 7.5° step in 58/60; OR-Tools ordering shortens the path in 59/60.

## Findings worth keeping

1. **Upstream bug**: `RP_Snake().genSortedSwaths()` **segfaults** when given
   exactly one swath (0 and 2+ are fine) — reproduced with
   `env/degenerate.py 1 snake` → exit 139. The runner guards this case and
   isolates every field in a child process so a crash cannot abort the sweep.
2. **Reference-counting trap**: keeping `Swath` objects obtained from
   `route.getVectorSwaths()` without copying them (and without keeping the
   returned vector proxy alive) makes the process segfault later; the runner
   copies every swath.
3. **cppclip's `working_length` over-counts multi-loop headlands**: for the 11
   fields where the headland consists of several loops (holes / pinched
   inset), `working_length − Σ swath lengths` equals the perimeter of the
   *concatenated* loop point list, i.e. it includes the straight jumps between
   loops (71–260 m per field). Correcting for that brings the ratio on those
   fields to 0.987, the same as on the 49 clean fields.
4. The F2C headland loop is **bit-identical** to cppclip's on 49/60 fields; on
   the other 11 the vertex sets coincide exactly but the loops are
   concatenated in a different order (see 3).
5. `generateHeadlands(cells, 6.0)` can return several cells for a pinched
   field; swathing only `getGeometry(0)` silently leaves the remainder
   uncovered — this cost ~0.2 coverage points on the affected fields.
6. `f2c.Visualizer.save()` needs `gnuplot-nox` in the image (already added).
