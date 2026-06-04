// paycheck-react/src/types.ts

export interface Transaction {
  platform: "wechat" | "alipay" | "bank";
  time: string;
  category: string;
  counterparty: string;
  description: string;
  amount: number;
  tx_type: string;
  payment_method: string;
  balance: number;
  currency: string;
  branch: string;
  cp_account: string;
  cp_bank: string;
}

export interface SummaryStats {
  total_expense: number;
  total_income: number;
  total_count: number;
  monthly_avg: number;
  wechat_total: number;
  alipay_total: number;
  bank_total: number;
  wechat_count: number;
  alipay_count: number;
  bank_count: number;
}

export interface MonthlyItem {
  month: string;
  expense: number;
  count: number;
  wechat: number;
  alipay: number;
  bank: number;
}

export interface CategoryItem {
  name: string;
  amount: number;
  count: number;
  pct: number;
}

export interface PlatformMonthlyItem {
  month: string;
  wechat: number;
  alipay: number;
  bank: number;
}

export interface AggregatedData {
  period: { start: string; end: string };
  summary: SummaryStats;
  monthly: MonthlyItem[];
  categories: CategoryItem[];
  platform_monthly: PlatformMonthlyItem[];
  income_details: Transaction[];
  all_transactions: Transaction[];
  generated_at: string;
}

export interface FingerprintStore {
  version: number;
  fingerprints: string[];
}
