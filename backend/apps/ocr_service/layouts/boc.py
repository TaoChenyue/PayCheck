"""中国银行（BOC）流水单布局

列坐标基于 3.0x 缩放下的 BOC 银行流水单：
  记账日期(108) 记账时间(296) 币别(465) 金额(641) 余额(833)
  交易名称(1014) 渠道(1173) 网点名称(1360) 附言(1578)
  对方账户名(1801) 对方卡号/账号(2018) 对方开户行(2250)
"""

import logging

from typing import List, Tuple

from apps.ocr_service.layouts.base import BankLayout, Row

# ── 常量 ──
FIELD_TIME = "time"
FIELD_AMOUNT = "amount"
FIELD_COUNTERPARTY = "counterparty"
FIELD_TX_TYPE = "tx_type"
FIELD_BALANCE = "balance"
FIELD_CURRENCY = "currency"
FIELD_BRANCH = "branch"
FIELD_CP_ACCOUNT = "cp_account"
FIELD_CP_BANK = "cp_bank"
BANK_COL_DATE = "date"
BANK_COL_CHANNEL = "channel"
BANK_COL_MEMO = "memo"
BANK_COL_TX_NAME = "tx_name"


log = logging.getLogger("paycheck.layout.boc")


COLUMNS_3X = [
    (BANK_COL_DATE,         0,    202),
    (FIELD_TIME,         202,  380),
    (FIELD_CURRENCY,     380,  553),
    (FIELD_AMOUNT,       553,  737),
    (FIELD_BALANCE,      737,  923),
    (BANK_COL_TX_NAME,      923,  1093),
    (BANK_COL_CHANNEL,      1093, 1266),
    (FIELD_BRANCH,       1266, 1469),
    (BANK_COL_MEMO,         1469, 1689),
    (FIELD_COUNTERPARTY, 1689, 1909),
    (FIELD_CP_ACCOUNT,   1909, 2180),
    (FIELD_CP_BANK,      2180, 9999),
]


class BocLayout(BankLayout):
    """中国银行流水单布局"""

    @property
    def name(self) -> str:
        return "boc"

    @property
    def columns(self) -> List[Tuple[str, int, int]]:
        return COLUMNS_3X

    def to_transactions(self, rows: List[Row]) -> List[dict]:
        """将 BOC 行数据转为标准交易记录

        不做字符级清洗，完全依赖 OCR 原始值。
        amount 正数为收入，负数为支出。
        """
        transactions = []
        for r in rows:
            if not r.date and not r.amount:
                continue

            try:
                raw_amount = float(r.amount.replace(",", ""))
            except (ValueError, TypeError):
                continue

            tx_type = "支出" if raw_amount < 0 else "收入"
            amount = abs(raw_amount)

            try:
                balance = float(r.balance.replace(",", ""))
            except (ValueError, TypeError):
                balance = 0.0

            cp = r.counterparty.strip()

            transactions.append({
                BANK_COL_DATE: r.date,
                FIELD_TIME: r.time,
                "dateTime": f"{r.date} {r.time}".strip() if r.date else "",
                FIELD_AMOUNT: amount,
                FIELD_BALANCE: balance,
                BANK_COL_TX_NAME: r.tx_name.strip(),
                BANK_COL_CHANNEL: r.channel.strip(),
                FIELD_COUNTERPARTY: cp,
                BANK_COL_MEMO: r.memo.strip(),
                FIELD_TX_TYPE: tx_type,
                FIELD_CURRENCY: r.currency.strip(),
                FIELD_BRANCH: r.branch.strip(),
                FIELD_CP_ACCOUNT: r.cp_account.strip(),
                FIELD_CP_BANK: r.cp_bank.strip(),
            })
        log.info("BOC转换: %d 行 → %d 条交易", len(rows), len(transactions))
        return transactions
