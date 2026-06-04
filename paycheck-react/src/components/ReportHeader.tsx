// paycheck-react/src/components/ReportHeader.tsx

interface ReportHeaderProps {
  start: string;
  end: string;
  generatedAt: string;
}

export default function ReportHeader({ start, end, generatedAt }: ReportHeaderProps) {
  return (
    <header style={{ textAlign: "center", padding: "40px 0 20px" }}>
      <h1 style={{ fontSize: 28, color: "#1a1a2e" }}>PayCheck 账单分析报告</h1>
      <p style={{ fontSize: 16, color: "#666", marginTop: 4 }}>{start} ~ {end} · 总账户（微信 + 支付宝 + 银行）</p>
      <p style={{ fontSize: 13, color: "#999", marginTop: 2 }}>生成于 {generatedAt}</p>
    </header>
  );
}
