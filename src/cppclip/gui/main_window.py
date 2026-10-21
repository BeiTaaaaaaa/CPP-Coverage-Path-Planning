"""Main window: three tabs, a status bar, and nothing else in the way."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QFont, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QMessageBox,
    QTabWidget,
)

from .. import __version__
from . import theme
from .incremental_tab import IncrementalTab
from .plan_tab import PlanTab
from .results_tab import ResultsTab

__all__ = ["MainWindow"]


ABOUT = """<h3>cppclip 结果查看器</h3>
<p>把「图形学裁剪 + 割草机覆盖路径规划」的研究结果做成可交互的界面。</p>
<p><b>田地规划</b>：选一块田地（合成或 Fields2Benchmark 的 350 块真实田地之一），
调参数，看条带、地头、绕行路径与全部指标。</p>
<p><b>增量重算</b>：在画布上点击放置障碍。程序只重算该障碍跨越的那几条扫描线
（橙色带），其余条带原地保留、路径局部修复，并实时给出与全量重算的耗时对比 ——
这正是论文的核心实验。</p>
<p><b>实验结果</b>：由 results/tables 里的 CSV 实时重绘五个实验的图表，
下方是原始表格。</p>
<p style="color:#6b7280">核心算法：扫描线活性边表 + 奇偶规则求有效区间。
Dubins 转弯为闭式解并逐条验证到达。</p>
"""


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"cppclip · 裁剪驱动的覆盖路径规划  v{__version__}")
        self.resize(1380, 880)

        self.plan_tab = PlanTab()
        self.incremental_tab = IncrementalTab()
        self.results_tab = ResultsTab()

        tabs = QTabWidget()
        tabs.addTab(self.plan_tab, "田地规划")
        tabs.addTab(self.incremental_tab, "增量重算（核心实验）")
        tabs.addTab(self.results_tab, "实验结果")
        tabs.setDocumentMode(True)
        self.setCentralWidget(tabs)
        self.tabs = tabs

        for tab in (self.plan_tab, self.incremental_tab, self.results_tab):
            tab.status.connect(self._show_status)

        self.status_label = QLabel("就绪")
        self.statusBar().addWidget(self.status_label, 1)
        self.version_label = QLabel(f"v{__version__}")
        self.version_label.setStyleSheet(f"color:{theme.MUTED};")
        self.statusBar().addPermanentWidget(self.version_label)

        self._build_menu()

    # ------------------------------------------------------------------
    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("文件(&F)")

        reload_action = QAction("重新载入结果表(&R)", self)
        reload_action.setShortcut(QKeySequence("Ctrl+R"))
        reload_action.triggered.connect(self.results_tab.reload)
        file_menu.addAction(reload_action)

        quit_action = QAction("退出(&Q)", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(QApplication.instance().quit)
        file_menu.addAction(quit_action)

        view_menu = self.menuBar().addMenu("视图(&V)")
        for index, name in enumerate(["田地规划", "增量重算", "实验结果"]):
            action = QAction(f"{name}(&{index + 1})", self)
            action.setShortcut(QKeySequence(f"Ctrl+{index + 1}"))
            action.triggered.connect(lambda _checked=False, i=index: self.tabs.setCurrentIndex(i))
            view_menu.addAction(action)

        help_menu = self.menuBar().addMenu("帮助(&H)")
        about_action = QAction("关于(&A)", self)
        about_action.triggered.connect(self._about)
        help_menu.addAction(about_action)

    def _about(self) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("关于 cppclip")
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(ABOUT)
        font = QFont()
        font.setPointSize(9)
        box.setFont(font)
        box.exec()

    def _show_status(self, message: str) -> None:
        self.status_label.setText(message)
