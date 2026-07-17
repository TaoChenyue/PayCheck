"""交易明细面板 — 摘要卡片 + 标签筛选 + 分渠道表格。"""

import logging
from typing import List, Set

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout,
    QLabel, QGroupBox,
)
from PySide6.QtCore import Qt, Signal

from paycheck.storage import database as db
from paycheck.gui.tag_builder import TagBuilder
from paycheck.gui.tag_dialog import TagDialog
from paycheck.gui.table_renderer import TableRenderer
from paycheck.core.tag_expr import validate_expression, compile_expression
from paycheck.core.constants import (
    FIELD_PLATFORM, FIELD_TIME, FIELD_CATEGORY, FIELD_COUNTERPARTY,
    FIELD_DESCRIPTION, FIELD_AMOUNT, FIELD_TX_TYPE, FIELD_PAYMENT_METHOD,
    FIELD_BALANCE, FIELD_CURRENCY, FIELD_BRANCH, FIELD_CP_ACCOUNT,
    FIELD_CP_BANK, FIELD_ID,
)

log = logging.getLogger("paycheck.gui")


class DetailPanel(QWidget):
    """交易明细页：摘要卡片 + 标签筛选 + 分渠道表格。

    通过 TagBuilder 的 execute_requested Signal 触发标签筛选，
    筛选结果同时更新摘要卡片和表格显示。
    """

    status_message = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._all_transactions = []
        self._tag_map = {}
        self._tag_filter_ids: Set[int] | None = None

        layout = QVBoxLayout(self)

        # ── 摘要 ──
        summary_group = QGroupBox("摘要")
        summary_layout_inner = QGridLayout(summary_group)
        self._summary_labels = {}
        card_names = ["总支出", "总收入", "月均支出", "月均收入",
                      "微信", "支付宝", "银行", "总交易"]
        for i, name in enumerate(card_names):
            card = QGroupBox(name)
            card.setMinimumWidth(120)
            cl = QVBoxLayout(card)
            lbl = QLabel("-")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("font-size: 16px; font-weight: bold;")
            cl.addWidget(lbl)
            self._summary_labels[name] = lbl
            summary_layout_inner.addWidget(card, i // 4, i % 4)
        layout.addWidget(summary_group)

        # ── 标签筛选 ──
        self._tag_builder = TagBuilder()
        self._tag_builder.execute_requested.connect(self._on_tag_filter)
        layout.addWidget(self._tag_builder)

        # ── 交易表格 ──
        self._table_renderer = TableRenderer(self)
        layout.addWidget(self._table_renderer, 1)

    # ── 公共接口 ──

    def set_data(self, transactions: list, tag_map: dict):
        """设置交易数据和标签映射，更新摘要和表格。"""
        self._all_transactions = transactions
        self._tag_map = tag_map
        self._update_summary()
        self._table_renderer.set_data(transactions, self._tag_filter_ids)

    def refresh_tag_data(self, tags: list):
        """刷新标签数据到 TagBuilder。"""
        self._tag_map = {t["name"]: t["id"] for t in tags}
        self._tag_builder.set_tag_data(self._tag_map, tags)

    def restore_tag_filter(self):
        """从数据库恢复上次的标签筛选表达式。"""
        expr = db.get_setting("tag_expr", "")
        if expr:
            self._tag_builder.restore_expression(expr)
            self._on_tag_filter(expr)

    def handle_tag_shortcut(self):
        """处理 Ctrl+T 快捷键：为选中行批量打标签。"""
        tx_ids = self._get_selected_tx_ids()
        if not tx_ids:
            return
        dlg = TagDialog(self, db_path=db.DB_PATH, mode="assign", tx_ids=tx_ids)
        if dlg.exec():
            # 通知 MainWindow 重新加载数据
            return True  # 返回 True 表示需要刷新
        return False

    def open_tag_manager(self):
        """打开标签管理对话框。"""
        dlg = TagDialog(self, db_path=db.DB_PATH, mode="manage")
        if dlg.exec():
            return True
        return False

    @property
    def table_renderer(self) -> TableRenderer:
        """暴露表格渲染器供 MainWindow 访问。"""
        return self._table_renderer

    @property
    def tag_builder(self) -> TagBuilder:
        """暴露标签构建器供 MainWindow 访问。"""
        return self._tag_builder

    # ── 内部方法 ──

    def _get_selected_tx_ids(self) -> List[int]:
        """获取当前表格中选中行对应的交易 ID 列表。"""
        tbl = self._table_renderer.current_table
        selected = tbl.selectedIndexes()
        if not selected:
            return []
        selected_rows = set()
        for sel in selected:
            selected_rows.add(sel.row())
        tx_ids = []
        channel_data = self._table_renderer.get_current_filtered()
        for row in sorted(selected_rows):
            if row < len(channel_data):
                tx_id = channel_data[row].get(FIELD_ID)
                if tx_id is not None:
                    tx_ids.append(tx_id)
        return tx_ids

    def _on_tag_filter(self, expr_text: str):
        """TagBuilder 执行按钮回调 — 筛选交易并更新摘要/表格。"""
        if not expr_text.strip():
            self._tag_filter_ids = None
            db.set_setting("tag_expr", "")
        else:
            valid, error = validate_expression(expr_text, self._tag_map)
            if not valid:
                self.status_message.emit(f"标签表达式无效: {error}")
                return
            sql = compile_expression(expr_text, self._tag_map)
            conn = db._connect(db.DB_PATH)
            try:
                rows = conn.execute(sql).fetchall()
                self._tag_filter_ids = {r[0] for r in rows}
            finally:
                conn.close()
            db.set_setting("tag_expr", expr_text)
        self._update_summary()
        self._table_renderer.set_data(self._all_transactions, self._tag_filter_ids)

    def _update_summary(self):
        """根据当前标签筛选更新摘要卡片。"""
        if self._tag_filter_ids is not None:
            txs = [t for t in self._all_transactions if t.get(FIELD_ID) in self._tag_filter_ids]
        else:
            txs = self._all_transactions

        if not txs:
            for name in self._summary_labels:
                self._summary_labels[name].setText("-")
            return

        expenses = [t for t in txs if t.get(FIELD_TX_TYPE) == "支出"]
        incomes = [t for t in txs if t.get(FIELD_TX_TYPE) == "收入"]

        total_expense = sum(t[FIELD_AMOUNT] for t in expenses)
        total_income = sum(t[FIELD_AMOUNT] for t in incomes)

        expense_months = len(set(t[FIELD_TIME][:7] for t in expenses if t.get(FIELD_TIME))) or 1
        monthly_avg = round(total_expense / expense_months, 2)

        income_months = len(set(t[FIELD_TIME][:7] for t in incomes if t.get(FIELD_TIME))) or 1
        monthly_income = round(total_income / income_months, 2)

        def platform_total(ts, p):
            return sum(t[FIELD_AMOUNT] for t in ts if t.get(FIELD_PLATFORM) == p)

        wechat_exp = [t for t in expenses if t.get(FIELD_PLATFORM) == "wechat"]
        alipay_exp = [t for t in expenses if t.get(FIELD_PLATFORM) == "alipay"]
        bank_exp = [t for t in expenses if t.get(FIELD_PLATFORM) == "bank"]

        self._summary_labels["总支出"].setText(f"¥{total_expense:,.2f}")
        self._summary_labels["总收入"].setText(f"¥{total_income:,.2f}")
        self._summary_labels["月均支出"].setText(f"¥{monthly_avg:,.2f}")
        self._summary_labels["月均收入"].setText(f"¥{monthly_income:,.2f}")
        self._summary_labels["微信"].setText(f"¥{platform_total(expenses, 'wechat'):,.2f} / {len(wechat_exp)}笔")
        self._summary_labels["支付宝"].setText(f"¥{platform_total(expenses, 'alipay'):,.2f} / {len(alipay_exp)}笔")
        self._summary_labels["银行"].setText(f"¥{platform_total(expenses, 'bank'):,.2f} / {len(bank_exp)}笔")
        self._summary_labels["总交易"].setText(f"{len(expenses)} 笔")

    @property
    def status_text(self) -> str:
        """获取当前状态文本。"""
        if not self._all_transactions:
            return "请导入账单文件"
        if self._tag_filter_ids is not None:
            txs = [t for t in self._all_transactions if t.get(FIELD_ID) in self._tag_filter_ids]
        else:
            txs = self._all_transactions
        return f"共 {len(txs)} 条交易"
