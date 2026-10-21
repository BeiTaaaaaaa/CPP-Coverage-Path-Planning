"""cppclip -- clipping-driven coverage path planning.

A research toolkit that formulates agricultural coverage path planning as a
*geometric clipping* problem rather than a cell-decomposition problem, and
exploits the resulting scanline edge table to replan incrementally when the
environment changes.

Public surface
--------------
``ScanlineClipper``
    The clipping core: effective intervals (有效区间) per scanline, with
    incremental insert/remove of obstacles.
``geometry``
    Polygon conventions and primitives shared by the rest of the package.
``planner``
    The end-to-end pipeline: field + obstacles -> coverage path.
``incremental``
    Dynamic replanning on obstacle insertion/removal.
``metrics``
    Coverage, path length, non-working ratio, overlap, turns.
"""

from __future__ import annotations

__version__ = "0.1.0"

from .geometry import (  # noqa: F401
    free_space,
    iter_polygons,
    normalise,
    total_area,
)
from .sweep import Edge, ScanlineClipper, check_rings  # noqa: F401

__all__ = [
    "__version__",
    "ScanlineClipper",
    "Edge",
    "check_rings",
    "free_space",
    "normalise",
    "total_area",
    "iter_polygons",
]
