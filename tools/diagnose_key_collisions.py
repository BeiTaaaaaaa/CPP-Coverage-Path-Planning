"""Did the scanline-key collision affect the real benchmark, or only regular fields?

The collision needs two swaths on *different* scanlines with an identical x range.
That is common on a rectangular field cut into equal stripes and rare on the
irregular Fields2Benchmark boundaries.  This measures which, because it decides
whether the recorded experiment tables were affected.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".cache" / "matplotlib"))
sys.path.insert(0, str(ROOT / "src"))

from collections import Counter  # noqa: E402

from cppclip.fields import make_field  # noqa: E402
from cppclip.incremental import IncrementalPlanner, _key  # noqa: E402
from cppclip.io_fields import load_benchmark  # noqa: E402
from cppclip.planner import PlanParams  # noqa: E402

P = dict(swath_width=6.0, headland_width=6.0, route="optimised",
         min_swath_length=1.5, n_angle_candidates=24)


def collisions(swaths) -> int:  # noqa: ANN001
    keys = [_key(s) for s in swaths]
    return len(keys) - len(set(keys))


def probe(field) -> tuple[int, int, int]:  # noqa: ANN001
    """(swaths, swaths that would collide without the fix, duplicates now).

    The middle number is the one that matters.  It counts swaths whose only
    distinguishing feature is the scanline index: if ``Swath.scanline`` failed to
    tell lines apart, that many entries would compare equal.  Measuring it does
    not depend on the fix being present, so the probe is meaningful either way --
    counting duplicates *now* would only confirm the fix works.
    """
    planner = IncrementalPlanner(field, PlanParams(**P), angle=0.0)
    swaths = planner._all_swaths()
    by_x: dict[tuple, set] = {}
    for s in swaths:
        by_x.setdefault((round(s.x0, 9), round(s.x1, 9)), set()).add(s.scanline)
    would_collide = sum(len(lines) - 1 for lines in by_x.values() if len(lines) > 1)
    return len(swaths), would_collide, collisions(swaths)


def main() -> None:
    print("synthetic fields (what the GUI builds):")
    for kind in ("rect", "l", "u", "star", "rectilinear"):
        for seed in (1, 4, 7):
            field = make_field(kind, seed=seed, n_obstacles=3, target_area=25_000.0)
            n, would, dup = probe(field)
            flag = "  <-- would have collided" if would else ""
            print(f"  {kind:<12} seed {seed}  swaths {n:3d}  "
                  f"colliding without the fix {would:3d}{flag}")

    print("\nreal Fields2Benchmark fields:")
    fields = load_benchmark(limit=120)
    print(f"  loaded {len(fields)} fields")
    now = 0
    would_total = 0
    affected = 0
    worst = []
    for field in fields:
        n, would, dup = probe(field)
        now += dup
        would_total += would
        affected += 1 if would else 0
        worst.append((would, field.name, n))
    print(f"  duplicate keys now                        : {now}")
    print(f"  swaths that would collide without the fix  : {would_total}")
    print(f"  fields that would have been affected       : {affected} / {len(fields)}")
    for would, name, n in sorted(worst, reverse=True)[:6]:
        print(f"    {name:<22} swaths {n:3d}  would collide {would}")


if __name__ == "__main__":
    main()
