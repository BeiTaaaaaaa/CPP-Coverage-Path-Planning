"""End-to-end smoke test for the planning pipeline."""
from __future__ import annotations

import os

# Keep every cache inside the workspace so runs are reproducible and do not
# depend on (or fight over) the user profile directory.
os.environ.setdefault("MPLCONFIGDIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".cache", "matplotlib"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from cppclip import fields as F
from cppclip.metrics import evaluate
from cppclip.planner import PlanParams, plan


def main() -> None:
    cases = [
        ("rect", 0),
        ("l", 1),
        ("u", 2),
        ("star", 3),
        ("rectilinear", 4),
    ]
    print(f"{'field':<28} {'stroke':>7} {'cover':>7} {'overlap':>8} {'nw%':>6} "
          f"{'path_m':>9} {'strokes':>8} {'time_ms':>8}")
    print("-" * 90)

    for kind, seed in cases:
        for n_obs in (0, 12):
            field = F.make_field(kind, seed=seed, n_obstacles=n_obs, target_area=20_000.0)
            params = PlanParams(swath_width=6.0, headland_width=6.0, min_swath_length=1.0)
            p = plan(field, params)
            m = evaluate(field, p)
            print(f"{field.name:<28} {m.stroke_width:>7.1f} {m.coverage:>7.3f} "
                  f"{m.overlap:>8.3f} {100*m.non_working_ratio:>6.1f} "
                  f"{m.path_length:>9.1f} {m.n_strokes:>8d} {1000*m.plan_time:>8.1f}")


if __name__ == "__main__":
    main()
