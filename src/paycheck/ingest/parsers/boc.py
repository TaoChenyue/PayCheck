"""BOC 银行 CSV 账单解析（OCR 管线产出物）"""

import logging
import os
from typing import List

from paycheck.core.models import Transaction
from paycheck.ingest.csv_utils import parse_csv_line

log = logging.getLogger("paycheck.parser.boc")


BANK_CSV_HEADER = ["date", "time", "tx_type", "amount", "counterparty", "channel", "balance", "memo", "tx_name", "currency", "branch", "cp_account", "cp_bank"]


def _decode_file(filepath: str) -> str:
    """检测编码并解码银行 CSV（UTF-16 LE、UTF-8 BOM、UTF-8）"""
    with open(filepath, "rb") as f:
        raw = f.read()

    if len(raw) >= 2 and raw[0] == 0xFF and raw[1] == 0xFE:
        return raw.decode("utf-16-le")
    if len(raw) >= 2 and raw[0] == 0xFE and raw[1] == 0xFF:
        return raw.decode("utf-16-be")
    if len(raw) >= 3 and raw[0] == 0xEF and raw[1] == 0xBB and raw[2] == 0xBF:
        return raw[3:].decode("utf-8")
    return raw.decode("utf-8")


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

    if "date" not in col_map and "amount" not in col_map:
        log.warning("BOC CSV 缺少关键列: %s", os.path.basename(filepath))
        return []

    transactions = []
    for i in range(1, len(lines)):
        values = parse_csv_line(lines[i])

        date_str = values[col_map.get("date", -1)].strip() if col_map.get("date", -1) < len(values) else ""
        if not date_str:
            continue
        time_of_day = values[col_map.get("time", -1)].strip() if col_map.get("time") is not None and col_map["time"] < len(values) else ""
        full_time = f"{date_str} {time_of_day}".strip() if time_of_day else date_str

        amount_str = values[col_map.get("amount", -1)].strip() if col_map.get("amount", -1) < len(values) else ""
        if not amount_str:
            continue
        try:
            amount = float(amount_str)
        except (ValueError, TypeError):
            continue

        tx_type_str = values[col_map.get("tx_type", -1)].strip() if col_map.get("tx_type", -1) < len(values) else "支出"

        balance_str = values[col_map.get("balance", -1)].strip() if col_map.get("balance") is not None and col_map["balance"] < len(values) else ""
        try:
            balance = float(balance_str.replace(",", ""))
        except (ValueError, TypeError):
            balance = 0.0

        cp_account_str = values[col_map.get("cp_account", -1)].strip() if col_map.get("cp_account") is not None and col_map["cp_account"] < len(values) else ""
        currency_str = values[col_map.get("currency", -1)].strip() if col_map.get("currency") is not None and col_map["currency"] < len(values) else ""
        branch_str = values[col_map.get("branch", -1)].strip() if col_map.get("branch") is not None and col_map["branch"] < len(values) else ""
        cp_bank_str = values[col_map.get("cp_bank", -1)].strip() if col_map.get("cp_bank") is not None and col_map["cp_bank"] < len(values) else ""

        transactions.append(
            Transaction(
                platform="bank",
                time=full_time,
                category=values[col_map.get("tx_name", -1)].strip()
                if col_map.get("tx_name") is not None and col_map["tx_name"] < len(values) else "",
                counterparty=values[col_map.get("counterparty", -1)].strip()
                if col_map.get("counterparty") is not None and col_map["counterparty"] < len(values) else "",
                description=values[col_map.get("memo", -1)].strip()
                if col_map.get("memo") is not None and col_map["memo"] < len(values) else "",
                amount=amount,
                tx_type=tx_type_str,
                payment_method=values[col_map.get("channel", -1)].strip()
                if col_map.get("channel") is not None and col_map["channel"] < len(values) else "",
                balance=balance,
                currency=currency_str,
                branch=branch_str,
                cp_account=cp_account_str,
                cp_bank=cp_bank_str,
            )
        )

    return transactions
