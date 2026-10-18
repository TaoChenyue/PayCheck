"""支付宝 CSV 解析：GBK 编码、~28 行信息头、12 列、明细值内嵌制表符"""

from __future__ import annotations

from paycheck_workbench.sources import ALIPAY_COLUMNS, SOURCE_ALIPAY

from .base import ParseResult, parse_csv_rows


def parse_alipay(text: str, file_name: str) -> ParseResult:
    # 表头行为「交易时间,…」；信息头在前 ~28 行，由 find_header 自动定位（设计 4.2）
    return parse_csv_rows(
        text,
        source=SOURCE_ALIPAY,
        file_name=file_name,
        columns=ALIPAY_COLUMNS,
        first_cell="交易时间",
    )
