// paycheck-react/src/App.tsx
import { useState } from "react";
import type { AggregatedData } from "./types";
import { useFingerprints } from "./hooks/useFingerprints";
import { useAggregation } from "./hooks/useAggregation";
import EmptyState from "./components/EmptyState";
import ReportHeader from "./components/ReportHeader";
import SummaryCards from "./components/SummaryCards";
import PlatformCards from "./components/PlatformCards";
import InternalSection from "./components/InternalSection";
import DetailTable from "./components/DetailTable";
import MonthlyChart from "./components/MonthlyChart";
import CategorySection from "./components/CategorySection";
import PlatformComparison from "./components/PlatformComparison";
import MonthlyTable from "./components/MonthlyTable";
import Footer from "./components/Footer";

export default function App() {
  const [data, setData] = useState<AggregatedData | null>(null);
  const [incomeExpanded, setIncomeExpanded] = useState(false);
  const [expenseExpanded, setExpenseExpanded] = useState(false);

  const { fingerprints, addFingerprints, removeFingerprint } = useFingerprints();
  const { internalTxs, stats } = useAggregation(data, fingerprints);

  if (!data) {
    return <EmptyState onDataLoaded={setData} />;
  }

  if (!stats) return null;

  return (
    <div className="container">
      <ReportHeader
        start={data.period.start}
        end={data.period.end}
        generatedAt={data.generated_at}
      />

      <SummaryCards
        summary={stats.summary}
        incomeExpanded={incomeExpanded}
        expenseExpanded={expenseExpanded}
        onToggleIncome={() => setIncomeExpanded((p) => !p)}
        onToggleExpense={() => setExpenseExpanded((p) => !p)}
      />

      <InternalSection
        internalTxs={internalTxs}
        fingerprints={fingerprints}
        onRemoveFingerprint={removeFingerprint}
        onImportFingerprints={addFingerprints}
      />

      {incomeExpanded && (
        <DetailTable
          items={data.income_details || []}
          txType="income"
          onMarkInternal={addFingerprints}
        />
      )}

      {expenseExpanded && (
        <DetailTable
          items={data.all_transactions}
          txType="expense"
          onMarkInternal={addFingerprints}
        />
      )}

      <PlatformCards summary={stats.summary} />

      <MonthlyChart monthly={stats.monthly} />

      <CategorySection categories={stats.categories} />

      <PlatformComparison platformMonthly={stats.platform_monthly} />

      <MonthlyTable monthly={stats.monthly} />

      <Footer generatedAt={data.generated_at} />
    </div>
  );
}
