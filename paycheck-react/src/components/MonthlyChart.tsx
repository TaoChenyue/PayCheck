// paycheck-react/src/components/MonthlyChart.tsx
import { useState } from "react";
import ReactECharts from "echarts-for-react";
import type { MonthlyItem } from "../types";
import { fmtYuan } from "../utils/format";
import "../styles/charts.css";

interface MonthlyChartProps {
  monthly: MonthlyItem[];
}

type Mode = "all" | "wechat" | "alipay" | "bank";

const MODES: { value: Mode; label: string; color: string }[] = [
  { value: "all", label: "全部", color: "#5470c6" },
  { value: "wechat", label: "微信", color: "#07c160" },
  { value: "alipay", label: "支付宝", color: "#1677ff" },
  { value: "bank", label: "银行", color: "#722ed1" },
];

export default function MonthlyChart({ monthly }: MonthlyChartProps) {
  const [mode, setMode] = useState<Mode>("all");

  const vals = monthly.map((m) =>
    mode === "all" ? m.expense : m[mode]
  );
  const months = monthly.map((m) => m.month);
  const activeColor = MODES.find((x) => x.value === mode)!.color;

  const option = {
    tooltip: {
      trigger: "axis" as const,
      formatter: (params: unknown) => {
        const p = (params as Array<{ axisValue: string; marker: string; value: number }>)[0];
        return `<strong>${p.axisValue}</strong><br/>${p.marker} 支出: ${fmtYuan(p.value)}`;
      },
    },
    grid: { left: 80, right: 30, top: 20, bottom: 30 },
    xAxis: {
      type: "category" as const,
      data: months,
      axisLabel: { rotate: 45, fontSize: 11 },
    },
    yAxis: {
      type: "value" as const,
      axisLabel: { formatter: "¥{value}" },
    },
    series: [
      {
        type: "bar",
        data: vals,
        itemStyle: { color: activeColor, borderRadius: [4, 4, 0, 0] },
      },
    ],
  };

  return (
    <div className="section">
      <h2>月度开销</h2>
      <div className="filter" style={{ marginBottom: 12 }}>
        {MODES.map((m) => (
          <button
            key={m.value}
            className={mode === m.value ? "active" : ""}
            onClick={() => setMode(m.value)}
          >
            {m.label}
          </button>
        ))}
      </div>
      <ReactECharts option={option} style={{ height: 400 }} />
    </div>
  );
}
