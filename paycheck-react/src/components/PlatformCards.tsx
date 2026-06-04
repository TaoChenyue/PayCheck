// paycheck-react/src/components/PlatformCards.tsx
import type { SummaryStats } from "../types";
import { fmtYuan } from "../utils/format";
import "../styles/cards.css";

interface PlatformCardsProps {
  summary: SummaryStats;
}

export default function PlatformCards({ summary }: PlatformCardsProps) {
  return (
    <div className="platform-cards">
      <div className="platform-card wechat">
        <div className="platform-name">微信支付（真实消费）</div>
        <div className="platform-value">{fmtYuan(summary.wechat_total)}</div>
        <div className="platform-count">{summary.wechat_count} 笔</div>
      </div>
      <div className="platform-card alipay">
        <div className="platform-name">支付宝（真实消费）</div>
        <div className="platform-value">{fmtYuan(summary.alipay_total)}</div>
        <div className="platform-count">{summary.alipay_count} 笔</div>
      </div>
      <div className="platform-card bank">
        <div className="platform-name">银行账户（银行卡）</div>
        <div className="platform-value">{fmtYuan(summary.bank_total)}</div>
        <div className="platform-count">{summary.bank_count} 笔</div>
      </div>
    </div>
  );
}
