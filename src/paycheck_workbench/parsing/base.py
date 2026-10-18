"""解析层公共工具：CSV 解码、表头定位、行规整"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# 表头定位规则：首个单元格以该串开头的行即明细表头（设计 4.2）
HEADER_TOKEN = "交易时间"


class ParseError(Exception):
    """文件无法解析（编码异常 / 未找到明细表头 / 结构不符）"""


@dataclass
class ParsedRow:
    """一条已规整的明细。row_number 为文件内行号（1 起，含信息头），用于失败定位。"""

    row_number: int
    values: List[str]

    def as_dict(self, columns: List[str]) -> dict:
        return dict(zip(columns, self.values))


@dataclass
class ParseResult:
    source: str
    file_name: str
    columns: List[str]
    rows: List[ParsedRow] = field(default_factory=list)
    errors: List[dict] = field(default_factory=list)  # {"row": N, "reason": ...}


def decode_csv_bytes(data: bytes) -> str:
    """按 UTF-8(BOM) → GBK 顺序解码：覆盖 BOC/微信的 UTF-8 与支付宝的 GBK。"""
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig")
    for enc in ("utf-8", "gbk"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ParseError("无法识别文件编码（尝试了 UTF-8 与 GBK）")


def read_csv_rows(text: str) -> List[Tuple[int, List[str]]]:
    """csv 整体解析（兼容引号内换行），返回 (reader 行号, 字段列表)。"""
    return list(enumerate(csv.reader(io.StringIO(text, newline="")), start=1))


def find_header(
    rows: List[Tuple[int, List[str]]],
    first_cell: str,
    fallback: Optional[str] = None,
) -> Optional[int]:
    """返回表头所在的下标；找不到时若给了 fallback 则按它匹配。"""
    tokens = [first_cell]
    if fallback:
        tokens.append(fallback)
    for idx, (_, row) in enumerate(rows):
        if row and any(row[0].strip().startswith(t) for t in tokens):
            return idx
    return None


def clean_value(value: str) -> str:
    """去除明细值内嵌的制表符与回车（支付宝订单号字段内确有 \\t，设计 8.1）。"""
    return value.replace("\t", "").replace("\r", "")


def normalize_row(
    row: List[str], expected: int
) -> Tuple[List[str], Optional[str]]:
    """规整为恰好 expected 列：清洗制表符、去尾空列、不足补空。

    返回 (values, error)；error 非空表示该行无法入库。
    """
    values = [clean_value(v) for v in row]
    while len(values) > expected and values[-1] == "":
        values.pop()  # 表头/数据行末尾的尾逗号（支付宝样本为 13 段）
    if len(values) > expected:
        return values[:expected], f"列数不符（{len(values)} 列，期望 {expected} 列）"
    while len(values) < expected:
        values.append("")
    return values, None


def parse_csv_rows(
    text: str,
    source: str,
    file_name: str,
    columns: List[str],
    *,
    first_cell: str = HEADER_TOKEN,
    first_row_is_header: bool = False,
) -> ParseResult:
    """CSV 类源的统一解析骨架。

    - 自动定位表头行（BOC 首行即表头；支付宝/微信跳过信息头）
    - 每行按列数校验，异常行进入 errors 不阻断整体
    """
    reader_rows = read_csv_rows(text)
    if first_row_is_header:
        header_idx = 0
        while header_idx < len(reader_rows) and not reader_rows[header_idx][1]:
            header_idx += 1  # 跳过文件开头的空行
    else:
        header_idx = find_header(reader_rows, first_cell)
    if header_idx is None:
        raise ParseError(
            f"未找到明细表头（首列应含「{first_cell}」），请确认 {file_name} 的格式是否正确"
        )

    header_row = reader_rows[header_idx][1]
    header, header_err = normalize_row(header_row, len(columns))
    if header_err or header != columns:
        got = "、".join(header[: len(columns)])
        want = "、".join(columns)
        raise ParseError(f"表头不匹配：期望「{want}」，实际「{got}」")

    result = ParseResult(source=source, file_name=file_name, columns=list(columns))
    for reader_no, row in reader_rows[header_idx + 1 :]:
        if not any(v.strip() for v in row):
            continue  # 空行
        values, err = normalize_row(row, len(columns))
        if err:
            result.errors.append({"row": reader_no, "reason": err})
            continue
        result.rows.append(ParsedRow(row_number=reader_no, values=values))
    return result
