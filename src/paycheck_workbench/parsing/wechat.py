"""微信账单解析：XLSX（Excel 序列号日期）与 CSV 变体，~15 行信息头，11 列"""

from __future__ import annotations

import io
import re
from datetime import datetime, timedelta
from typing import Any, List, Optional

from paycheck_workbench.sources import SOURCE_WECHAT, WECHAT_COLUMNS

from .base import HEADER_TOKEN, ParseError, ParseResult, ParsedRow, clean_value, parse_csv_rows

_EXCEL_EPOCH = datetime(1899, 12, 30)  # Excel 序列号基准日
_SERIAL_RE = re.compile(r"^\d{4,5}(\.\d+)?$")  # 序列号形态（如 45868.81）

# 收/支列下标：中性交易行在源文件中标记为 '/'（与「支付方式」的 '/' 无关）
_DIRECTION_IDX = WECHAT_COLUMNS.index("收/支")


def _normalize_direction(values: List[str]) -> List[str]:
    """收/支 '/' → 中性交易（设计 3.4：微信中性交易为第三种收支类型）。"""
    if values[_DIRECTION_IDX] == "/":
        values[_DIRECTION_IDX] = "中性交易"
    return values


def _excel_serial_to_text(value: float) -> str:
    """Excel 序列号 → 'YYYY-MM-DD HH:mm:ss'（设计 8.3）。"""
    days = int(value)
    frac = value - days
    dt = _EXCEL_EPOCH + timedelta(days=days, seconds=round(frac * 86400))
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _cell_to_text(value: Any, is_time: bool) -> str:
    """XLSX 单元格 → 文本；时间为序列号则转换，数值去掉多余小数点。"""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, float):
        if is_time:
            return _excel_serial_to_text(value)
        if value == int(value):
            return str(int(value))
        return repr(value)
    if isinstance(value, int):
        return str(value)
    text = str(value)
    if is_time and _SERIAL_RE.match(text):
        try:
            return _excel_serial_to_text(float(text))
        except ValueError:
            pass
    return text


def _rows_from_xlsx(data: bytes) -> List[List[Any]]:
    try:
        import openpyxl
    except ImportError as exc:  # pragma: no cover
        raise ParseError("缺少 openpyxl 依赖，无法解析 XLSX（请通过 uv sync 安装）") from exc
    try:
        workbook = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:
        raise ParseError(f"XLSX 文件无法打开：{exc}") from exc
    try:
        sheet = workbook.active
        return [list(row) for row in sheet.iter_rows(values_only=True)]
    finally:
        workbook.close()


def parse_wechat_xlsx(data: bytes, file_name: str) -> ParseResult:
    rows = _rows_from_xlsx(data)
    header_idx: Optional[int] = None
    for idx, row in enumerate(rows):
        first = row[0] if row else None
        if isinstance(first, str) and first.strip().startswith(HEADER_TOKEN):
            header_idx = idx
            break
    if header_idx is None:
        raise ParseError(
            f"未找到明细表头（首列应含「{HEADER_TOKEN}」），请确认 {file_name} 的格式是否正确"
        )

    header = [_cell_to_text(v, is_time=False) for v in rows[header_idx]]
    # 微信表头 11 列，无尾逗号；直接用与列数一致的判断
    header = [clean_value(v) for v in header][: len(WECHAT_COLUMNS)]
    while len(header) < len(WECHAT_COLUMNS):
        header.append("")
    if header != WECHAT_COLUMNS:
        got = "、".join(header)
        want = "、".join(WECHAT_COLUMNS)
        raise ParseError(f"表头不匹配：期望「{want}」，实际「{got}」")

    result = ParseResult(source=SOURCE_WECHAT, file_name=file_name, columns=list(WECHAT_COLUMNS))
    for row_no, row in enumerate(rows[header_idx + 1 :], start=header_idx + 2):
        if not any(v is not None and str(v).strip() for v in row):
            continue  # 空行
        values = [_cell_to_text(v, is_time=(i == 0)) for i, v in enumerate(row)]
        values = [clean_value(v) for v in values][: len(WECHAT_COLUMNS)]
        while len(values) < len(WECHAT_COLUMNS):
            values.append("")
        result.rows.append(ParsedRow(row_number=row_no, values=_normalize_direction(values)))
    return result


def parse_wechat_csv(text: str, file_name: str) -> ParseResult:
    """微信 CSV 变体：结构与 XLSX 相同（11 列），日期为文本或序列号。

    序列号形态的文本日期同样转换，保证入库后与 XLSX 口径一致。
    """
    result = parse_csv_rows(
        text,
        source=SOURCE_WECHAT,
        file_name=file_name,
        columns=WECHAT_COLUMNS,
        first_cell=HEADER_TOKEN,
    )
    for row in result.rows:
        time_value = row.values[0]
        if time_value and _SERIAL_RE.match(time_value):
            try:
                row.values[0] = _excel_serial_to_text(float(time_value))
            except ValueError:
                pass
        row.values = _normalize_direction(row.values)
    return result
