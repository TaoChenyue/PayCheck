"""中国银行（BOC）流水单布局

列坐标基于 3.0x 缩放下的 BOC 银行流水单：
  记账日期(108) 记账时间(296) 币别(465) 金额(641) 余额(833)
  交易名称(1014) 渠道(1173) 网点名称(1360) 附言(1578)
  对方账户名(1801) 对方卡号/账号(2018) 对方开户行(2250)
跳过：币别、网点名称、对方开户行
"""

from typing import List, Tuple

from paycheck.ocr.layouts.base import BankLayout, Row


COLUMNS_3X = [
    ("date",         0,    202),
    ("time",         202,  380),
    ("amount",       553,  737),
    ("balance",      737,  923),
    ("tx_name",      923,  1093),
    ("channel",      1093, 1266),
    ("memo",         1469, 1689),
    ("counterparty", 1689, 1909),
    ("cp_account",   1909, 9999),
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

            cp = r.counterparty.strip()
            # cp_account 拼接在 counterparty 后
            # （cp_account 是 BOC 特有字段，Row 里没有定义，跳过）

            transactions.append({
                "date": r.date,
                "time": r.time,
                "dateTime": f"{r.date} {r.time}".strip() if r.date else "",
                "amount": amount,
                "balance": r.balance,
                "tx_name": r.tx_name.strip(),
                "channel": r.channel.strip(),
                "counterparty": cp,
                "memo": r.memo.strip(),
                "tx_type": tx_type,
            })
        return transactions
