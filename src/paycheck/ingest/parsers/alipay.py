"""支付宝 CSV 账单解析（GBK 编码）"""

import logging
import os
from typing import List

from paycheck.core.models import Transaction
from paycheck.core.constants import (
    PARSER_COL_TIME, PARSER_COL_CATEGORY, PARSER_COL_COUNTERPARTY,
    PARSER_COL_DESCRIPTION, PARSER_COL_TX_TYPE, PARSER_COL_AMOUNT,
    PARSER_COL_PAYMENT,
)
from paycheck.ingest.csv_utils import parse_csv_line

log = logging.getLogger("paycheck.parser.alipay")


ALIPAY_ENCODINGS = ["gbk", "gb2312", "utf-8", "utf-16-le"]

HEADER_KEYWORDS = {
    PARSER_COL_TIME: ["交易时间"],
    PARSER_COL_CATEGORY: ["交易类型", "交易分类"],
    PARSER_COL_COUNTERPARTY: ["交易对方"],
    PARSER_COL_DESCRIPTION: ["商品"],
    PARSER_COL_TX_TYPE: ["收/支"],
    PARSER_COL_AMOUNT: ["金额"],
    PARSER_COL_PAYMENT: ["支付方式", "收/付款方式"],
}


def _decode_file(filepath: str) -> str:
    """尝试多种编码解码支付宝 CSV"""
    with open(filepath, "rb") as f:
        raw = f.read()
    for enc in ALIPAY_ENCODINGS:
        try:
            text = raw.decode(enc)
            if "交易时间" in text:
                return text
        except (UnicodeDecodeError, UnicodeError):
            continue
    return raw.decode("gbk", errors="ignore")


def _map_columns(headers):
    """映射支付宝 CSV 列名到标准字段"""
    col_map = {}
    for i, h in enumerate(headers):
        h_str = h.strip()
        for key, keywords in HEADER_KEYWORDS.items():
            if any(kw in h_str for kw in keywords):
                col_map[key] = i
                break
    return col_map


def parse_alipay_csv(filepath: str) -> List[Transaction]:
    """解析支付宝 CSV 账单"""
    text = _decode_file(filepath)
    lines = text.splitlines()

    # 找表头行
    header_idx = -1
    for i, line in enumerate(lines):
        if line.strip().startswith("交易时间") and "," in line:
            header_idx = i
            break

    if header_idx == -1:
        log.warning("未找到支付宝表头行: %s", os.path.basename(filepath))
        return []

    headers = parse_csv_line(lines[header_idx])
    col_map = _map_columns(headers)

    if PARSER_COL_TIME not in col_map or PARSER_COL_AMOUNT not in col_map:
        log.warning("支付宝关键列缺失: %s", os.path.basename(filepath))
        return []

    transactions = []
    for i in range(header_idx + 1, len(lines)):
        line = lines[i].strip()
        if not line:
            continue

        values = parse_csv_line(line)
        time_str = values[col_map[PARSER_COL_TIME]].strip() if col_map[PARSER_COL_TIME] < len(values) else ""
        if not time_str or time_str.lower() == "nan":
            continue

        amount_str = values[col_map[PARSER_COL_AMOUNT]].strip().replace(",", "").replace(" ", "") if col_map[PARSER_COL_AMOUNT] < len(values) else ""
        if not amount_str or amount_str.lower() == "nan":
            continue
        try:
            amount = float(amount_str)
        except (ValueError, TypeError):
            continue

        tx_type_str = (
            values[col_map[PARSER_COL_TX_TYPE]].strip()
            if col_map.get(PARSER_COL_TX_TYPE) is not None and col_map[PARSER_COL_TX_TYPE] < len(values)
            else "支出"
        )
        if not tx_type_str or tx_type_str.lower() == "nan":
            continue

        transactions.append(
            Transaction(
                platform="alipay",
                time=time_str,
                category=values[col_map.get(PARSER_COL_CATEGORY, -1)].strip()
                if col_map.get(PARSER_COL_CATEGORY) is not None and col_map[PARSER_COL_CATEGORY] < len(values) else "",
                counterparty=values[col_map.get(PARSER_COL_COUNTERPARTY, -1)].strip()
                if col_map.get(PARSER_COL_COUNTERPARTY) is not None and col_map[PARSER_COL_COUNTERPARTY] < len(values) else "",
                description=values[col_map.get(PARSER_COL_DESCRIPTION, -1)].strip()
                if col_map.get(PARSER_COL_DESCRIPTION) is not None and col_map[PARSER_COL_DESCRIPTION] < len(values) else "",
                amount=amount,
                tx_type=tx_type_str,
                payment_method=values[col_map.get(PARSER_COL_PAYMENT, -1)].strip()
                if col_map.get(PARSER_COL_PAYMENT) is not None and col_map[PARSER_COL_PAYMENT] < len(values) else "",
            )
        )

    return transactions
