"""解析器入口 — 根据文件路径自动选择解析器"""

import logging
import os
from typing import List

from paycheck.core.models import Transaction

log = logging.getLogger("paycheck.parser")


def parse_file(filepath: str) -> List[Transaction]:
    """根据文件路径自动选择解析器"""
    log.info("解析文件: %s", filepath)
    name = os.path.basename(filepath)
    path_parts = filepath.replace("\\", "/").split("/")

    # 微信目录下的 xlsx
    if "wechat" in path_parts and name.lower().endswith(".xlsx"):
        if name.startswith("~$"):
            log.debug("跳过文件: %s", filepath)
            return []
        log.debug("路由到: 微信解析器")
        from paycheck.ingest.parsers.wechat import parse_wechat_xlsx
        result = parse_wechat_xlsx(filepath)
        log.info("解析完成: %d 条交易", len(result))
        return result

    # 支付宝目录下的 csv
    if "ant" in path_parts and name.lower().endswith(".csv"):
        log.debug("路由到: 支付宝解析器")
        from paycheck.ingest.parsers.alipay import parse_alipay_csv
        result = parse_alipay_csv(filepath)
        log.info("解析完成: %d 条交易", len(result))
        return result

    # BOC 目录下的 csv
    if "boc" in path_parts and name.lower().endswith(".csv"):
        log.debug("路由到: BOC解析器")
        from paycheck.ingest.parsers.boc import parse_boc_csv
        result = parse_boc_csv(filepath)
        log.info("解析完成: %d 条交易", len(result))
        return result

    log.debug("未匹配到解析器: %s", filepath)
    return []
