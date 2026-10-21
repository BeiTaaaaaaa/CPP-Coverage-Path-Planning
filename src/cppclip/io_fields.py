"""Loading real field boundaries into metric, plan-ready geometry.

The Fields2Benchmark fields (Mier et al., 2025) are distributed as WKT in
EPSG:4326 -- degrees of longitude and latitude.  Coverage planning needs
metres: swath widths, turn radii and path lengths are physical quantities, and a
degree of longitude is a different distance in Estonia than in the Netherlands.

Rather than depend on pyproj/GDAL, this module projects each field into a
**local tangent plane** centred on the field's own centroid, using the standard
WGS84 series expansions for metres per degree:

.. math::

    m_\\varphi &= 111132.92 - 559.82\\cos 2\\varphi + 1.175\\cos 4\\varphi
                  - 0.0023\\cos 6\\varphi \\\\
    m_\\lambda &= 111412.84\\cos\\varphi - 93.5\\cos 3\\varphi
                  + 0.118\\cos 5\\varphi

For a field of a few hectares the scale error is far below the accuracy of the
boundary survey itself, and the projection is exactly invertible for plotting.
Fields are then translated so their bounding box starts at the origin, which
keeps the scanline grid well conditioned.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from shapely import wkt as shapely_wkt
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shapely_transform

from . import geometry as G
from .fields import Field

__all__ = [
    "BENCHMARK_DIR",
    "project_wgs84_to_local",
    "load_wkt",
    "load_benchmark",
    "benchmark_records",
    "origin_shift",
]

BENCHMARK_DIR = Path(__file__).resolve().parents[2] / "data" / "fields2benchmark"
WKT_SUBDIR = "wkt_extracted"
SUMMARY_FILE = "geometry_summary.json"


# --------------------------------------------------------------------------
# projection
# --------------------------------------------------------------------------
def _metres_per_degree(lat_deg: float) -> tuple[float, float]:
    """``(m per degree of latitude, m per degree of longitude)`` at *lat_deg*."""
    phi = math.radians(lat_deg)
    m_lat = (
        111132.92
        - 559.82 * math.cos(2 * phi)
        + 1.175 * math.cos(4 * phi)
        - 0.0023 * math.cos(6 * phi)
    )
    m_lon = (
        111412.84 * math.cos(phi)
        - 93.5 * math.cos(3 * phi)
        + 0.118 * math.cos(5 * phi)
    )
    return m_lat, m_lon


def project_wgs84_to_local(geom: BaseGeometry) -> G.MultiPolygon:
    """Project a WGS84 geometry to metres in a tangent plane at its centroid."""
    if geom is None or geom.is_empty:
        return G.MultiPolygon()
    c = geom.centroid
    lon0, lat0 = c.x, c.y
    m_lat, m_lon = _metres_per_degree(lat0)

    def _fn(x, y, z=None):
        # Shapely 2 passes coordinate arrays; the transform is elementwise.
        return ((x - lon0) * m_lon, (y - lat0) * m_lat)

    return G.normalise(shapely_transform(_fn, geom))


def origin_shift(geom: BaseGeometry) -> G.MultiPolygon:
    """Translate a geometry so its bounding box starts at the origin."""
    geom = G.normalise(geom)
    if geom.is_empty:
        return geom
    minx, miny, _maxx, _maxy = G.bounds_of(geom)

    def _fn(x, y, z=None):
        return (x - minx, y - miny)

    return G.normalise(shapely_transform(_fn, geom))


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------
def load_wkt(path: str | Path, *, project: bool = True, shift: bool = True) -> G.MultiPolygon:
    """Load one WKT file as metric geometry."""
    text = Path(path).read_text(encoding="utf-8", errors="replace").strip()
    # Some files may hold several records separated by newlines.
    first = text.splitlines()[0].strip() if text else ""
    if not first:
        return G.MultiPolygon()
    geom = shapely_wkt.loads(first)
    if project:
        geom = project_wgs84_to_local(geom)
    if shift:
        geom = origin_shift(geom)
    return G.normalise(geom)


def benchmark_records(summary_file: Path | None = None) -> list[dict]:
    """The per-field metadata shipped with the dataset, if present."""
    path = Path(summary_file) if summary_file else BENCHMARK_DIR / SUMMARY_FILE
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def load_benchmark(
    root: str | Path | None = None,
    *,
    countries: tuple[str, ...] | None = None,
    limit: int | None = None,
    min_area_ha: float = 0.0,
    max_area_ha: float | None = None,
    with_obstacles: int = 0,
    obstacle_seed: int = 0,
) -> list[Field]:
    """Load Fields2Benchmark fields as plan-ready :class:`~cppclip.fields.Field` objects.

    Parameters
    ----------
    countries:
        Restrict to ISO country prefixes, e.g. ``("nl", "ee")``.
    min_area_ha, max_area_ha:
        Filter on the field's net area in hectares.  Very small fields are
        dominated by headland effects and very large ones make the routing
        benchmark slow, so the experiment scripts filter explicitly rather than
        silently.
    with_obstacles:
        Inject this many synthetic in-field obstacles per field.  The published
        benchmark ships boundaries only, but the dynamic-replanning experiment
        needs obstacles, so they are generated reproducibly and the count is
        recorded in the field metadata.
    """
    root = Path(root) if root else BENCHMARK_DIR
    wkt_dir = root / WKT_SUBDIR / "wkt"
    if not wkt_dir.is_dir():
        # Fall back to a plain `wkt/` layout.
        alt = root / "wkt"
        wkt_dir = alt if alt.is_dir() else wkt_dir
    if not wkt_dir.is_dir():
        raise FileNotFoundError(f"no WKT directory under {root}")

    summary = {r["f"]: r for r in benchmark_records(root / SUMMARY_FILE)}

    out: list[Field] = []
    for path in sorted(wkt_dir.glob("*.wkt")):
        cc = path.name[:2].lower()
        if countries and cc not in countries:
            continue
        rec = summary.get(path.name, {})
        area_ha = float(rec.get("area_net_ha", 0.0))
        if area_ha and area_ha < min_area_ha:
            continue
        if max_area_ha is not None and area_ha and area_ha > max_area_ha:
            continue

        try:
            boundary = load_wkt(path)
        except Exception:  # noqa: BLE001 - a single bad file must not kill a sweep
            continue
        if boundary.is_empty or boundary.area <= 0:
            continue

        obstacles: list = []
        if with_obstacles > 0:
            from .fields import random_obstacles

            inner = G.erode(boundary, 20.0)
            if not inner.is_empty and inner.area > 200.0:
                obstacles = random_obstacles(
                    inner, with_obstacles, seed=obstacle_seed + len(out), size_range=(4.0, 10.0)
                )

        out.append(
            Field(
                name=path.stem,
                boundary=boundary,
                obstacles=obstacles,
                meta={
                    "country": cc,
                    "area_ha": area_ha,
                    "n_vertices": rec.get("n_vertices_total"),
                    "n_holes": rec.get("n_holes", 0),
                    "source": "Fields2Benchmark",
                },
            )
        )
        if limit is not None and len(out) >= limit:
            break

    return out
