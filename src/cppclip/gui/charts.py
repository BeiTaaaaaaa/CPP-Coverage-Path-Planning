"""Charts for the results browser, drawn from the CSVs rather than from PNGs.

Re-plotting instead of loading ``results/figures/*.png`` buys three things: the
charts cannot drift from the tables they summarise, they can be zoomed and
explored, and they can be re-saved at any size.  The styling follows
``cppclip.viz`` so an on-screen chart matches its counterpart in the report.
"""

from __future__ import annotations

from typing import Callable

import matplotlib
import numpy as np
import pandas as pd
from matplotlib.figure import Figure

__all__ = ["CHARTS", "draw_chart"]

#: Charts in this window are labelled in Chinese, and matplotlib's bundled
#: DejaVu Sans has no CJK glyphs -- titles and axis labels come out blank, which
#: looks like a broken chart rather than a font problem.  Pick the first
#: installed font that can actually draw the text.
_CJK_CANDIDATES = [
    "Microsoft YaHei", "SimHei", "SimSun",          # Windows
    "Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Micro Hei",  # Linux
    "PingFang SC", "Hiragino Sans GB", "Heiti SC",  # macOS
]


def _use_cjk_font() -> str | None:
    from matplotlib import font_manager

    installed = {f.name for f in font_manager.fontManager.ttflist}
    chosen = next((name for name in _CJK_CANDIDATES if name in installed), None)
    if chosen:
        matplotlib.rcParams["font.sans-serif"] = [chosen, "DejaVu Sans"]
    matplotlib.rcParams["axes.unicode_minus"] = False
    return chosen


CJK_FONT = _use_cjk_font()

_ACCENT = "#1f6f8b"
_WARM = "#b03a2e"
_PURPLE = "#7d5ba6"
_GREEN = "#0b6e4f"


def _clean(ax) -> None:  # noqa: ANN001
    ax.grid(alpha=0.3)
    ax.set_axisbelow(True)


def _scaling(df: pd.DataFrame, fig: Figure) -> None:
    by = df.groupby("scale").agg(
        area=("area_ha", "mean"),
        scanlines=("n_scanlines", "mean"),
        affected=("affected_fraction", "mean"),
        sp_full=("speedup_vs_full", "median"),
        sp_fixed=("speedup_vs_fixed", "median"),
        penalty=("path_penalty", "mean"),
    )
    axes = fig.subplots(1, 3)

    axes[0].plot(by.scanlines, 100 * by.affected, "o-", color=_WARM)
    axes[0].set_xlabel("田地扫描线数")
    axes[0].set_ylabel("单个障碍失效的扫描线 [%]")
    axes[0].set_title("省下的工作量随田地增大")
    _clean(axes[0])

    axes[1].plot(by.scanlines, by.sp_full, "s-", label="对比全量重算", color=_ACCENT)
    axes[1].plot(by.scanlines, by.sp_fixed, "o--", label="对比冻结作业角", color=_GREEN)
    axes[1].set_xlabel("田地扫描线数")
    axes[1].set_ylabel("加速比 [倍]")
    axes[1].set_yscale("log")
    axes[1].set_title("增量重规划的加速比")
    axes[1].legend()
    _clean(axes[1])

    axes[2].bar(range(len(by)), 100 * by.penalty, color=_PURPLE)
    axes[2].set_xticks(range(len(by)))
    axes[2].set_xticklabels([f"{a:.0f} ha" for a in by.area], rotation=30, ha="right")
    axes[2].axhline(0, color="k", lw=0.8)
    axes[2].set_ylabel("路径长度代价 [%]")
    axes[2].set_title("加速付出的代价")
    _clean(axes[2])


def _ablation(df: pd.DataFrame, fig: Figure) -> None:
    """Both ablation tables live in one figure when both are present."""
    axes = fig.subplots(1, 2)
    left = df[df.get("repair_window", 12) >= 12] if "repair_window" in df else df
    g = left.groupby("global_fraction").agg(
        sp=("speedup_vs_fixed_median", "mean"), pen=("path_penalty_median", "mean")
    )
    ax = axes[0]
    ax.plot(g.index, g.sp, "o-", color=_ACCENT)
    ax.set_xlabel("global_repair_fraction")
    ax.set_ylabel("相对冻结作业角的加速 [倍]", color=_ACCENT)
    ax.tick_params(axis="y", colors=_ACCENT)
    ax2 = ax.twinx()
    ax2.plot(g.index, 100 * g.pen, "s--", color=_WARM)
    ax2.set_ylabel("路径代价 [%]", color=_WARM)
    ax2.tick_params(axis="y", colors=_WARM)
    ax.set_title("路径重解阈值")
    ax.grid(alpha=0.3)

    ax = axes[1]
    if "repair_window" in df:
        w = df.groupby("repair_window").agg(
            sp=("speedup_vs_fixed_median", "mean"),
            med=("path_penalty_median", "mean"),
            p90=("path_penalty_p90", "mean"),
        )
        ax.plot(w.index, w.sp, "o-", color=_ACCENT, label="加速")
        ax.set_xlabel("repair_window")
        ax.set_ylabel("加速 [倍]", color=_ACCENT)
        ax2 = ax.twinx()
        ax2.plot(w.index, 100 * w.med, "s--", color=_WARM, label="中位代价")
        ax2.plot(w.index, 100 * w.p90, "^:", color="#e08a3c", label="p90 代价")
        ax2.set_ylabel("路径代价 [%]")
        ax2.legend(fontsize=8)
        ax.set_title("局部修复窗口")
        ax.grid(alpha=0.3)
    else:
        ax.text(0.5, 0.5, "需要 exp_ablation_window.csv", ha="center", transform=ax.transAxes)
        ax.axis("off")


def _compare(df: pd.DataFrame, fig: Figure) -> None:
    ok = df[df.error.isna()] if "error" in df.columns else df
    systems = ["cppclip", "fields2cover"]
    labels = {"cppclip": "cppclip", "fields2cover": "Fields2Cover (snake)"}
    colours = {"cppclip": _ACCENT, "fields2cover": _WARM}
    axes = fig.subplots(1, 3)

    for ax, column, ylabel, title in (
        (axes[0], "coverage", "覆盖率", "对可行驶区域的覆盖"),
        (axes[1], "total_length", "总行驶里程 [m]", "里程（双方转弯半径均为 2 m）"),
        (axes[2], "non_working_ratio", "空走率 [%]", "空走占比"),
    ):
        data = []
        for s in systems:
            values = ok[ok.system == s][column].dropna().values
            data.append(100 * values if column == "non_working_ratio" else values)
        bp = ax.boxplot(data, tick_labels=[labels[s] for s in systems], patch_artist=True, widths=0.55)
        for patch, s in zip(bp["boxes"], systems):
            patch.set_facecolor(colours[s])
            patch.set_alpha(0.75)
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        _clean(ax)


def _incremental(df: pd.DataFrame, fig: Figure) -> None:
    axes = fig.subplots(1, 3)
    axes[0].hist(100 * df.affected_fraction.dropna(), bins=24, color=_GREEN, alpha=0.85)
    axes[0].set_xlabel("失效扫描线 [%]")
    axes[0].set_ylabel("变更次数")
    axes[0].set_title(f"每次环境变更的工作量（n={len(df)}）")
    _clean(axes[0])

    axes[1].hist(100 * df.path_penalty_vs_fixed.dropna(), bins=30, color=_PURPLE, alpha=0.85)
    axes[1].axvline(0, color="k", lw=0.9)
    axes[1].set_xlabel("相对全局重解的路径代价 [%]")
    axes[1].set_ylabel("变更次数")
    axes[1].set_title("增量修复的质量代价")
    _clean(axes[1])

    ax = axes[2]
    ax.scatter(df.n_scanlines_total, 1000 * df.t_incremental_s, s=9, alpha=0.5,
               color=_ACCENT, label="增量")
    ax.scatter(df.n_scanlines_total, 1000 * df.t_full_fixed_s, s=9, alpha=0.5,
               color=_WARM, label="全量（冻结作业角）")
    ax.set_xlabel("田地扫描线数")
    ax.set_ylabel("每次变更耗时 [ms]")
    ax.set_yscale("log")
    ax.set_title("单次变更的耗时")
    ax.legend()
    _clean(ax)


def _turn_radius(df: pd.DataFrame, fig: Figure) -> None:
    by = df.groupby("turn_radius").agg(
        path=("path_length", "median"),
        transit=("transit_length", "median"),
        nw=("non_working_ratio", "median"),
        ratio=("ratio_vs_straight", "median"),
    )
    axes = fig.subplots(1, 2)
    x = np.arange(len(by))
    axes[0].bar(x, by.path, color=_ACCENT, alpha=0.9)
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(["直线" if r == 0 else f"{r:g} m" for r in by.index])
    axes[0].set_ylabel("总路径（中位）[m]")
    axes[0].set_title("转弯半径对行驶里程的影响")
    _clean(axes[0])

    axes[1].plot(x, 100 * (by.ratio - 1.0), "o-", color=_WARM)
    axes[1].axhline(0, color="k", lw=0.8)
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(["直线" if r == 0 else f"{r:g} m" for r in by.index])
    axes[1].set_ylabel("直线连接的低估幅度 [%]")
    axes[1].set_title("不建模曲率会乐观多少")
    _clean(axes[1])


#: name -> (table file, title, drawing function, needs a second table)
CHARTS: dict[str, tuple[str, str, Callable, str | None]] = {
    "scaling": ("exp3_scaling", "规模效应（实验三）", _scaling, None),
    "incremental": ("exp2_incremental", "增量 vs 全量（实验二）", _incremental, None),
    "compare": ("exp4_compare", "与 Fields2Cover 对比（实验四）", _compare, None),
    "turn_radius": ("exp5_turn_radius", "转弯运动学代价（实验五）", _turn_radius, None),
    "ablation": ("exp_ablation_repair", "消融实验（实验 5.4）", _ablation, "exp_ablation_window"),
}

#: Charts that only make sense with more than one table loaded.
COMBINED: dict[str, tuple[str, ...]] = {"ablation": ("exp_ablation_repair", "exp_ablation_window")}


def draw_chart(name: str, tables: dict[str, pd.DataFrame], fig: Figure) -> None:
    """Populate *fig* with chart *name*, using whatever tables are available."""
    fig.clear()
    if name not in CHARTS:
        raise KeyError(name)
    _file, _title, fn, extra = CHARTS[name]
    df = tables.get(_file)
    if df is None:
        ax = fig.subplots(1, 1)
        ax.text(0.5, 0.5, f"缺少结果表 {_file}.csv\n请先运行 experiments/run_all.py",
                ha="center", va="center", transform=ax.transAxes, color="#6b7280")
        ax.axis("off")
        return
    if extra and extra in tables and name == "ablation":
        df = pd.concat([df, tables[extra]], ignore_index=True)
    fn(df, fig)
    fig.tight_layout()
