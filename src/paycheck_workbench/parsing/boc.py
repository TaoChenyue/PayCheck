"""BOC CSV 解析：UTF-8 BOM + CRLF，首行即表头，13 列（尾列可能为空）"""

from __future__ import annotations

from paycheck_workbench.sources import BOC_COLUMNS, SOURCE_BOC

from .base import ParseResult, parse_csv_rows


def parse_boc(text: str, file_name: str) -> ParseResult:
    return parse_csv_rows(
        text,
        source=SOURCE_BOC,
        file_name=file_name,
        columns=BOC_COLUMNS,
        first_row_is_header=True,
    )
