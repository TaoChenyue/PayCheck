"""标签表达式 Chip 构建器 — 可视化集合运算表达式编辑器"""
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel,
    QFrame, QMenu, QSizePolicy, QScrollArea,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QAction
from typing import List, Optional, Dict, Union

from paycheck.core.tag_expr import validate_expression, ALL_TAG_ID, ALL_TAG_NAME


class TagChip(QFrame):
    """单个标签 Chip：标签名 + ×关闭按钮"""

    removed = Signal(int)

    def __init__(self, tag_id: int, tag_name: str, chip_index: int, parent=None):
        super().__init__(parent)
        self.tag_id = tag_id
        self.tag_name = tag_name
        self.chip_index = chip_index
        self.setFrameStyle(QFrame.StyledPanel | QFrame.Plain)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 4, 2)
        layout.setSpacing(4)

        layout.addWidget(QLabel(tag_name))

        close_btn = QPushButton("x")
        close_btn.setFixedSize(18, 18)
        close_btn.setFlat(True)
        close_btn.clicked.connect(lambda: self.removed.emit(self.chip_index))
        layout.addWidget(close_btn)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            builder = self._find_builder()
            if builder:
                builder._on_chip_clicked(self.chip_index)
        super().mousePressEvent(event)

    def _find_builder(self) -> Optional["TagBuilder"]:
        w = self.parent()
        while w:
            if isinstance(w, TagBuilder):
                return w
            w = w.parent()
        return None


class OpChip(QFrame):
    """运算符或括号 Chip"""

    def __init__(self, op_type: str, chip_index: int, parent=None):
        super().__init__(parent)
        self.op_type = op_type
        self.chip_index = chip_index
        self.setFrameStyle(QFrame.StyledPanel | QFrame.Plain)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(0)

        label = QLabel(op_type)
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            builder = self._find_builder()
            if builder:
                builder._on_chip_clicked(self.chip_index)
        super().mousePressEvent(event)

    def _find_builder(self) -> Optional["TagBuilder"]:
        w = self.parent()
        while w:
            if isinstance(w, TagBuilder):
                return w
            w = w.parent()
        return None


class TagBuilder(QWidget):
    """标签表达式 Chip 构建器"""

    execute_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._chips: List[Union[TagChip, OpChip]] = []
        self._cursor: int = 0
        self._tag_map: Dict[str, int] = {}
        self._tag_list: List[Dict] = []

        self._init_ui()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 4)
        root.setSpacing(4)

        # Chip 区域 (可滚动)
        self._chip_area_frame = QFrame()
        self._chip_area_frame.setFrameStyle(QFrame.StyledPanel | QFrame.Plain)
        self._chip_area_frame.setMinimumHeight(32)
        self._chip_area_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        self._chip_layout = QHBoxLayout(self._chip_area_frame)
        self._chip_layout.setContentsMargins(4, 4, 4, 4)
        self._chip_layout.setSpacing(4)
        self._chip_layout.addStretch()

        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll_area.setMaximumHeight(44)
        self._scroll_area.setMinimumHeight(36)
        self._scroll_area.setWidget(self._chip_area_frame)

        self._placeholder = QLabel("点击下方按钮添加标签或运算符")
        self._chip_layout.insertWidget(0, self._placeholder)

        root.addWidget(self._scroll_area)

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)

        self._btn_add_tag = QPushButton("添加标签")
        self._btn_add_tag.clicked.connect(self._show_tag_menu)
        btn_row.addWidget(self._btn_add_tag)

        for sym in ("∪", "∩", "-"):
            btn = QPushButton(sym)
            btn.clicked.connect(lambda checked, s=sym: self.insert_op(s))
            btn_row.addWidget(btn)

        for sym in ("(", ")"):
            btn = QPushButton(sym)
            btn.clicked.connect(lambda checked, s=sym: self.insert_op(s))
            btn_row.addWidget(btn)

        self._btn_clear = QPushButton("清空")
        self._btn_clear.clicked.connect(self.clear)
        btn_row.addWidget(self._btn_clear)

        self._btn_execute = QPushButton("执行筛选")
        self._btn_execute.clicked.connect(self._on_execute)
        btn_row.addWidget(self._btn_execute)

        btn_row.addStretch()
        root.addLayout(btn_row)

        # 状态行
        self._status_label = QLabel("")
        root.addWidget(self._status_label)

        self._rebuild_chips()

    # ── 公开 API ──

    def set_tag_data(self, tag_map: Dict[str, int], tag_list: List[Dict]):
        self._tag_map = tag_map
        self._tag_list = tag_list

    def restore_expression(self, text: str):
        """从表达式文本重建所有 Chip"""
        self.clear()
        if not text.strip():
            return
        # 预处理：在运算符和括号两侧插入空格
        _OPERATORS = "∪∩-()"
        chars = []
        for ch in text:
            if ch in _OPERATORS:
                chars.append(f" {ch} ")
            else:
                chars.append(ch)
        prepared = "".join(chars)
        for tok in prepared.split():
            if tok in ("∪", "∩", "-", "(", ")"):
                self.insert_op(tok)
            elif tok == ALL_TAG_NAME:
                self.insert_tag(ALL_TAG_ID, ALL_TAG_NAME)
            elif tok in self._tag_map:
                self.insert_tag(self._tag_map[tok], tok)

    def insert_tag(self, tag_id: int, tag_name: str):
        chip = TagChip(tag_id, tag_name, self._cursor)
        chip.removed.connect(self._on_chip_removed)
        self._chips.insert(self._cursor, chip)
        self._cursor += 1
        self._rebuild_chips()

    def insert_op(self, op_type: str):
        chip = OpChip(op_type, self._cursor)
        self._chips.insert(self._cursor, chip)
        self._cursor += 1
        self._rebuild_chips()

    def remove_chip(self, index: int):
        if 0 <= index < len(self._chips):
            chip = self._chips.pop(index)
            chip.deleteLater()
            if self._cursor > index:
                self._cursor -= 1
            self._cursor = max(0, min(self._cursor, len(self._chips)))
            self._rebuild_chips()

    def move_cursor(self, delta: int):
        self._cursor = max(0, min(self._cursor + delta, len(self._chips)))
        self._rebuild_chips()

    def get_expression_text(self) -> str:
        parts: List[str] = []
        for chip in self._chips:
            if isinstance(chip, TagChip):
                parts.append(chip.tag_name)
            elif isinstance(chip, OpChip):
                parts.append(chip.op_type)
        return " ".join(parts)

    def has_expression(self) -> bool:
        return len(self._chips) > 0

    def clear(self):
        for chip in self._chips:
            chip.deleteLater()
        self._chips.clear()
        self._cursor = 0
        self._rebuild_chips()

    # ── 内部方法 ──

    def _rebuild_chips(self):
        self._placeholder.setVisible(False)
        # 清空布局：chips 仅移除（保留以便重新添加），光标等临时控件销毁
        while self._chip_layout.count():
            item = self._chip_layout.takeAt(0)
            w = item.widget()
            if w is None:
                continue
            if w is self._placeholder:
                continue
            if isinstance(w, (TagChip, OpChip)):
                self._chip_layout.removeWidget(w)
            else:
                w.deleteLater()

        for i, chip in enumerate(self._chips):
            if i == self._cursor:
                self._chip_layout.addWidget(self._create_cursor())
            chip.chip_index = i
            self._chip_layout.addWidget(chip)

        if self._cursor == len(self._chips):
            self._chip_layout.addWidget(self._create_cursor())

        self._chip_layout.addStretch()

        if not self._chips:
            self._placeholder.setVisible(True)
            self._chip_layout.insertWidget(0, self._placeholder)

        self._validate()
        self._chip_area_frame.updateGeometry()
        QTimer.singleShot(0, self._scroll_to_cursor)

    def _create_cursor(self) -> QFrame:
        cursor = QFrame()
        cursor.setFrameStyle(QFrame.VLine | QFrame.Plain)
        cursor.setFixedSize(2, 20)
        return cursor

    def _scroll_to_cursor(self):
        hbar = self._scroll_area.horizontalScrollBar()
        if not hbar:
            return
        total_x = 8
        for i, chip in enumerate(self._chips):
            w = chip.sizeHint().width() + 4
            if i == self._cursor:
                break
            total_x += w
        hbar.setValue(min(total_x, hbar.maximum()))

    def _validate(self):
        text = self.get_expression_text()
        if not text.strip():
            self._status_label.setText("")
            self._btn_execute.setEnabled(True)
            return
        valid, error = validate_expression(text, self._tag_map)
        if valid:
            self._status_label.setText("表达式有效")
            self._btn_execute.setEnabled(True)
        else:
            self._status_label.setText(error)
            self._btn_execute.setEnabled(False)

    def _on_execute(self):
        text = self.get_expression_text()
        self.execute_requested.emit(text)

    def _on_chip_removed(self, index: int):
        self.remove_chip(index)

    def _on_chip_clicked(self, index: int):
        self._cursor = index + 1
        self._rebuild_chips()

    def _show_tag_menu(self):
        menu = QMenu(self)
        # "全部" 始终在第一位
        act = QAction(f"{ALL_TAG_NAME}  (全部交易)", menu)
        act.triggered.connect(
            lambda checked: self.insert_tag(ALL_TAG_ID, ALL_TAG_NAME)
        )
        menu.addAction(act)
        menu.addSeparator()

        if not self._tag_list:
            act = menu.addAction("(暂无标签)")
            act.setEnabled(False)
        else:
            for tag in self._tag_list:
                label = f"{tag['name']}  ({tag['count']})"
                act = QAction(label, menu)
                act.triggered.connect(
                    lambda checked, tid=tag["id"], tname=tag["name"]:
                        self.insert_tag(tid, tname)
                )
                menu.addAction(act)
        menu.exec(self._btn_add_tag.mapToGlobal(self._btn_add_tag.rect().bottomLeft()))

    # ── 键盘事件 ──

    def keyPressEvent(self, event):
        key = event.key()
        mods = event.modifiers()
        if key == Qt.Key_Left:
            self.move_cursor(-1)
            event.accept()
        elif key == Qt.Key_Right:
            self.move_cursor(1)
            event.accept()
        elif key == Qt.Key_Backspace:
            if self._cursor > 0:
                self.remove_chip(self._cursor - 1)
            event.accept()
        elif key == Qt.Key_Delete:
            if self._cursor < len(self._chips):
                self.remove_chip(self._cursor)
            event.accept()
        elif key == Qt.Key_Return and (mods & Qt.ControlModifier):
            if self._btn_execute.isEnabled():
                self._on_execute()
            event.accept()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos_in_chip = self._chip_area_frame.mapFromGlobal(event.globalPos())
            if not self._chip_area_frame.rect().contains(pos_in_chip):
                self.setFocus()
        super().mousePressEvent(event)
