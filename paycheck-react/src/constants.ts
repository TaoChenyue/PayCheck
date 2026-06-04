// paycheck-react/src/constants.ts

export const COLORS = [
  "#5470c6", "#91cc75", "#fac858", "#ee6666", "#73c0de",
  "#3ba272", "#fc8452", "#9a60b4", "#ea7ccc", "#2f4554",
  "#61a0a8", "#d48265", "#749f83", "#ca8622", "#bda29a",
];

export const FINGERPRINT_KEY = "paycheck_v1";

export interface ColumnDef {
  field: string;
  label: string;
}

export type PlatformColumnMap = Record<string, ColumnDef[]>;

export const PLATFORM_COLUMNS: PlatformColumnMap = {
  wechat: [
    { field: "time", label: "交易时间" },
    { field: "amount", label: "金额" },
    { field: "category", label: "交易类型" },
    { field: "counterparty", label: "交易对方" },
    { field: "description", label: "商品" },
    { field: "payment_method", label: "支付方式" },
  ],
  alipay: [
    { field: "time", label: "交易时间" },
    { field: "amount", label: "金额" },
    { field: "category", label: "交易分类" },
    { field: "counterparty", label: "交易对方" },
    { field: "description", label: "商品说明" },
    { field: "payment_method", label: "收/付款方式" },
  ],
  bank: [
    { field: "time", label: "记账日期/时间" },
    { field: "amount", label: "金额" },
    { field: "balance", label: "余额" },
    { field: "category", label: "交易名称" },
    { field: "currency", label: "币别" },
    { field: "counterparty", label: "对方账户名" },
    { field: "cp_account", label: "对方卡号/账号" },
    { field: "cp_bank", label: "对方开户行" },
    { field: "branch", label: "网点名称" },
    { field: "payment_method", label: "渠道" },
    { field: "description", label: "附言" },
  ],
};

export interface FilterLabels {
  category: string;
  counterparty: string;
  description: string;
  payment_method: string;
  balance?: string;
  currency?: string;
  cp_bank?: string;
  branch?: string;
  cp_account?: string;
}

export type PlatformFilterLabelMap = Record<string, FilterLabels>;

export const PLATFORM_FILTER_LABELS: PlatformFilterLabelMap = {
  wechat: {
    category: "交易类型",
    counterparty: "交易对方",
    description: "商品",
    payment_method: "支付方式",
  },
  alipay: {
    category: "交易分类",
    counterparty: "交易对方",
    description: "商品说明",
    payment_method: "收/付款方式",
  },
  bank: {
    category: "交易名称",
    counterparty: "对方账户名",
    description: "附言",
    payment_method: "渠道",
    balance: "余额",
    currency: "币别",
    branch: "网点名称",
    cp_bank: "对方开户行",
    cp_account: "对方卡号",
  },
};

export interface PlatformMeta {
  name: string;
  color: string;
}

export type PlatformMetaMap = Record<string, PlatformMeta>;

export const PLATFORM_META: PlatformMetaMap = {
  wechat: { name: "微信支付", color: "#07c160" },
  alipay: { name: "支付宝", color: "#1677ff" },
  bank: { name: "银行账户", color: "#722ed1" },
};

export const PLATFORM_ORDER = ["wechat", "alipay", "bank"] as const;
