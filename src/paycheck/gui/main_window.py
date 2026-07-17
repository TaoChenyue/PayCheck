"""PySide6 主窗口 — 页签组装 + 数据加载协调 + 主题管理。"""

import logging

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QMenu,
    QLabel, QComboBox, QTabWidget, QApplication,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup

from paycheck.storage import database as db
from paycheck.gui.import_panel import ImportPanel
from paycheck.gui.detail_panel import DetailPanel
from paycheck.gui.theme import ThemeManager, ThemeMode

try:
    from paycheck.ocr.layouts import list_layouts
except ImportError:
    list_layouts = lambda: ["boc"]

log = logging.getLogger("paycheck.gui")


class MainWindow(QMainWindow):
    """主窗口：组装导入面板和交易明细面板，协调数据加载和主题切换。"""

    def __init__(self, theme_mgr: ThemeManager | None = None):
        super().__init__()
        self.setWindowTitle("PayCheck - 个人账单统计")
        self.setMinimumSize(1000, 700)

        self._theme_mgr = theme_mgr or ThemeManager()
        if theme_mgr is None:
            self._theme_mgr.load_preference()

        # 银行类型选择器 — ImportPanel 和 _sync_bank_tab_label 共享引用
        layouts = list_layouts()
        self._bank_type_combo = QComboBox()
        for name in layouts:
            self._bank_type_combo.addItem(name.upper(), name)

        self._init_ui()
        self._load_from_db()

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(8)

        # ── 底部状态（先创建，后续信号连接需要）──
        self._status = QLabel("就绪")
        self._status.setStyleSheet("font-style: italic;")

        # ── 顶层分页：导入 / 交易明细 ──
        self._page_tabs = QTabWidget()

        # 导入页
        self._import_panel = ImportPanel(self._bank_type_combo)
        self._import_panel.import_finished.connect(self._load_from_db)
        self._page_tabs.addTab(self._import_panel, "导入")

        # 交易明细页
        self._detail_panel = DetailPanel()
        self._detail_panel.status_message.connect(self._status.setText)
        self._page_tabs.addTab(self._detail_panel, "交易明细")

        layout.addWidget(self._page_tabs, 1)
        layout.addWidget(self._status)

        # ── 菜单栏 ──
        self._setup_menu()

    # ── 主题菜单 ──

    def _setup_menu(self):
        menubar = self.menuBar()

        # ── 视图菜单 ──
        view_menu = menubar.addMenu("视图")

        theme_menu = view_menu.addMenu("主题")
        self._theme_group = QActionGroup(self)
        self._theme_group.setExclusive(True)

        self._theme_action_light = QAction("亮色", self)
        self._theme_action_light.setCheckable(True)
        self._theme_action_light.triggered.connect(
            lambda: self._on_theme_change(ThemeMode.LIGHT))
        self._theme_group.addAction(self._theme_action_light)
        theme_menu.addAction(self._theme_action_light)

        self._theme_action_dark = QAction("暗色", self)
        self._theme_action_dark.setCheckable(True)
        self._theme_action_dark.triggered.connect(
            lambda: self._on_theme_change(ThemeMode.DARK))
        self._theme_group.addAction(self._theme_action_dark)
        theme_menu.addAction(self._theme_action_dark)

        self._theme_action_system = QAction("跟随系统", self)
        self._theme_action_system.setCheckable(True)
        self._theme_action_system.triggered.connect(
            lambda: self._on_theme_change(ThemeMode.SYSTEM))
        self._theme_group.addAction(self._theme_action_system)
        theme_menu.addAction(self._theme_action_system)

        self._sync_theme_menu()

    def _sync_theme_menu(self):
        """根据当前主题模式勾选对应菜单项。"""
        mode = self._theme_mgr.current_mode
        mapping = {
            ThemeMode.LIGHT: self._theme_action_light,
            ThemeMode.DARK: self._theme_action_dark,
            ThemeMode.SYSTEM: self._theme_action_system,
        }
        for m, action in mapping.items():
            action.setChecked(m == mode)

    def _on_theme_change(self, mode: ThemeMode):
        """切换主题并刷新菜单勾选。"""
        app = QApplication.instance()
        if app is None:
            return
        self._theme_mgr.set_mode(app, mode)
        self._sync_theme_menu()

    # ── 快捷键 ──

    def keyPressEvent(self, event):
        if event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_T:
            if self._detail_panel.handle_tag_shortcut():
                self._load_from_db()
        elif event.modifiers() == (Qt.ControlModifier | Qt.ShiftModifier) and event.key() == Qt.Key_T:
            if self._detail_panel.open_tag_manager():
                self._load_from_db()
        else:
            super().keyPressEvent(event)

    # ── 数据加载协调 ──

    def _load_from_db(self):
        """从数据库加载交易数据，刷新所有面板。"""
        transactions = db.get_all_transactions()
        if not transactions:
            self._status.setText("请导入账单文件")
            return

        tags = db.get_all_tags()
        tag_map = {t["name"]: t["id"] for t in tags}

        self._detail_panel.refresh_tag_data(tags)
        self._detail_panel.set_data(transactions, tag_map)
        self._detail_panel.restore_tag_filter()

        self._sync_bank_tab_label()
        self._status.setText(self._detail_panel.status_text)

    def _sync_bank_tab_label(self):
        """根据银行类型选择器更新表格中银行标签页名称。"""
        if self._bank_type_combo is not None and self._bank_type_combo.count() > 0:
            name = self._bank_type_combo.currentData()
            label = name.upper() if name else "银行"
            self._detail_panel.table_renderer.set_tab_text(2, label)
