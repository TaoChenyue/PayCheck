// paycheck-react/src/components/SummaryCards.tsx
import type { SummaryStats } from "../types";
import { fmtYuan } from "../utils/format";
import "../styles/cards.css";

interface SummaryCardsProps {
  summary: SummaryStats;
  incomeExpanded: boolean;
  expenseExpanded: boolean;
  onToggleIncome: () => void;
  onToggleExpense: () => void;
}

export default function SummaryCards({
  summary, incomeExpanded, expenseExpanded, onToggleIncome, onToggleExpense,
}: SummaryCardsProps) {
  return (
    <div className="cards">
      <div className="card clickable" onClick={onToggleExpense}>
        <div className="card-label">总支出</div>
        <div className="card-value">{fmtYuan(summary.total_expense)}</div>
        <div className="card-sub">
          {summary.total_count} 笔 · 已剔除内部转账{expenseExpanded ? " · 点击收起" : " · 点击展开"}
        </div>
      </div>
      <div className="card">
        <div className="card-label">月均支出</div>
        <div className="card-value">{fmtYuan(summary.monthly_avg)}</div>
        <div className="card-sub">共 {summary.total_count > 0 ? "-" : "0"} 个月</div>
      </div>
      <div className="card clickable" onClick={onToggleIncome}>
        <div className="card-label">总收入（参考）</div>
        <div className="card-value">{fmtYuan(summary.total_income)}</div>
        <div className="card-sub">
          外部收入 · 不含转账{incomeExpanded ? " · 点击收起" : " · 点击展开"}
        </div>
      </div>
    </div>
  );
}
