// paycheck-react/src/utils/aggregation.ts
import type { Transaction, SummaryStats, MonthlyItem, CategoryItem } from "../types";

export interface AggregationResult {
  summary: SummaryStats;
  monthly: MonthlyItem[];
  categories: CategoryItem[];
  platform_monthly: { month: string; wechat: number; alipay: number; bank: number }[];
}

export function aggregate(transactions: Transaction[]): AggregationResult {
  const expenses = transactions.filter(
    (t) => t.tx_type === "支出" || t.tx_type === "pay" || t.tx_type === "Pay"
  );
  const incomes = transactions.filter(
    (t) => t.tx_type === "收入" || t.tx_type === "收款"
  );

  const totalExpense = expenses.reduce((s, t) => s + t.amount, 0);
  const totalIncome = incomes.reduce((s, t) => s + t.amount, 0);
  const totalCount = expenses.length;

  const monthMap: Record<string, { expense: number; count: number; wechat: number; alipay: number; bank: number }> = {};
  expenses.forEach((t) => {
    const m = t.time.substring(0, 7);
    if (!monthMap[m]) monthMap[m] = { expense: 0, count: 0, wechat: 0, alipay: 0, bank: 0 };
    monthMap[m].expense += t.amount;
    monthMap[m].count += 1;
    if (t.platform === "wechat") monthMap[m].wechat += t.amount;
    else if (t.platform === "alipay") monthMap[m].alipay += t.amount;
    else monthMap[m].bank += t.amount;
  });

  const months = Object.keys(monthMap).sort();
  const monthly: MonthlyItem[] = months.map((m) => {
    const d = monthMap[m];
    return {
      month: m,
      expense: Math.round(d.expense * 100) / 100,
      count: d.count,
      wechat: Math.round(d.wechat * 100) / 100,
      alipay: Math.round(d.alipay * 100) / 100,
      bank: Math.round(d.bank * 100) / 100,
    };
  });

  const monthsCount = months.length;
  const monthlyAvg = monthsCount > 0 ? Math.round((totalExpense / monthsCount) * 100) / 100 : 0;

  const we = expenses.filter((t) => t.platform === "wechat");
  const ae = expenses.filter((t) => t.platform === "alipay");
  const be = expenses.filter((t) => t.platform === "bank");

  const catMap: Record<string, { name: string; amount: number; count: number }> = {};
  expenses.forEach((t) => {
    const c = t.category || "未分类";
    if (!catMap[c]) catMap[c] = { name: c, amount: 0, count: 0 };
    catMap[c].amount += t.amount;
    catMap[c].count += 1;
  });
  const categories: CategoryItem[] = Object.values(catMap)
    .sort((a, b) => b.amount - a.amount)
    .map((c) => ({
      name: c.name,
      amount: Math.round(c.amount * 100) / 100,
      count: c.count,
      pct: totalExpense > 0 ? Math.round((c.amount / totalExpense) * 1000) / 10 : 0,
    }));

  const platformMonthly = monthly.map((m) => ({
    month: m.month,
    wechat: m.wechat,
    alipay: m.alipay,
    bank: m.bank,
  }));

  return {
    summary: {
      total_expense: Math.round(totalExpense * 100) / 100,
      total_income: Math.round(totalIncome * 100) / 100,
      total_count: totalCount,
      monthly_avg: monthlyAvg,
      wechat_total: Math.round(we.reduce((s, t) => s + t.amount, 0) * 100) / 100,
      alipay_total: Math.round(ae.reduce((s, t) => s + t.amount, 0) * 100) / 100,
      bank_total: Math.round(be.reduce((s, t) => s + t.amount, 0) * 100) / 100,
      wechat_count: we.length,
      alipay_count: ae.length,
      bank_count: be.length,
    },
    monthly,
    categories,
    platform_monthly: platformMonthly,
  };
}
