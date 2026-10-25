"""现有 boc-pdf2csv 工具回归：包导入与版本不受工作台改动影响"""

from __future__ import annotations


def test_boc_pdf2csv_importable():
    import boc_pdf2csv

    assert boc_pdf2csv.__version__ == "1.1.0"


def test_boc_pdf2csv_public_api():
    from boc_pdf2csv import FolderResult, process_folder, process_pdf

    assert callable(process_pdf)
    assert callable(process_folder)
    assert FolderResult is not None


def test_rows_to_transactions_amount_space_cleaning():
    """OCR 常把负号与数字分离（"- 8 8 . 00"）：剔除金额内空格后按数值解析，
    不再丢弃负数交易（测试侧观察项回归）。"""
    from boc_pdf2csv.layout import Row, rows_to_transactions

    txns = rows_to_transactions([
        Row(date="2026-10-01", time="10:00:00", amount="- 8 8 . 00", counterparty="示例商户"),
        Row(date="2026-10-02", time="10:00:00", amount="3, 0 0 0 . 0 0", counterparty="示例公司"),
        Row(date="2026-10-03", time="10:00:00", amount="无效", counterparty="示例商户"),
    ])
    assert len(txns) == 2
    assert txns[0]["tx_type"] == "支出"
    assert txns[0]["amount"] == 88.0
    assert txns[1]["tx_type"] == "收入"
    assert txns[1]["amount"] == 3000.0
