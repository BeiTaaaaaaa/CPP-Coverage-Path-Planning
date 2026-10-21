"""Exchange format for the cppclip <-> Fields2Cover comparison.

A benchmark is only meaningful if both systems see the same geometry and are
scored by the same code.  So the comparison does not let each library compute
its own metrics: cppclip exports the *projected metric* field geometry, the
Fields2Cover run consumes exactly those coordinates and writes back its raw
swaths and path, and a single evaluator then scores both.

Layout (under ``results/f2c_io``)::

    fields.json          {name: {"outer": [[x,y],...], "holes": [[[x,y],...]], "area": m2}}
    cppclip/<name>.json  {"swaths": [[[x0,y0],[x1,y1]], ...], "headland_loops": [[[x,y],...], ...],
                          "path": [[x,y],...], "time_s": float}
    fields2cover/<name>.json   the same keys, written inside the container

``swaths`` are the working strokes only (implement down); ``headland`` is the
concatenated perimeter loops; ``path`` is the full driven polyline, transit
included.  Every length is in metres.
"""

from __future__ import annotations

import json
from pathlib import Path

from cppclip import geometry as G
from cppclip.fields import Field

from common import ROOT

IO_DIR = ROOT / "results" / "f2c_io"


def ensure_io_dirs() -> dict[str, Path]:
    dirs = {
        "root": IO_DIR,
        "cppclip": IO_DIR / "cppclip",
        "fields2cover": IO_DIR / "fields2cover",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    return dirs


def field_to_dict(field: Field) -> dict:
    """Everything Fields2Cover needs, in metres, in the planner's own frame."""
    outer = []
    holes = []
    for poly in G.iter_polygons(field.boundary):
        outer.append([[float(x), float(y)] for x, y in poly.exterior.coords])
        for interior in poly.interiors:
            holes.append([[float(x), float(y)] for x, y in interior.coords])
    return {
        "outer": outer,
        "holes": holes,
        "area": float(field.boundary.area),
        "n_vertices": int(sum(len(r) for r in outer) + sum(len(r) for r in holes)),
    }


def export_fields(fields: list[Field]) -> Path:
    """Write the shared geometry file and return its path."""
    dirs = ensure_io_dirs()
    payload = {f.name: field_to_dict(f) for f in fields}
    path = dirs["root"] / "fields.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    print(f"[io] wrote {len(payload)} fields -> {path}")
    return path


def _as_points(seq) -> list[list[float]]:
    return [[float(p[0]), float(p[1])] for p in seq]


def write_solution(system: str, name: str, *, swaths, headland_loops, path, time_s: float,
                   extra: dict | None = None) -> Path:
    """Persist one system's solution in the shared format.

    ``headland_loops`` is a list of loops, and the format keeps it that way.  A
    flat point list cannot distinguish "one loop" from "several loops joined by
    straight lines", and the scorer has no way to tell the joining segments from
    driven path -- so it sweeps and measures them.  Flattening is available to a
    reader that wants it via the ``headland`` key, which is written for the
    convenience of anything that only draws the outline.
    """
    dirs = ensure_io_dirs()
    loops = [_as_points(loop) for loop in headland_loops]
    payload = {
        "system": system,
        "field": name,
        "swaths": [
            [[float(s[0][0]), float(s[0][1])], [float(s[1][0]), float(s[1][1])]]
            for s in swaths
        ],
        "headland_loops": loops,
        "headland": [pt for loop in loops for pt in loop],
        "path": _as_points(path),
        "time_s": float(time_s),
    }
    if extra:
        payload.update(extra)
    out = dirs[system] / f"{name}.json"
    out.write_text(json.dumps(payload), encoding="utf-8")
    return out


def read_solution(system: str, name: str) -> dict | None:
    path = IO_DIR / system / f"{name}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_exported_fields() -> dict:
    path = IO_DIR / "fields.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} missing; run the exporter first")
    return json.loads(path.read_text(encoding="utf-8"))
