"""表格渲染与列筛选 — 分渠道表格 + 筛选控件 + 数据渲染。"""

import logging
from typing import Set

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QFrame, QTabWidget, QDateEdit,
)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QDoubleValidator

from paycheck.core.constants import (
    FIELD_PLATFORM, FIELD_TIME, FIELD_CATEGORY, FIELD_COUNTERPARTY,
    FIELD_DESCRIPTION, FIELD_AMOUNT, FIELD_TX_TYPE, FIELD_PAYMENT_METHOD,
    FIELD_BALANCE, FIELD_CURRENCY, FIELD_BRANCH, FIELD_CP_ACCOUNT,
    FIELD_CP_BANK, FIELD_ID,
)

log = logging.getLogger("paycheck.gui")

CHANNEL_COLUMNS = {
    "wechat": [
        (FIELD_TIME, "交易时间", 160), (FIELD_CATEGORY, "交易类型", 90),
        (FIELD_COUNTERPARTY, "交易对方", 130), (FIELD_DESCRIPTION, "商品", 120),
        (FIELD_AMOUNT, "金额(元)", 100), (FIELD_TX_TYPE, "收/支", 60),
        (FIELD_PAYMENT_METHOD, "支付方式", 90),
    ],
    "alipay": [
        (FIELD_TIME, "交易时间", 160), (FIELD_CATEGORY, "交易分类", 90),
        (FIELD_COUNTERPARTY, "交易对方", 130), (FIELD_DESCRIPTION, "商品说明", 120),
        (FIELD_AMOUNT, "金额", 100), (FIELD_TX_TYPE, "收/支", 60),
        (FIELD_PAYMENT_METHOD, "收/付款方式", 90),
    ],
    "bank": [
        (FIELD_TIME, "交易时间", 160), (FIELD_CATEGORY, "交易名称", 100),
        (FIELD_COUNTERPARTY, "对方账户名", 130), (FIELD_DESCRIPTION, "附言", 100),
        (FIELD_AMOUNT, "金额", 100), (FIELD_TX_TYPE, "收支类型", 60),
        (FIELD_PAYMENT_METHOD, "渠道", 80), (FIELD_BALANCE, "余额", 100),
        (FIELD_CURRENCY, "币别", 50), (FIELD_BRANCH, "网点名称", 100),
        (FIELD_CP_ACCOUNT, "对方账号", 130), (FIELD_CP_BANK, "对方开户行", 120),
    ],
}

CHANNEL_NAMES = {"wechat": "微信", "alipay": "支付宝", "bank": "银行"}


class TableRenderer(QWidget):
    """分渠道表格渲染器，包含筛选行和表格控件。"""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._tables = {}
        self._col_filters = {"wechat": {}, "alipay": {}, "bank": {}}
        self._filter_frames = {}
        self._filter_widgets = {}

        self._all_transactions = []
        self._tag_filter_ids: Set[int] | None = None

        self._bank_tab_index = -1  # 银行标签页索引，初始化时记录

        self._tabs = QTabWidget()
        self._tabs.currentChanged.connect(self._on_tab_changed)

        for ch_key, ch_name in CHANNEL_NAMES.items():
            tab = QWidget()
            tab_layout = QVBoxLayout(tab)

            filter_frame = QFrame()
            filter_layout = QHBoxLayout(filter_frame)
            filter_layout.setContentsMargins(0, 0, 0, 0)
            filter_layout.setSpacing(2)
            tab_layout.addWidget(filter_frame)

            tbl = QTableWidget()
            tbl.setAlternatingRowColors(True)
            tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
            tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
            tbl.setSortingEnabled(True)
            tbl.horizontalHeader().setStretchLastSection(True)
            tab_layout.addWidget(tbl, 1)
            self._tables[ch_key] = tbl

            self._filter_frames[ch_key] = filter_frame

            idx = self._tabs.addTab(tab, ch_name)
            if ch_key == "bank":
                self._bank_tab_index = idx

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._tabs, 1)

    # ── 公共接口 ──

    def set_data(self, transactions: list, tag_filter_ids: Set[int] | None):
        """设置数据并渲染所有表格。"""
        self._all_transactions = transactions
        self._tag_filter_ids = tag_filter_ids
        self.render_all()

    def render_all(self):
        """渲染所有渠道表格（渲染当前活跃标签页）。"""
        self._render_current_tab()

    @property
    def tabs(self):
        """暴露 QTabWidget 供外部访问。"""
        return self._tabs

    @property
    def current_table(self):
        """获取当前活跃标签页的表格控件。"""
        idx = self._tabs.currentIndex()
        ch_key = ("wechat", "alipay", "bank")[idx] if 0 <= idx < 3 else "wechat"
        return self._tables[ch_key]

    @property
    def current_channel(self) -> str:
        """获取当前活跃标签页的渠道键名。"""
        idx = self._tabs.currentIndex()
        return ("wechat", "alipay", "bank")[idx] if 0 <= idx < 3 else "wechat"

    def get_current_filtered(self) -> list:
        """获取当前渠道筛选后的交易数据。"""
        ch_key = self.current_channel
        channel_data = [t for t in self._all_transactions if t.get(FIELD_PLATFORM) == ch_key]
        if self._tag_filter_ids is not None:
            channel_data = [t for t in channel_data if t.get(FIELD_ID) in self._tag_filter_ids]
        channel_data = self._apply_filters(channel_data, ch_key)
        return channel_data

    def set_tab_text(self, bank_idx: int, label: str):
        """设置银行标签页的文本。bank_idx 参数保留用于兼容性，实际使用内部索引。"""
        if 0 <= self._bank_tab_index < self._tabs.count():
            self._tabs.setTabText(self._bank_tab_index, label)

    # ── 内部方法 ──

    def _render_current_tab(self):
        ch_key = self.current_channel
        self._render_table(ch_key)

    def _on_tab_changed(self, _idx):
        if self._all_transactions:
            self._render_current_tab()

    # ── 筛选 ──

    def _on_apply_filters(self, channel: str):
        """从所有筛选控件收集值并执行筛选。"""
        new_filters = {}
        for item in self._filter_widgets.get(channel, []):
            wtype = item[0]
            if wtype == "text":
                _, col, inp = item
                text = inp.text().strip()
                if text:
                    new_filters[col] = text
            elif wtype == "range":
                _, col, lo, hi = item
                try:
                    lo_val = float(lo.text()) if lo.text().strip() else None
                except ValueError:
                    lo_val = None
                try:
                    hi_val = float(hi.text()) if hi.text().strip() else None
                except ValueError:
                    hi_val = None
                if lo_val is not None or hi_val is not None:
                    new_filters[f"{col}_range"] = (lo_val, hi_val)
            elif wtype == "combo":
                _, col, cb = item
                val = cb.currentText()
                if val and val != "全部":
                    new_filters[col] = val
            elif wtype == "date":
                _, col, frm, to = item
                d_from = frm.date() if frm.date() > frm.minimumDate() else None
                d_to = to.date() if to.date() > to.minimumDate() else None
                if d_from or d_to:
                    new_filters[f"{col}_range"] = (d_from, d_to)
        self._col_filters[channel] = new_filters
        self._render_table(channel)

    def _apply_filters(self, transactions: list, channel: str) -> list:
        """应用该渠道的列筛选（含文本/范围/下拉）。"""
        filters = self._col_filters.get(channel, {})
        if not filters:
            return transactions

        cols = CHANNEL_COLUMNS[channel]
        result = transactions

        for fkey, fval in filters.items():
            if isinstance(fkey, str) and fkey.endswith("_range"):
                col_idx = int(fkey.replace("_range", ""))
                key = cols[col_idx][0] if col_idx < len(cols) else None
                if not key:
                    continue
                lo, hi = fval
                # 金额范围（float）
                if isinstance(lo, (int, float)) or isinstance(hi, (int, float)):
                    if lo is not None:
                        result = [t for t in result if float(t.get(key, 0)) >= lo]
                    if hi is not None:
                        result = [t for t in result if float(t.get(key, 0)) <= hi]
                # 日期范围（QDate）
                elif lo is not None or hi is not None:
                    if lo:
                        s = lo.toString("yyyy-MM")
                        result = [t for t in result if (t.get(FIELD_TIME, "") or "") >= s]
                    if hi:
                        s = hi.toString("yyyy-MM")
                        result = [t for t in result if (t.get(FIELD_TIME, "") or "")[:7] <= s]
            else:
                col_idx = fkey
                key = cols[col_idx][0] if isinstance(col_idx, int) and col_idx < len(cols) else None
                if not key:
                    continue
                val = str(fval).lower()
                result = [t for t in result if val in str(t.get(key, "")).lower()]

        return result

    # ── 筛选行构建 ──

    def _build_filter_row(self, channel: str, cols: list):
        """重建筛选行，根据列类型适配控件。"""
        frame = self._filter_frames.get(channel)
        if not frame:
            return

        fl = frame.layout()
        while fl.count():
            item = fl.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        QWidget().setLayout(fl)  # 废弃旧 layout
        grid = QGridLayout(frame)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(4)
        max_cols = 5
        for c in range(max_cols):
            grid.setColumnStretch(c, 1)

        filters = self._col_filters.get(channel, {})
        self._filter_widgets[channel] = []
        for i, (key, title, _) in enumerate(cols):
            card = QFrame()
            card.setFrameStyle(QFrame.StyledPanel | QFrame.Plain)
            wrapper = QHBoxLayout(card)
            wrapper.setContentsMargins(4, 2, 4, 2)
            wrapper.setSpacing(2)
            lbl = QLabel(title)
            lbl.setStyleSheet("color: #555;")
            wrapper.addWidget(lbl)

            if key in (FIELD_AMOUNT, FIELD_BALANCE):
                row = QHBoxLayout()
                lo = QLineEdit(); lo.setPlaceholderText("最低"); lo.setMinimumWidth(80)
                hi = QLineEdit(); hi.setPlaceholderText("最高"); hi.setMinimumWidth(80)

                rng = filters.get(f"{i}_range")
                if rng:
                    if rng[0] is not None:
                        lo.setText(str(rng[0]))
                    if rng[1] is not None:
                        hi.setText(str(rng[1]))

                self._filter_widgets[channel].append(("range", i, lo, hi))
                row.addWidget(lo, 1); row.addWidget(QLabel("~")); row.addWidget(hi, 1)
                wrapper.addLayout(row, 1)
            elif key == FIELD_TX_TYPE:
                cb = QComboBox()
                cb.addItems(["全部", "支出", "收入", "不计收支"])
                if i in filters:
                    idx_found = cb.findText(filters[i])
                    if idx_found >= 0:
                        cb.setCurrentIndex(idx_found)

                self._filter_widgets[channel].append(("combo", i, cb))
                wrapper.addWidget(cb, 1)
            elif key == FIELD_TIME:
                times = [t.get(FIELD_TIME, "")[:7] for t in self._all_transactions
                         if t.get(FIELD_PLATFORM) == channel and t.get(FIELD_TIME)]
                if times:
                    min_t = min(times)
                    max_t = max(times)
                    min_date = QDate(int(min_t[:4]), int(min_t[5:7]), 1)
                    max_date = QDate(int(max_t[:4]), int(max_t[5:7]), 1)
                else:
                    min_date = QDate(2020, 1, 1)
                    max_date = QDate.currentDate()

                row = QHBoxLayout()
                frm = QDateEdit(); frm.setCalendarPopup(True); frm.setDisplayFormat("yyyy-MM")
                frm.setDateRange(min_date, max_date)
                to = QDateEdit(); to.setCalendarPopup(True); to.setDisplayFormat("yyyy-MM")
                to.setDateRange(min_date, max_date)

                rng = filters.get(f"{i}_range")
                frm.blockSignals(True)
                to.blockSignals(True)
                if rng and rng[0]:
                    frm.setDate(rng[0])
                else:
                    frm.setDate(min_date)
                if rng and rng[1]:
                    to.setDate(rng[1])
                else:
                    to.setDate(max_date)
                frm.blockSignals(False)
                to.blockSignals(False)

                self._filter_widgets[channel].append(("date", i, frm, to))
                row.addWidget(frm, 1); row.addWidget(QLabel("~")); row.addWidget(to, 1)
                wrapper.addLayout(row, 1)
            else:
                inp = QLineEdit()
                if i in filters:
                    inp.setText(str(filters[i]))

                self._filter_widgets[channel].append(("text", i, inp))
                wrapper.addWidget(inp, 1)
            grid.addWidget(card, i // max_cols, i % max_cols)

        # 筛选按钮
        filter_btn = QPushButton("筛选")
        filter_btn.clicked.connect(lambda checked, ch=channel: self._on_apply_filters(ch))
        grid.addWidget(filter_btn, ((len(cols)) // max_cols), (len(cols)) % max_cols)

    # ── 表格渲染 ──

    def _render_table(self, channel: str):
        cols = CHANNEL_COLUMNS[channel]
        tbl = self._tables[channel]

        self._build_filter_row(channel, cols)

        filtered = [t for t in self._all_transactions if t.get(FIELD_PLATFORM) == channel]
        if self._tag_filter_ids is not None:
            filtered = [t for t in filtered if t.get(FIELD_ID) in self._tag_filter_ids]
        filtered = self._apply_filters(filtered, channel)
        total = len(filtered)

        tbl.clear()
        tbl.setColumnCount(len(cols))
        tbl.setRowCount(total)
        tbl.setHorizontalHeaderLabels([c[1] for c in cols])

        for r, t in enumerate(filtered):
            for c, (key, _, _) in enumerate(cols):
                val = t.get(key, "")
                if key == FIELD_AMOUNT:
                    try:
                        val = f"¥{float(val):,.2f}"
                    except (ValueError, TypeError):
                        val = ""
                item = QTableWidgetItem(str(val) if val is not None else "")
                item.setTextAlignment(Qt.AlignRight if key == FIELD_AMOUNT else Qt.AlignLeft)
                tbl.setItem(r, c, item)

        header = tbl.horizontalHeader()
        for i in range(len(cols)):
            header.setSectionResizeMode(i, QHeaderView.Stretch)
