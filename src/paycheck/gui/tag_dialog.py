"""统一标签弹窗 — 标签管理 + 交易赋值"""
import logging
from typing import Dict, List, Optional, Set

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QCheckBox, QScrollArea, QWidget, QGridLayout, QTableWidget,
    QTableWidgetItem, QHeaderView, QComboBox, QDialogButtonBox,
    QMessageBox, QFrame, QInputDialog,
)
from PySide6.QtCore import Qt, Signal

from paycheck.storage import database as db

log = logging.getLogger("paycheck.gui.tag_dialog")


class TagDialog(QDialog):
    """统一标签弹窗 — manage 模式用于标签 CRUD，assign 模式用于交易标签赋值"""

    def __init__(
        self,
        parent=None,
        db_path: str = None,
        mode: str = "manage",
        tx_ids: Optional[List[int]] = None,
    ):
        super().__init__(parent)
        self._db_path = db_path if db_path is not None else db.DB_PATH
        self._mode = mode
        self._tx_ids = tx_ids or []
        self._tags: List[Dict] = []
        self._all_checkboxes: List[QCheckBox] = []
        self._search_text = ""

        self._setup_ui()
        self._refresh_ui()

        if self._mode == "assign" and self._tx_ids:
            self._precheck_intersection()

    # ── UI construction ────────────────────────────────────────────

    def _setup_ui(self) -> None:
        """构建完整 UI 布局"""
        n = len(self._tx_ids)
        title_text = "标签管理" if self._mode == "manage" else f"为 {n} 笔交易设置标签"
        self.setWindowTitle(title_text)
        self.setMinimumSize(600, 500)

        layout = QVBoxLayout(self)

        # ── 标题 ──
        self._title_label = QLabel(title_text)
        font = self._title_label.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 2)
        self._title_label.setFont(font)
        layout.addWidget(self._title_label)

        # ── 搜索框 ──
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("搜索标签...")
        self._search_input.textChanged.connect(self._on_search)
        layout.addWidget(self._search_input)

        # ── 分隔线1 ──
        layout.addWidget(self._make_sep())

        # ── 标签选择区（可滚动复选框网格）──
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._grid_container = QWidget()
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        self._scroll_area.setWidget(self._grid_container)
        layout.addWidget(self._scroll_area, 1)  # stretch=1 让此区域可伸缩

        # ── 新建标签行 ──
        new_tag_layout = QHBoxLayout()
        self._new_tag_input = QLineEdit()
        self._new_tag_input.setPlaceholderText("新标签名")
        self._new_tag_input.returnPressed.connect(self._on_create_tag)
        new_tag_layout.addWidget(self._new_tag_input)
        add_btn = QPushButton("+")
        add_btn.setFixedWidth(36)
        add_btn.clicked.connect(self._on_create_tag)
        new_tag_layout.addWidget(add_btn)
        layout.addLayout(new_tag_layout)

        # ── 分隔线2 ──
        layout.addWidget(self._make_sep())

        # ── 管理区标题 ──
        layout.addWidget(QLabel("管理标签"))

        # ── 管理表格 ──
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["标签名", "笔数", "操作"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.verticalHeader().setVisible(False)
        layout.addWidget(self._table, 1)

        # ── 合并区 ──
        merge_layout = QHBoxLayout()
        merge_layout.addWidget(QLabel("合并:"))
        self._source_combo = QComboBox()
        self._source_combo.setMinimumWidth(120)
        merge_layout.addWidget(self._source_combo)
        merge_layout.addWidget(QLabel("→"))
        self._target_combo = QComboBox()
        self._target_combo.setMinimumWidth(120)
        merge_layout.addWidget(self._target_combo)
        merge_btn = QPushButton("执行")
        merge_btn.clicked.connect(self._on_merge)
        merge_layout.addWidget(merge_btn)
        merge_layout.addStretch()
        layout.addLayout(merge_layout)

        # ── 底部按钮 ──
        button_box = QDialogButtonBox()
        cancel_btn = button_box.addButton("取消", QDialogButtonBox.ButtonRole.RejectRole)
        cancel_btn.clicked.connect(self.reject)
        action_text = "关闭" if self._mode == "manage" else "覆盖确认"
        self._action_btn = button_box.addButton(action_text, QDialogButtonBox.ButtonRole.AcceptRole)
        self._action_btn.clicked.connect(self._on_accept)
        layout.addWidget(button_box)

    @staticmethod
    def _make_sep() -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.Shape.HLine)
        f.setFrameShadow(QFrame.Shadow.Sunken)
        return f

    # ── Data loading ────────────────────────────────────────────────

    def _refresh_ui(self) -> None:
        """从数据库重新加载标签，刷新复选框网格、管理表格、合并下拉框"""
        self._tags = db.get_all_tags(path=self._db_path)
        self._rebuild_checkboxes()
        self._rebuild_table()
        self._rebuild_combos()
        if self._search_text:
            self._apply_filter(self._search_text)

    def _precheck_intersection(self) -> None:
        """在 assign 模式下，预选所有已选交易共有的标签"""
        if not self._tx_ids:
            return
        # 批量查询，避免逐笔打开连接
        tag_map = db.get_transaction_tags_batch(self._tx_ids, path=self._db_path)
        if not tag_map:
            return
        common_ids: Set[int] = set.intersection(*tag_map.values()) if tag_map else set()
        for cb in self._all_checkboxes:
            tag_id = cb.property("tag_id")
            if tag_id in common_ids:
                cb.setChecked(True)

    # ── Checkbox grid ───────────────────────────────────────────────

    def _rebuild_checkboxes(self) -> None:
        """重建复选框网格，4 列排列，标签按笔数降序"""
        # 清空旧控件
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._all_checkboxes.clear()

        cols = 4
        for i, tag in enumerate(self._tags):
            cb = QCheckBox(f"{tag['name']} ({tag['count']}笔)")
            cb.setProperty("tag_id", tag["id"])
            cb.setProperty("tag_name", tag["name"])
            self._grid_layout.addWidget(cb, i // cols, i % cols)
            self._all_checkboxes.append(cb)

    # ── Management table ─────────────────────────────────────────────

    def _rebuild_table(self) -> None:
        """重建管理表格"""
        self._table.setRowCount(0)
        for row_idx, tag in enumerate(self._tags):
            self._table.insertRow(row_idx)

            # 标签名列
            name_item = QTableWidgetItem(tag["name"])
            name_item.setData(Qt.ItemDataRole.UserRole, tag["id"])
            self._table.setItem(row_idx, 0, name_item)

            # 笔数列
            count_item = QTableWidgetItem(str(tag["count"]))
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row_idx, 1, count_item)

            # 操作列（按钮容器）
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(4, 2, 4, 2)
            btn_layout.setSpacing(6)

            rename_btn = QPushButton("重命名")
            rename_btn.setFlat(True)
            rename_btn.clicked.connect(
                lambda checked=False, r=row_idx, t=tag: self._on_rename(r, t)
            )
            btn_layout.addWidget(rename_btn)

            delete_btn = QPushButton("删除")
            delete_btn.setFlat(True)
            delete_btn.clicked.connect(
                lambda checked=False, r=row_idx, t=tag: self._on_delete(r, t)
            )
            btn_layout.addWidget(delete_btn)

            self._table.setCellWidget(row_idx, 2, btn_widget)

        self._table.resizeColumnsToContents()

    # ── Merge combos ─────────────────────────────────────────────────

    def _rebuild_combos(self) -> None:
        """重建合并区的两个下拉框"""
        self._source_combo.clear()
        self._target_combo.clear()
        for tag in self._tags:
            self._source_combo.addItem(tag["name"], tag["id"])
            self._target_combo.addItem(tag["name"], tag["id"])

    # ── Filter ───────────────────────────────────────────────────────

    def _on_search(self, text: str) -> None:
        self._search_text = text
        self._apply_filter(text)

    def _apply_filter(self, text: str) -> None:
        """根据搜索文本过滤复选框网格和管理表格"""
        lower = text.lower()

        # 过滤复选框
        for i, cb in enumerate(self._all_checkboxes):
            name = cb.property("tag_name") or ""
            cb.setVisible(lower in name.lower())

        # 过滤表格
        for row in range(self._table.rowCount()):
            name_item = self._table.item(row, 0)
            if name_item is None:
                self._table.setRowHidden(row, True)
                continue
            visible = lower in name_item.text().lower()
            self._table.setRowHidden(row, not visible)

    # ── Actions ──────────────────────────────────────────────────────

    def _on_create_tag(self) -> None:
        name = self._new_tag_input.text().strip()
        if not name:
            return
        # 检查重名
        existing = [t for t in self._tags if t["name"] == name]
        if existing:
            QMessageBox.warning(self, "重复标签", f"标签「{name}」已存在。")
            return
        try:
            new_id = db.create_tag(name, path=self._db_path)
            log.info("创建标签: id=%s name=%s", new_id, name)
            self._new_tag_input.clear()
            self._refresh_ui()
            # assign 模式下自动勾选新标签
            if self._mode == "assign":
                for cb in self._all_checkboxes:
                    if cb.property("tag_id") == new_id:
                        cb.setChecked(True)
                        break
        except Exception as e:
            log.error("创建标签失败: %s", e)
            QMessageBox.critical(self, "错误", f"创建标签失败: {e}")

    def _on_rename(self, row: int, tag: Dict) -> None:
        old_name = tag["name"]
        new_name, ok = QInputDialog.getText(
            self, "重命名标签", f"将「{old_name}」重命名为:", text=old_name
        )
        if not ok or not new_name.strip() or new_name.strip() == old_name:
            return
        new_name = new_name.strip()
        try:
            db.rename_tag(tag["id"], new_name, path=self._db_path)
            log.info("重命名标签: %d %s -> %s", tag["id"], old_name, new_name)
            self._refresh_ui()
        except Exception as e:
            log.error("重命名标签失败: %s", e)
            QMessageBox.critical(self, "错误", f"重命名标签失败: {e}")

    def _on_delete(self, row: int, tag: Dict) -> None:
        tag_name = tag["name"]
        count = tag["count"]
        msg = f"标签「{tag_name}」已关联 {count} 笔交易，删除后将移除所有关联。确定？"
        reply = QMessageBox.question(
            self, "确认删除", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            db.delete_tag(tag["id"], path=self._db_path)
            log.info("删除标签: %d %s", tag["id"], tag_name)
            self._refresh_ui()
        except Exception as e:
            log.error("删除标签失败: %s", e)
            QMessageBox.critical(self, "错误", f"删除标签失败: {e}")

    def _on_merge(self) -> None:
        source_id = self._source_combo.currentData()
        target_id = self._target_combo.currentData()
        if source_id is None or target_id is None or source_id == target_id:
            QMessageBox.warning(self, "无效合并", "源标签和目标标签不能相同。")
            return
        source_name = self._source_combo.currentText()
        target_name = self._target_combo.currentText()
        msg = f"将「{source_name}」合并入「{target_name}」，\n原标签将被删除。确定？"
        reply = QMessageBox.question(
            self, "确认合并", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            db.merge_tags(source_id, target_id, path=self._db_path)
            log.info("合并标签: %d(%s) -> %d(%s)", source_id, source_name, target_id, target_name)
            self._refresh_ui()
        except Exception as e:
            log.error("合并标签失败: %s", e)
            QMessageBox.critical(self, "错误", f"合并标签失败: {e}")

    def _on_accept(self) -> None:
        """点击底部操作按钮"""
        if self._mode == "manage":
            self.accept()
            return

        # assign 模式：收集所有勾选的 tag_ids，批量写入
        checked_ids: List[int] = []
        for cb in self._all_checkboxes:
            if cb.isChecked():
                tag_id = cb.property("tag_id")
                if tag_id is not None:
                    checked_ids.append(tag_id)
        try:
            db.batch_set_tags(self._tx_ids, checked_ids, path=self._db_path)
            log.info(
                "批量设置标签: %d 笔交易 -> %d 个标签",
                len(self._tx_ids), len(checked_ids),
            )
        except Exception as e:
            log.error("批量设置标签失败: %s", e)
            QMessageBox.critical(self, "错误", f"设置标签失败: {e}")
            return

        self.accept()
