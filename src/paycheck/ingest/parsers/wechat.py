"""微信 XLSX 账单解析"""

import os
from typing import List

import openpyxl

from paycheck.core.models import Transaction


HEADER_KEYWORDS = {
    "time": ["交易时间"],
    "category": ["交易类型", "交易分类"],
    "counterparty": ["交易对方"],
    "description": ["商品"],
    "tx_type": ["收/支"],
    "amount": ["金额"],
    "payment": ["支付方式", "收/付款方式"],
}

SUMMARY_KEYWORDS = ["总计", "合计", "开始", "结束", "导出", "---", "微信支付账单"]


def _find_header_row(data):
    """查找微信账单表头行"""
    for i, row in enumerate(data):
        if not isinstance(row, (list, tuple)):
            continue
        row_strs = [str(c) for c in row]
        if any("交易时间" in s for s in row_strs) and any("金额" in s for s in row_strs):
            return i
    return -1


def _map_columns(headers):
    """映射微信账单列名到标准字段"""
    col_map = {}
    for i, h in enumerate(headers):
        h_str = str(h).strip()
        for key, keywords in HEADER_KEYWORDS.items():
            if any(kw in h_str for kw in keywords):
                col_map[key] = i
                break
    return col_map


def parse_wechat_xlsx(filepath: str) -> List[Transaction]:
    """解析微信 XLSX 账单"""
    wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
    ws = wb.active
    data = [list(row) for row in ws.iter_rows(values_only=True)]
    wb.close()

    header_idx = _find_header_row(data)
    if header_idx == -1:
        print(f"  ⚠ 未找到微信账单表头: {os.path.basename(filepath)}")
        return []

    headers = data[header_idx]
    col_map = _map_columns(headers)

    if "time" not in col_map or "amount" not in col_map:
        print(f"  ⚠ 微信账单关键列缺失: {os.path.basename(filepath)}")
        return []

    transactions = []
    for i in range(header_idx + 1, len(data)):
        row = data[i]
        if not row or len(row) == 0:
            continue

        first_val = str(row[0]).strip()
        if any(kw in first_val for kw in SUMMARY_KEYWORDS) or first_val == "":
            continue

        time_str = str(row[col_map["time"]]).strip() if col_map["time"] < len(row) else ""
        if not time_str:
            continue

        amount_str = str(row[col_map["amount"]]).strip().replace(",", "").replace(" ", "") if col_map["amount"] < len(row) else ""
        try:
            amount = float(amount_str)
        except (ValueError, TypeError):
            continue

        tx_type_str = (
            str(row[col_map["tx_type"]]).strip()
            if col_map.get("tx_type") is not None and col_map["tx_type"] < len(row)
            else "支出"
        )

        transactions.append(
            Transaction(
                platform="wechat",
                time=time_str,
                category=str(row[col_map.get("category", -1)]).strip()
                if col_map.get("category") is not None and col_map["category"] < len(row) else "",
                counterparty=str(row[col_map.get("counterparty", -1)]).strip()
                if col_map.get("counterparty") is not None and col_map["counterparty"] < len(row) else "",
                description=str(row[col_map.get("description", -1)]).strip()
                if col_map.get("description") is not None and col_map["description"] < len(row) else "",
                amount=amount,
                tx_type=tx_type_str,
                payment_method=str(row[col_map.get("payment", -1)]).strip()
                if col_map.get("payment") is not None and col_map["payment"] < len(row) else "",
            )
        )

    return transactions
