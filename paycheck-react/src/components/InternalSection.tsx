// paycheck-react/src/components/InternalSection.tsx
import { useState, useCallback, useRef } from "react";
import type { Transaction } from "../types";
import { PLATFORM_ORDER, PLATFORM_META, PLATFORM_COLUMNS } from "../constants";
import { fmtYuan } from "../utils/format";
import { hashTx } from "../utils/hash";
import Pagination from "./common/Pagination";
import "../styles/tables.css";
import "../styles/internal.css";

interface InternalSectionProps {
  internalTxs: Transaction[];
  fingerprints: Set<string>;
  onRemoveFingerprint: (fp: string) => void;
  onImportFingerprints: (fps: string[]) => void;
}

export default function InternalSection({
  internalTxs, fingerprints, onRemoveFingerprint, onImportFingerprints,
}: InternalSectionProps) {
  const defaultPlatform = PLATFORM_ORDER.find((p) => internalTxs.some((t) => t.platform === p)) || "wechat";
  const [platform, setPlatform] = useState(defaultPlatform);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const fileRef = useRef<HTMLInputElement>(null);

  const filtered = internalTxs.filter((t) => t.platform === platform);
  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const pageItems = filtered.slice((page - 1) * pageSize, page * pageSize);
  const columns = PLATFORM_COLUMNS[platform] || PLATFORM_COLUMNS.bank;
  const totalInternalAmount = internalTxs.reduce((s, t) => s + t.amount, 0);

  const activePlatforms = PLATFORM_ORDER.filter((p) => internalTxs.some((t) => t.platform === p));

  if (internalTxs.length === 0) return null;

  const handleExport = useCallback(() => {
    const data = {
      version: 1,
      fingerprints: Array.from(fingerprints),
      exported_at: new Date().toISOString(),
      count: fingerprints.size,
    };
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "paycheck-internal-fingerprints.json";
    a.click();
    URL.revokeObjectURL(url);
  }, [fingerprints]);

  const handleImport = useCallback(() => {
    fileRef.current?.click();
  }, []);

  const handleFile = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => {
        try {
          const data = JSON.parse(reader.result as string);
          if (data.fingerprints && Array.isArray(data.fingerprints)) {
            onImportFingerprints(data.fingerprints);
          }
        } catch {
          // ignore
        }
      };
      reader.readAsText(file);
      e.target.value = "";
    },
    [onImportFingerprints]
  );

  return (
    <div className="section">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <h2 style={{ margin: 0 }}>内部转账（已剔除）</h2>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={handleExport}
            style={{ padding: "4px 12px", border: "1px solid #d9d9d9", background: "#fff", borderRadius: 4, cursor: "pointer", fontSize: 13 }}>
            导出指纹
          </button>
          <button onClick={handleImport}
            style={{ padding: "4px 12px", border: "1px solid #d9d9d9", background: "#fff", borderRadius: 4, cursor: "pointer", fontSize: 13 }}>
            导入指纹
          </button>
          <input ref={fileRef} type="file" accept=".json" style={{ display: "none" }} onChange={handleFile} />
        </div>
      </div>

      <div className="income-tabs">
        {activePlatforms.map((p) => {
          const meta = PLATFORM_META[p];
          const count = internalTxs.filter((t) => t.platform === p).length;
          return (
            <button
              key={p}
              className={`income-tab${platform === p ? " active" : ""}`}
              onClick={() => { setPlatform(p); setPage(1); }}
            >
              {meta.name}
              <span className="tab-count">{count} 笔</span>
            </button>
          );
        })}
      </div>

      <div className="internal-note show">
        <strong>内部转账已剔除</strong> — 共剔除 <strong>{internalTxs.length}</strong> 笔，
        金额合计 <strong>{fmtYuan(totalInternalAmount)}</strong>
      </div>

      <div className="table-wrap internal-table-wrap">
        <table>
          <thead>
            <tr>
              <th style={{ width: 60 }}>操作</th>
              {columns.map((col) => (
                <th key={col.field}>{col.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageItems.map((tx, i) => (
              <tr key={i}>
                <td>
                  <button
                    onClick={() => onRemoveFingerprint(hashTx(tx))}
                    style={{ padding: "2px 8px", border: "1px solid #ff4d4f", color: "#ff4d4f", background: "#fff", borderRadius: 4, cursor: "pointer", fontSize: 12 }}
                  >
                    取消
                  </button>
                </td>
                {columns.map((col) => {
                  const val = (tx as unknown as Record<string, unknown>)[col.field];
                  if (col.field === "amount") {
                    return (
                      <td key={col.field} style={{ color: "#cf1322", fontWeight: 600, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                        {fmtYuan(val as number)}
                      </td>
                    );
                  }
                  if (col.field === "balance" && val) {
                    return (
                      <td key={col.field} style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                        {fmtYuan(val as number)}
                      </td>
                    );
                  }
                  if (col.field === "balance") {
                    return <td key={col.field} style={{ textAlign: "right" }}>-</td>;
                  }
                  return <td key={col.field}>{String(val || "-")}</td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Pagination page={page} totalPages={totalPages} pageSize={pageSize}
        onPageChange={setPage} onPageSizeChange={(s) => { setPageSize(s); setPage(1); }} />
    </div>
  );
}
