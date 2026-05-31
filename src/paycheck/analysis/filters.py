"""交易过滤规则 — 内部转账检测

内部转账（充值、提现、理财等）是子账户间的资金流动，
不影响总资产，分析时应予剔除。

新增规则只需在此文件添加函数，然后在 filters() 中调用。
"""

from typing import Dict, List

from paycheck.core.models import Transaction


def is_internal_transfer(t: Transaction) -> bool:
    """判断一笔交易是否为内部转账"""
    # 支付宝：不计收支 = 内部资金流动
    if t.platform == "alipay" and t.tx_type == "不计收支":
        return True
    # 微信：充值/提现/零钱
    if t.platform == "wechat":
        cat = t.category or ""
        if "充值" in cat or "提现" in cat or "零钱" in cat:
            return True
    return False


def is_internal_transfer_from_dict(t: Dict) -> bool:
    """从 dict 版交易记录判断内部转账"""
    if t["platform"] == "alipay" and t["tx_type"] == "不计收支":
        return True
    if t["platform"] == "wechat":
        cat = t.get("category") or ""
        if "充值" in cat or "提现" in cat or "零钱" in cat:
            return True
    return False


def separate_internal(transactions: List[Dict]) -> tuple:
    """将交易分为内部转账和外部交易

    Returns:
        (internal_txs, external_txs)
    """
    internal = [t for t in transactions if is_internal_transfer_from_dict(t)]
    external = [t for t in transactions if not is_internal_transfer_from_dict(t)]
    return internal, external
