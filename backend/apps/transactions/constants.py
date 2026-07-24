"""交易字段常量 — 统一各解析器和序列化器的列名引用。

所有解析器（alipay/wechat/boc）及前端 API 均使用此常量作为标准字段名。
"""

# ── 交易通用字段 ──
FIELD_TIME = "time"
FIELD_CATEGORY = "category"
FIELD_COUNTERPARTY = "counterparty"
FIELD_DESCRIPTION = "description"
FIELD_AMOUNT = "amount"
FIELD_TX_TYPE = "tx_type"
FIELD_PAYMENT_METHOD = "payment_method"

# ── 银行专属字段 ──
FIELD_BALANCE = "balance"
FIELD_CURRENCY = "currency"
FIELD_BRANCH = "branch"
FIELD_CP_ACCOUNT = "cp_account"
FIELD_CP_BANK = "cp_bank"

# ── 平台标识 ──
PLATFORM_ALIPAY = "alipay"
PLATFORM_WECHAT = "wechat"
PLATFORM_BOC = "boc"

# ── 交易类型 ──
TX_TYPE_EXPENSE = "支出"
TX_TYPE_INCOME = "收入"

# ── API 通用参数 ──
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
