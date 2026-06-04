// paycheck-react/src/components/PlatformComparison.tsx
import ReactECharts from "echarts-for-react";
import { fmtYuan } from "../utils/format";
import "../styles/charts.css";

interface PlatformComparisonProps {
  platformMonthly: { month: string; wechat: number; alipay: number; bank: number }[];
}

export default function PlatformComparison({ platformMonthly }: PlatformComparisonProps) {
  if (platformMonthly.length === 0) return null;

  const option = {
    tooltip: {
      trigger: "axis" as const,
      axisPointer: { type: "shadow" as const },
      formatter: (params: unknown) => {
        const arr = params as Array<{ axisValue: string; marker: string; seriesName: string; value: number }>;
        let h = `<strong>${arr[0].axisValue}</strong><br/>`;
        arr.forEach((x) => { h += `${x.marker} ${x.seriesName}: ${fmtYuan(x.value)}<br/>`; });
        return h;
      },
    },
    legend: { data: ["微信", "支付宝", "银行"], top: 0 },
    grid: { left: 80, right: 30, top: 40, bottom: 30 },
    xAxis: {
      type: "category" as const,
      data: platformMonthly.map((d) => d.month),
      axisLabel: { rotate: 45, fontSize: 11 },
    },
    yAxis: { type: "value" as const, axisLabel: { formatter: "¥{value}" } },
    series: [
      { name: "微信", type: "bar", data: platformMonthly.map((d) => d.wechat), itemStyle: { color: "#07c160", borderRadius: [4, 4, 0, 0] } },
      { name: "支付宝", type: "bar", data: platformMonthly.map((d) => d.alipay), itemStyle: { color: "#1677ff", borderRadius: [4, 4, 0, 0] } },
      { name: "银行", type: "bar", data: platformMonthly.map((d) => d.bank), itemStyle: { color: "#722ed1", borderRadius: [4, 4, 0, 0] } },
    ],
  };

  return (
    <div className="section">
      <h2>平台对比（真实消费）</h2>
      <ReactECharts option={option} style={{ height: 380 }} />
    </div>
  );
}
