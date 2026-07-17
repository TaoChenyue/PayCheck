"""字段名常量 — 替代魔法字符串，统一管理 Transaction 数据模型中的字段/列名。

使用方式:
    from paycheck.core.constants import (
        FIELD_TIME, FIELD_AMOUNT, FIELD_CATEGORY, FIELD_PLATFORM,
        FIELD_TX_TYPE, FIELD_PAYMENT_METHOD, FIELD_DESCRIPTION,
        FIELD_COUNTERPARTY, FIELD_BALANCE, FIELD_CURRENCY,
        FIELD_BRANCH, FIELD_CP_ACCOUNT, FIELD_CP_BANK,
        FIELD_ID, FIELD_MONTH, FIELD_COUNT,
    )

注意:
    仅用于替换代码中的字段名/列名字符串，不用于替换用户可见的 UI 文本。
"""

# ── Transaction 模型字段名 ──
# 与 core/models.py 中的 Transaction dataclass 字段一一对应
FIELD_PLATFORM = "platform"
FIELD_TIME = "time"
FIELD_CATEGORY = "category"
FIELD_COUNTERPARTY = "counterparty"
FIELD_DESCRIPTION = "description"
FIELD_AMOUNT = "amount"
FIELD_TX_TYPE = "tx_type"
FIELD_PAYMENT_METHOD = "payment_method"
FIELD_BALANCE = "balance"
FIELD_CURRENCY = "currency"
FIELD_BRANCH = "branch"
FIELD_CP_ACCOUNT = "cp_account"
FIELD_CP_BANK = "cp_bank"

# ── 数据库/序列化专用字段 ──
FIELD_ID = "id"

# ── 解析器内部列映射键名 ──
# HEADER_KEYWORDS 中用于将 CSV 列映射到内部名称的键
# 注意: PARSER_COL_PAYMENT 映射到 FIELD_PAYMENT_METHOD
PARSER_COL_TIME = "time"
PARSER_COL_CATEGORY = "category"
PARSER_COL_COUNTERPARTY = "counterparty"
PARSER_COL_DESCRIPTION = "description"
PARSER_COL_TX_TYPE = "tx_type"
PARSER_COL_AMOUNT = "amount"
PARSER_COL_PAYMENT = "payment"

# ── 银行 CSV 特定列名 ──
# BOC OCR 管线生成 CSV 时使用的列名，部分映射到 Transaction 字段
BANK_COL_DATE = "date"
BANK_COL_CHANNEL = "channel"
BANK_COL_MEMO = "memo"
BANK_COL_TX_NAME = "tx_name"

# ── 统计/聚合内部字段 ──
STAT_FIELD_MONTH = "month"
STAT_FIELD_TX_TYPE_NORM = "tx_type_norm"
STAT_FIELD_COUNT = "count"
STAT_FIELD_EXPENSE = "expense"
STAT_FIELD_INCOME = "income"
