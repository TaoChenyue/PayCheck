"""解析器入口 — 根据文件路径自动选择解析器"""

import os
from typing import List

from paycheck.core.models import Transaction


def parse_file(filepath: str) -> List[Transaction]:
    """根据文件路径自动选择解析器"""
    name = os.path.basename(filepath)
    path_parts = filepath.replace("\\", "/").split("/")

    # 微信目录下的 xlsx
    if "wechat" in path_parts and name.lower().endswith(".xlsx"):
        if name.startswith("~$"):
            return []
        from paycheck.ingest.parsers.wechat import parse_wechat_xlsx
        return parse_wechat_xlsx(filepath)

    # 支付宝目录下的 csv
    if "ant" in path_parts and name.lower().endswith(".csv"):
        from paycheck.ingest.parsers.alipay import parse_alipay_csv
        return parse_alipay_csv(filepath)

    # BOC 目录下的 csv
    if "boc" in path_parts and name.lower().endswith(".csv"):
        from paycheck.ingest.parsers.boc import parse_boc_csv
        return parse_boc_csv(filepath)

    return []
