// paycheck-react/src/components/MonthlyTable.tsx
import type { MonthlyItem } from "../types";
import { fmtYuan } from "../utils/format";
import "../styles/tables.css";

interface MonthlyTableProps {
  monthly: MonthlyItem[];
}

export default function MonthlyTable({ monthly }: MonthlyTableProps) {
  return (
    <div className="section">
      <h2>月度明细（总账户）</h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>月份</th>
              <th>笔数</th>
              <th>总金额</th>
              <th>微信</th>
              <th>支付宝</th>
              <th>银行</th>
            </tr>
          </thead>
          <tbody>
            {monthly.map((m) => (
              <tr key={m.month}>
                <td>{m.month}</td>
                <td>{m.count}</td>
                <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{fmtYuan(m.expense)}</td>
                <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{m.wechat > 0 ? fmtYuan(m.wechat) : "-"}</td>
                <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{m.alipay > 0 ? fmtYuan(m.alipay) : "-"}</td>
                <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{m.bank > 0 ? fmtYuan(m.bank) : "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
