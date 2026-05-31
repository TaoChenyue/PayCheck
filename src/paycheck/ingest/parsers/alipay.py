"""支付宝 CSV 账单解析（GBK 编码）"""

import logging
import os
from typing import List

from paycheck.core.models import Transaction
from paycheck.ingest.csv_utils import parse_csv_line

log = logging.getLogger("paycheck.parser.alipay")


ALIPAY_ENCODINGS = ["gbk", "gb2312", "utf-8", "utf-16-le"]

HEADER_KEYWORDS = {
    "time": ["交易时间"],
    "category": ["交易类型", "交易分类"],
    "counterparty": ["交易对方"],
    "description": ["商品"],
    "tx_type": ["收/支"],
    "amount": ["金额"],
    "payment": ["支付方式", "收/付款方式"],
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

    if "time" not in col_map or "amount" not in col_map:
        log.warning("支付宝关键列缺失: %s", os.path.basename(filepath))
        return []

    transactions = []
    for i in range(header_idx + 1, len(lines)):
        line = lines[i].strip()
        if not line:
            continue

        values = parse_csv_line(line)
        time_str = values[col_map["time"]].strip() if col_map["time"] < len(values) else ""
        if not time_str or time_str.lower() == "nan":
            continue

        amount_str = values[col_map["amount"]].strip().replace(",", "").replace(" ", "") if col_map["amount"] < len(values) else ""
        if not amount_str or amount_str.lower() == "nan":
            continue
        try:
            amount = float(amount_str)
        except (ValueError, TypeError):
            continue

        tx_type_str = (
            values[col_map["tx_type"]].strip()
            if col_map.get("tx_type") is not None and col_map["tx_type"] < len(values)
            else "支出"
        )
        if not tx_type_str or tx_type_str.lower() == "nan":
            continue

        transactions.append(
            Transaction(
                platform="alipay",
                time=time_str,
                category=values[col_map.get("category", -1)].strip()
                if col_map.get("category") is not None and col_map["category"] < len(values) else "",
                counterparty=values[col_map.get("counterparty", -1)].strip()
                if col_map.get("counterparty") is not None and col_map["counterparty"] < len(values) else "",
                description=values[col_map.get("description", -1)].strip()
                if col_map.get("description") is not None and col_map["description"] < len(values) else "",
                amount=amount,
                tx_type=tx_type_str,
                payment_method=values[col_map.get("payment", -1)].strip()
                if col_map.get("payment") is not None and col_map["payment"] < len(values) else "",
            )
        )

    return transactions
