"""解析层：按数据源分发，输出统一的 ParseResult

统一处理设计第 8 节的真实样本坑：
- 支付宝 GBK 编码 + 明细值内嵌制表符
- 微信 XLSX 的 Excel 序列号日期
- 支付宝/微信信息头自动定位表头行（首列含「交易时间」）
- BOC 尾列空值
"""

from __future__ import annotations

from pathlib import Path

from paycheck_workbench.sources import (
    ALLOWED_EXTENSIONS,
    SOURCE_ALIPAY,
    SOURCE_BOC,
    SOURCE_CONFIGS,
    SOURCE_WECHAT,
)

from .base import ParseError, ParseResult, ParsedRow, decode_csv_bytes

__all__ = ["ParseError", "ParseResult", "ParsedRow", "parse_file"]


def parse_file(source: str, file_name: str, data: bytes) -> ParseResult:
    """解析导入文件：按扩展名与数据源校验后分发。"""
    cfg = SOURCE_CONFIGS[source]
    ext = Path(file_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS[source]:
        allowed = "、".join(ALLOWED_EXTENSIONS[source])
        raise ParseError(f"{cfg.label} 只支持 {allowed} 文件（收到 {ext or '无扩展名'}）")

    if ext == ".xlsx" and source == SOURCE_WECHAT:
        from .wechat import parse_wechat_xlsx

        return parse_wechat_xlsx(data, file_name)

    text = decode_csv_bytes(data)
    if source == SOURCE_BOC:
        from .boc import parse_boc

        return parse_boc(text, file_name)
    if source == SOURCE_ALIPAY:
        from .alipay import parse_alipay

        return parse_alipay(text, file_name)
    if source == SOURCE_WECHAT:
        from .wechat import parse_wechat_csv

        return parse_wechat_csv(text, file_name)
    raise ParseError(f"未知数据源：{source}")
