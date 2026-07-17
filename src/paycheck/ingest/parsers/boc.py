"""BOC 银行 CSV 账单解析（OCR 管线产出物）"""

import logging
import os
from typing import List

from paycheck.core.models import Transaction
from paycheck.core.constants import (
    FIELD_PLATFORM, FIELD_TIME, FIELD_CATEGORY, FIELD_COUNTERPARTY,
    FIELD_DESCRIPTION, FIELD_AMOUNT, FIELD_TX_TYPE, FIELD_PAYMENT_METHOD,
    FIELD_BALANCE, FIELD_CURRENCY, FIELD_BRANCH, FIELD_CP_ACCOUNT,
    FIELD_CP_BANK, BANK_COL_DATE, BANK_COL_CHANNEL, BANK_COL_MEMO,
    BANK_COL_TX_NAME,
)
from paycheck.ingest.csv_utils import parse_csv_line

log = logging.getLogger("paycheck.parser.boc")


BANK_CSV_HEADER = [BANK_COL_DATE, FIELD_TIME, FIELD_TX_TYPE, FIELD_AMOUNT, FIELD_COUNTERPARTY, BANK_COL_CHANNEL, FIELD_BALANCE, BANK_COL_MEMO, BANK_COL_TX_NAME, FIELD_CURRENCY, FIELD_BRANCH, FIELD_CP_ACCOUNT, FIELD_CP_BANK]


def _decode_file(filepath: str) -> str:
    """检测编码并解码银行 CSV"""
    with open(filepath, "rb") as f:
        raw = f.read()

    # BOM 检测
    if len(raw) >= 2 and raw[0] == 0xFF and raw[1] == 0xFE:
        return raw.decode("utf-16-le")
    if len(raw) >= 2 and raw[0] == 0xFE and raw[1] == 0xFF:
        return raw.decode("utf-16-be")
    if len(raw) >= 3 and raw[0] == 0xEF and raw[1] == 0xBB and raw[2] == 0xBF:
        return raw[3:].decode("utf-8")

    # 无 BOM：先试 UTF-8，失败回退 GBK
    for enc in ("utf-8", "gbk", "gb2312", "utf-16-le"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return raw.decode("utf-8", errors="ignore")


def parse_boc_csv(filepath: str) -> List[Transaction]:
    """解析 BOC 银行 CSV（OCR 生成）"""
    text = _decode_file(filepath)
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    if not lines:
        return []

    headers = parse_csv_line(lines[0])
    col_map = {}
    for i, h in enumerate(headers):
        h_lower = h.strip().lower()
        if h_lower in BANK_CSV_HEADER:
            col_map[h_lower] = i

    if BANK_COL_DATE not in col_map and FIELD_AMOUNT not in col_map:
        log.warning("BOC CSV 缺少关键列: %s", os.path.basename(filepath))
        return []

    transactions = []
    for i in range(1, len(lines)):
        values = parse_csv_line(lines[i])

        date_str = values[col_map.get(BANK_COL_DATE, -1)].strip() if col_map.get(BANK_COL_DATE, -1) < len(values) else ""
        if not date_str:
            continue
        time_of_day = values[col_map.get(FIELD_TIME, -1)].strip() if col_map.get(FIELD_TIME) is not None and col_map[FIELD_TIME] < len(values) else ""
        full_time = f"{date_str} {time_of_day}".strip() if time_of_day else date_str

        amount_str = values[col_map.get(FIELD_AMOUNT, -1)].strip() if col_map.get(FIELD_AMOUNT, -1) < len(values) else ""
        if not amount_str:
            continue
        try:
            amount = float(amount_str)
        except (ValueError, TypeError):
            continue

        tx_type_str = values[col_map.get(FIELD_TX_TYPE, -1)].strip() if col_map.get(FIELD_TX_TYPE, -1) < len(values) else "支出"

        balance_str = values[col_map.get(FIELD_BALANCE, -1)].strip() if col_map.get(FIELD_BALANCE) is not None and col_map[FIELD_BALANCE] < len(values) else ""
        try:
            balance = float(balance_str.replace(",", ""))
        except (ValueError, TypeError):
            balance = 0.0

        cp_account_str = values[col_map.get(FIELD_CP_ACCOUNT, -1)].strip() if col_map.get(FIELD_CP_ACCOUNT) is not None and col_map[FIELD_CP_ACCOUNT] < len(values) else ""
        currency_str = values[col_map.get(FIELD_CURRENCY, -1)].strip() if col_map.get(FIELD_CURRENCY) is not None and col_map[FIELD_CURRENCY] < len(values) else ""
        branch_str = values[col_map.get(FIELD_BRANCH, -1)].strip() if col_map.get(FIELD_BRANCH) is not None and col_map[FIELD_BRANCH] < len(values) else ""
        cp_bank_str = values[col_map.get(FIELD_CP_BANK, -1)].strip() if col_map.get(FIELD_CP_BANK) is not None and col_map[FIELD_CP_BANK] < len(values) else ""

        transactions.append(
            Transaction(
                platform="bank",
                time=full_time,
                category=values[col_map.get(BANK_COL_TX_NAME, -1)].strip()
                if col_map.get(BANK_COL_TX_NAME) is not None and col_map[BANK_COL_TX_NAME] < len(values) else "",
                counterparty=values[col_map.get(FIELD_COUNTERPARTY, -1)].strip()
                if col_map.get(FIELD_COUNTERPARTY) is not None and col_map[FIELD_COUNTERPARTY] < len(values) else "",
                description=values[col_map.get(BANK_COL_MEMO, -1)].strip()
                if col_map.get(BANK_COL_MEMO) is not None and col_map[BANK_COL_MEMO] < len(values) else "",
                amount=amount,
                tx_type=tx_type_str,
                payment_method=values[col_map.get(BANK_COL_CHANNEL, -1)].strip()
                if col_map.get(BANK_COL_CHANNEL) is not None and col_map[BANK_COL_CHANNEL] < len(values) else "",
                balance=balance,
                currency=currency_str,
                branch=branch_str,
                cp_account=cp_account_str,
                cp_bank=cp_bank_str,
            )
        )

    return transactions
