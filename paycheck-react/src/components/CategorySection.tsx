// paycheck-react/src/components/CategorySection.tsx
import ReactECharts from "echarts-for-react";
import type { CategoryItem } from "../types";
import { COLORS } from "../constants";
import { fmtYuan } from "../utils/format";
import "../styles/charts.css";

interface CategorySectionProps {
  categories: CategoryItem[];
}

export default function CategorySection({ categories }: CategorySectionProps) {
  if (categories.length === 0) {
    return (
      <div className="section">
        <h2>消费类别分布</h2>
        <p style={{ color: "#999", padding: 10 }}>暂无分类数据</p>
      </div>
    );
  }

  const colorMap: Record<string, string> = {};
  categories.forEach((c, i) => { colorMap[c.name] = COLORS[i % COLORS.length]; });

  const pieOption = {
    tooltip: {
      formatter: (p: { name: string; value: number; percent: number }) =>
        `<strong>${p.name}</strong><br/>金额: ${fmtYuan(p.value)}<br/>占比: ${p.percent}%`,
    },
    series: [
      {
        type: "pie" as const,
        radius: ["35%", "65%"],
        center: ["50%", "50%"],
        data: categories.map((c) => ({ name: c.name, value: c.amount })),
        itemStyle: { borderRadius: 4, borderColor: "#fff", borderWidth: 2 },
        label: { show: false },
        emphasis: {
          label: { show: true, fontSize: 14, fontWeight: "bold" as const },
          itemStyle: { shadowBlur: 10, shadowColor: "rgba(0,0,0,0.2)" },
        },
      },
    ],
  };

  const barOption = {
    tooltip: {
      trigger: "axis" as const,
      axisPointer: { type: "shadow" as const },
      formatter: (params: unknown) => {
        const arr = params as Array<{ name: string; marker: string; value: number }>;
        const p = arr[0];
        const cat = categories.find((c) => c.name === p.name);
        return `<strong>${p.name}</strong><br/>${p.marker} ${fmtYuan(p.value)} (${cat?.pct ?? 0}%)`;
      },
    },
    grid: { left: 10, right: 80, top: 10, bottom: 10 },
    xAxis: { type: "value" as const, axisLabel: { formatter: "¥{value}" } },
    yAxis: {
      type: "category" as const,
      data: categories.map((c) => c.name).reverse(),
      axisLabel: { fontSize: 11 },
    },
    series: [
      {
        type: "bar",
        data: categories
          .map((c) => ({ value: c.amount, itemStyle: { color: colorMap[c.name], borderRadius: [0, 4, 4, 0] } }))
          .reverse(),
      },
    ],
  };

  return (
    <div className="section">
      <h2>消费类别分布</h2>
      <div className="chart-row">
        <div className="chart chart-inline" style={{ width: "55%", height: 380 }}>
          <ReactECharts option={pieOption} style={{ height: "100%" }} />
        </div>
        <div className="chart chart-inline" style={{ width: "45%", height: 380 }}>
          <ReactECharts option={barOption} style={{ height: "100%" }} />
        </div>
      </div>
      <div className="category-list">
        {categories.map((c) => (
          <div key={c.name} className="category-item">
            <span className="cat-dot" style={{ background: colorMap[c.name] }} />
            <span className="cat-name">{c.name}</span>
            <span className="cat-amount">{fmtYuan(c.amount)}</span>
            <span className="cat-pct">{c.pct}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}
