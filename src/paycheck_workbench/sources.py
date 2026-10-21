"""数据源元信息：列定义、逻辑列（展示/详情）、筛选与排序维度（设计文档第 3、5 节的落地）

- 明细列（columns）：源文件列全量入库，顺序与源文件一致。
- 逻辑列（logical_columns）：表格/详情呈现的列。BOC 的「记账时间」由 date+time
  两物理列合并；visible=False 的列在行展开详情中呈现（低频列默认隐藏，设计 3.5）。
"""

from __future__ import annotations

from typing import Dict, List

SOURCE_BOC = "boc"
SOURCE_ALIPAY = "alipay"
SOURCE_WECHAT = "wechat"

SOURCES = (SOURCE_BOC, SOURCE_ALIPAY, SOURCE_WECHAT)

# 允许导入的文件扩展名（BOC/支付宝限 CSV，微信 XLSX 兼容 CSV）
ALLOWED_EXTENSIONS: Dict[str, List[str]] = {
    SOURCE_BOC: [".csv"],
    SOURCE_ALIPAY: [".csv"],
    SOURCE_WECHAT: [".xlsx", ".csv"],
}

# ---- 明细列（源文件全量保留，顺序与源文件一致）----
BOC_COLUMNS = [
    "date", "time", "tx_type", "amount", "counterparty", "channel",
    "balance", "memo", "tx_name", "currency", "branch", "cp_account", "cp_bank",
]
ALIPAY_COLUMNS = [
    "交易时间", "交易分类", "交易对方", "对方账号", "商品说明", "收/支",
    "金额", "收/付款方式", "交易状态", "交易订单号", "商家订单号", "备注",
]
WECHAT_COLUMNS = [
    "交易时间", "交易类型", "交易对方", "商品", "收/支", "金额(元)",
    "支付方式", "当前状态", "交易单号", "商户单号", "备注",
]


class SourceConfig:
    """单源配置：表结构、逻辑列、筛选/搜索/排序维度"""

    def __init__(
        self,
        name: str,
        label: str,
        table: str,
        columns: List[str],
        logical_columns: List[dict],
        date_col: str,
        time_col: str,  # 仅 BOC 有独立时间列，其余源为空串
        amount_col: str,
        direction_col: str,
        directions: List[str],
        neutral_direction: str,  # 不计收支 / 中性交易；BOC 为空串
        category_col: str,
        category_label: str,
        search_cols: List[str],
        search_placeholder: str,
        balance_col: str,  # 仅 BOC
    ):
        self.name = name
        self.label = label
        self.table = table
        self.columns = columns
        self.logical_columns = logical_columns
        self.date_col = date_col
        self.time_col = time_col
        self.amount_col = amount_col
        self.direction_col = direction_col
        self.directions = directions
        self.neutral_direction = neutral_direction
        self.category_col = category_col
        self.category_label = category_label
        self.search_cols = search_cols
        self.search_placeholder = search_placeholder
        self.balance_col = balance_col

    @property
    def has_neutral_card(self) -> bool:
        return bool(self.neutral_direction)


def _col(key, label, kind, visible=True, sort=None):
    return {"key": key, "label": label, "kind": kind, "visible": visible, "sort": sort}


SOURCE_CONFIGS: Dict[str, SourceConfig] = {
    SOURCE_BOC: SourceConfig(
        name=SOURCE_BOC,
        label="BOC",
        table="boc_transactions",
        columns=BOC_COLUMNS,
        logical_columns=[
            _col("datetime", "记账时间", "datetime", sort="datetime"),
            _col("tx_name", "交易名称", "text"),
            _col("tx_type", "类型", "direction"),
            _col("amount", "金额", "amount", sort="amount"),
            _col("balance", "余额", "balance"),
            _col("counterparty", "对方账户名", "text", sort="counterparty"),
            _col("channel", "渠道", "text"),
            _col("memo", "附言", "text", visible=False),
            _col("currency", "币别", "text", visible=False),
            _col("branch", "网点名称", "text", visible=False),
            _col("cp_account", "对方卡号/账号", "copy", visible=False),
            _col("cp_bank", "对方开户行", "text", visible=False),
        ],
        date_col="date",
        time_col="time",
        amount_col="amount",
        direction_col="tx_type",
        directions=["支出", "收入"],
        neutral_direction="",
        category_col="channel",
        category_label="渠道",
        search_cols=["counterparty", "tx_name", "memo"],
        search_placeholder="搜索对方账户名 / 交易名称 / 附言",
        balance_col="balance",
    ),
    SOURCE_ALIPAY: SourceConfig(
        name=SOURCE_ALIPAY,
        label="支付宝",
        table="alipay_transactions",
        columns=ALIPAY_COLUMNS,
        logical_columns=[
            _col("交易时间", "交易时间", "datetime", sort="datetime"),
            _col("收/支", "收/支", "direction"),
            _col("金额", "金额", "amount", sort="amount"),
            _col("交易对方", "交易对方", "text", sort="counterparty"),
            _col("商品说明", "商品说明", "text"),
            _col("交易分类", "交易分类", "text"),
            _col("收/付款方式", "收/付款方式", "text"),
            _col("交易状态", "交易状态", "status"),
            _col("对方账号", "对方账号", "copy", visible=False),
            _col("交易订单号", "交易订单号", "copy", visible=False),
            _col("商家订单号", "商家订单号", "copy", visible=False),
            _col("备注", "备注", "text", visible=False),
        ],
        date_col="交易时间",
        time_col="",
        amount_col="金额",
        direction_col="收/支",
        directions=["支出", "收入", "不计收支"],
        neutral_direction="不计收支",
        category_col="交易分类",
        category_label="交易分类",
        search_cols=["交易对方", "商品说明", "备注"],
        search_placeholder="搜索交易对方 / 商品说明 / 备注",
        balance_col="",
    ),
    SOURCE_WECHAT: SourceConfig(
        name=SOURCE_WECHAT,
        label="微信",
        table="wechat_transactions",
        columns=WECHAT_COLUMNS,
        logical_columns=[
            _col("交易时间", "交易时间", "datetime", sort="datetime"),
            _col("收/支", "收/支", "direction"),
            _col("金额(元)", "金额(元)", "amount", sort="amount"),
            _col("交易对方", "交易对方", "text", sort="counterparty"),
            _col("商品", "商品", "text"),
            _col("交易类型", "交易类型", "text"),
            _col("支付方式", "支付方式", "text"),
            _col("当前状态", "当前状态", "status"),
            _col("交易单号", "交易单号", "copy", visible=False),
            _col("商户单号", "商户单号", "copy", visible=False),
            _col("备注", "备注", "text", visible=False),
        ],
        date_col="交易时间",
        time_col="",
        amount_col="金额(元)",
        direction_col="收/支",
        directions=["支出", "收入", "中性交易"],
        neutral_direction="中性交易",
        category_col="交易类型",
        category_label="交易类型",
        search_cols=["交易对方", "商品", "备注"],
        search_placeholder="搜索交易对方 / 商品 / 备注",
        balance_col="",
    ),
}

# 排序维度：前端 sort key → 实际排序列（白名单，防注入）
SORT_COLUMNS: Dict[str, Dict[str, str]] = {
    SOURCE_BOC: {"datetime": "date, time", "amount": "amount", "counterparty": "counterparty"},
    SOURCE_ALIPAY: {"datetime": "交易时间", "amount": "金额", "counterparty": "交易对方"},
    SOURCE_WECHAT: {"datetime": "交易时间", "amount": "金额(元)", "counterparty": "交易对方"},
}

# 去重键（设计 4.3）：[主键列] 或 (主键列, 回退列)
DEDUP_KEYS: Dict[str, object] = {
    SOURCE_BOC: ["date", "time", "amount", "counterparty"],
    SOURCE_ALIPAY: (["交易订单号"], ["交易时间", "金额", "交易对方"]),
    SOURCE_WECHAT: (["交易单号"], ["交易时间", "金额(元)", "交易对方"]),
}


def dedup_key(source: str, values: Dict[str, str]) -> str:
    """按设计 4.3 计算去重键；主键或回退键全为空时返回空串（由调用方兜底）。"""
    spec = DEDUP_KEYS[source]
    primary, fallback = spec if isinstance(spec[0], list) else (spec, [])
    if primary:
        key = "|".join((values.get(c) or "").strip() for c in primary)
        if key:
            return key
    return "|".join((values.get(c) or "").strip() for c in fallback).strip("|")


# ---- 总账户虚拟源（TCY-15）：统一逻辑列与筛选维度 ----
TOTAL_SOURCE = "total"
TOTAL_DIRECTIONS = ["支出", "收入", "不计收支"]
TOTAL_NEUTRAL = "不计收支"

TOTAL_COLUMNS = [
    _col("time", "时间", "datetime", sort="datetime"),
    _col("direction", "收·支", "direction"),
    _col("amount", "金额", "amount", sort="amount"),
    _col("source", "来源", "source"),
    _col("counterparty", "对方", "text", sort="counterparty"),
    _col("summary", "摘要", "text"),
    _col("mark", "标记", "mark"),  # 仅内部流动区（内部流动 / 重复记录）
]
