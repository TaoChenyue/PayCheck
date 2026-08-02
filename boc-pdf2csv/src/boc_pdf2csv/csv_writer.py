"""CSV 读写工具

合并自:
  - ingest/csv_utils.py          (parse_csv_line)
  - pipeline._write_csv / _esc_csv (write_csv)
"""

import io
import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger("boc_pdf2csv.csv_writer")

# 13 列标准 CSV 表头
CSV_HEADER = [
    "date", "time", "tx_type", "amount", "counterparty", "channel",
    "balance", "memo", "tx_name", "currency", "branch", "cp_account", "cp_bank",
]

# 字段名 → CSV 列映射
_FIELD_MAP = {
    "date": "date",
    "time": "time",
    "tx_type": "tx_type",
    "amount": "amount",
    "counterparty": "counterparty",
    "channel": "channel",
    "balance": "balance",
    "memo": "memo",
    "tx_name": "tx_name",
    "currency": "currency",
    "branch": "branch",
    "cp_account": "cp_account",
    "cp_bank": "cp_bank",
}


def _esc_csv(s: Optional[str]) -> str:
    """CSV 字段转义"""
    if s is None:
        return ""
    s = str(s)
    if "," in s or '"' in s or "\n" in s:
        return '"' + s.replace('"', '""') + '"'
    return s


def write_csv(
    transactions: List[Dict[str, Any]],
    output_path: Optional[str] = None,
) -> str:
    """将交易记录列表写出为 CSV 文件

    输出 UTF-8 BOM 编码，确保 Windows Excel 兼容。

    Args:
        transactions: 交易字典列表
        output_path: 输出 CSV 路径（不指定则只返回字符串）

    Returns:
        CSV 内容字符串
    """
    csv_buf = io.StringIO()
    csv_buf.write("﻿")  # UTF-8 BOM
    csv_buf.write(",".join(CSV_HEADER) + "\n")

    for t in transactions:
        row = [
            _esc_csv(t.get("date", "")),
            _esc_csv(t.get("time", "")),
            _esc_csv(t.get("tx_type", "")),
            f"{t['amount']:.2f}" if isinstance(t.get("amount"), (int, float)) else "",
            _esc_csv(t.get("counterparty", "")),
            _esc_csv(t.get("channel", "")),
            f"{float(t['balance']):.2f}" if isinstance(t.get("balance"), (int, float)) else "0.00",
            _esc_csv(t.get("memo", "")),
            _esc_csv(t.get("tx_name", "")),
            _esc_csv(t.get("currency", "")),
            _esc_csv(t.get("branch", "")),
            _esc_csv(t.get("cp_account", "")),
            _esc_csv(t.get("cp_bank", "")),
        ]
        csv_buf.write(",".join(row) + "\n")

    csv_content = csv_buf.getvalue()
    csv_buf.close()

    if output_path:
        with open(output_path, "w", encoding="utf-8-sig") as f:
            f.write(csv_content)
        log.info("已写入: %s", output_path)

    return csv_content


def parse_csv_line(line: str) -> List[str]:
    """解析单行 CSV，正确处理引号包裹的字段"""
    result = []
    current = ""
    in_quotes = False
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == '"':
            if in_quotes and i + 1 < len(line) and line[i + 1] == '"':
                current += '"'
                i += 1
            else:
                in_quotes = not in_quotes
        elif ch == ',' and not in_quotes:
            result.append(current)
            current = ""
        else:
            current += ch
        i += 1
    result.append(current)
    return result
