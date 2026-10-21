"""Picking a field to look at: synthetic scenes, or one of the 350 real ones.

Loading all 350 benchmark geometries takes seconds and ~200 MB, and the user
will look at a handful of them.  So the catalogue reads only the shipped
``geometry_summary.json`` up front -- names, countries and areas -- and parses a
single WKT file when one is actually selected.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..fields import Field, make_field
from ..io_fields import BENCHMARK_DIR, SUMMARY_FILE, WKT_SUBDIR, benchmark_records, load_wkt

__all__ = ["FieldCatalog", "FieldSourcePanel"]

KINDS = [
    ("rect", "矩形"),
    ("l", "L 形"),
    ("u", "U 形"),
    ("star", "星形（凹）"),
    ("rectilinear", "矩形带缺口（类真实田地）"),
]
COUNTRIES = [("全部", None), ("荷兰 nl", "nl"), ("爱沙尼亚 ee", "ee"), ("立陶宛 lt", "lt")]


class FieldCatalog:
    """Names and metadata for the shipped benchmark, with lazy geometry loading."""

    def __init__(self) -> None:
        self._entries: list[dict] | None = None
        self._cache: dict[str, Field] = {}
        self._wkt_dir = self._find_wkt_dir()

    @staticmethod
    def _find_wkt_dir() -> Path | None:
        for candidate in (
            BENCHMARK_DIR / WKT_SUBDIR / "wkt",
            BENCHMARK_DIR / "wkt",
        ):
            if candidate.is_dir():
                return candidate
        return None

    @property
    def available(self) -> bool:
        return self._wkt_dir is not None

    def entries(self) -> list[dict]:
        """``[{name, country, area_ha, path}]``, sorted by name."""
        if self._entries is not None:
            return self._entries
        if not self.available:
            self._entries = []
            return self._entries

        meta = {r["f"]: r for r in benchmark_records(BENCHMARK_DIR / SUMMARY_FILE)}
        out = []
        for path in sorted(self._wkt_dir.glob("*.wkt")):  # type: ignore[union-attr]
            rec = meta.get(path.name, {})
            out.append(
                {
                    "name": path.stem,
                    "country": path.name[:2].lower(),
                    "area_ha": float(rec.get("area_net_ha", 0.0)),
                    "path": path,
                }
            )
        self._entries = out
        return out

    def load(self, name: str) -> Field:
        if name in self._cache:
            return self._cache[name]
        entry = next((e for e in self.entries() if e["name"] == name), None)
        if entry is None:
            raise KeyError(name)
        boundary = load_wkt(entry["path"])
        field = Field(
            name=name,
            boundary=boundary,
            meta={"country": entry["country"], "area_ha": entry["area_ha"], "source": "Fields2Benchmark"},
        )
        self._cache[name] = field
        return field


class FieldSourcePanel(QGroupBox):
    """Synthetic-or-real field chooser.  Emits :attr:`field_changed`."""

    field_changed = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("田地", parent)
        self.catalog = FieldCatalog()
        self._current: Field | None = None

        self.mode = QComboBox()
        self.mode.addItems(["合成田地", "真实田地（Fields2Benchmark）"])
        if not self.catalog.available:
            self.mode.setItemText(1, "真实田地（未下载数据）")
            self.mode.model().item(1).setEnabled(False)

        # --- synthetic -------------------------------------------------
        self.kind = QComboBox()
        for value, label in KINDS:
            self.kind.addItem(label, value)
        self.seed = QSpinBox()
        self.seed.setRange(0, 9999)
        self.seed.setValue(4)
        self.n_obstacles = QSpinBox()
        self.n_obstacles.setRange(0, 60)
        self.n_obstacles.setValue(10)
        self.target_area = QDoubleSpinBox()
        self.target_area.setRange(0.2, 400.0)
        self.target_area.setValue(2.0)
        self.target_area.setSuffix(" ha")
        self.target_area.setDecimals(2)

        synthetic = QWidget()
        form = QFormLayout(synthetic)
        form.setContentsMargins(0, 0, 0, 0)
        form.addRow("形状", self.kind)
        form.addRow("随机种子", self.seed)
        form.addRow("田内障碍数", self.n_obstacles)
        form.addRow("面积", self.target_area)

        # --- real ------------------------------------------------------
        self.country = QComboBox()
        for label, value in COUNTRIES:
            self.country.addItem(label, value)
        self.search = QLineEdit()
        self.search.setPlaceholderText("按名称筛选，例如 field_10")
        self.field_list = QComboBox()
        self.field_list.setMaxVisibleItems(24)

        real = QWidget()
        rform = QFormLayout(real)
        rform.setContentsMargins(0, 0, 0, 0)
        rform.addRow("国家", self.country)
        rform.addRow("筛选", self.search)
        rform.addRow("田地", self.field_list)

        self.stack = QStackedWidget()
        self.stack.addWidget(synthetic)
        self.stack.addWidget(real)

        self.refresh_button = QPushButton("载入 / 更新田地")
        self.status = QLabel("")
        self.status.setStyleSheet("color:#6b7280; font-size:11px;")
        self.status.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(self.mode)
        layout.addWidget(self.stack)
        layout.addWidget(self.refresh_button)
        layout.addWidget(self.status)
        layout.setSpacing(6)

        self.mode.currentIndexChanged.connect(self.stack.setCurrentIndex)
        self.country.currentIndexChanged.connect(self._reload_real_list)
        self.search.textChanged.connect(self._reload_real_list)
        self.refresh_button.clicked.connect(self.rebuild)

    # ------------------------------------------------------------------
    @property
    def current(self) -> Field | None:
        return self._current

    def build_field(self) -> Field:
        """Construct the scene the controls currently describe."""
        if self.mode.currentIndex() == 0:
            return make_field(
                self.kind.currentData(),
                seed=self.seed.value(),
                n_obstacles=self.n_obstacles.value(),
                target_area=self.target_area.value() * 10_000.0,
            )
        name = self.field_list.currentData()
        if not name:
            raise RuntimeError("没有可用的真实田地")
        return self.catalog.load(name)

    def rebuild(self) -> None:
        try:
            field = self.build_field()
        except Exception as exc:  # noqa: BLE001 - surface, never crash the window
            self.status.setText(f"载入失败：{exc}")
            return
        self._current = field
        w, h = field.size()
        obstacles = len(field.obstacles)
        source = field.meta.get("source", "synthetic")
        self.status.setText(
            f"{field.name} · {source} · {field.area:,.0f} m² · "
            f"{w:.0f} × {h:.0f} m · 障碍 {obstacles}"
        )
        self.field_changed.emit(field)

    def _reload_real_list(self) -> None:
        if not self.catalog.available:
            return
        wanted = self.country.currentData()
        needle = self.search.text().strip().lower()
        names = [
            e["name"]
            for e in self.catalog.entries()
            if (wanted is None or e["country"] == wanted)
            and (not needle or needle in e["name"].lower())
        ]
        self.field_list.clear()
        self.field_list.addItems(names[:400])
        self.status.setText(f"匹配 {len(names)} 块田地")
