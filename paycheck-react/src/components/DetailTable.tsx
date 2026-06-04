// paycheck-react/src/components/DetailTable.tsx
import { useState, useMemo, useCallback } from "react";
import type { Transaction } from "../types";
import { PLATFORM_COLUMNS, PLATFORM_FILTER_LABELS, PLATFORM_ORDER, PLATFORM_META } from "../constants";
import { fmtYuan } from "../utils/format";
import { useFilteredList } from "../hooks/useFilteredList";
import { hashTx } from "../utils/hash";
import TagSelect from "./common/TagSelect";
import Pagination from "./common/Pagination";
import "../styles/tables.css";
import "../styles/filters.css";

interface DetailTableProps {
  items: Transaction[];
  txType: "income" | "expense";
  onMarkInternal: (fps: string[]) => void;
}

function txField(tx: Transaction, field: string): unknown {
  return (tx as unknown as Record<string, unknown>)[field];
}

export default function DetailTable({ items, txType, onMarkInternal }: DetailTableProps) {
  const preFiltered = useMemo(() => {
    return items.filter((t) => {
      if (txType === "income") return t.tx_type === "收入" || t.tx_type === "收款";
      return t.tx_type === "支出" || t.tx_type === "pay" || t.tx_type === "Pay";
    });
  }, [items, txType]);

  const {
    filters, setFilters, setPlatform, resetFilters,
    page, setPage, pageSize, setPageSize, totalPages, pageItems, totalFiltered, totalAmount,
  } = useFilteredList(preFiltered);

  const [selected, setSelected] = useState<Set<number>>(new Set());
  const platform = filters.platform;
  const columns = PLATFORM_COLUMNS[platform] || PLATFORM_COLUMNS.bank;
  const labels = PLATFORM_FILTER_LABELS[platform] || PLATFORM_FILTER_LABELS.bank;
  const isBank = platform === "bank";

  const activePlatforms = PLATFORM_ORDER.filter(
    (p) => preFiltered.some((t) => t.platform === p)
  );

  const getUniqueValues = useCallback(
    (field: string): string[] => {
      const set = new Set<string>();
      preFiltered.forEach((t) => {
        if (t.platform === platform) {
          const val = (t as unknown as Record<string, unknown>)[field];
          if (val) set.add(String(val));
        }
      });
      return Array.from(set).sort();
    },
    [preFiltered, platform]
  );

  const toggleSelect = (idx: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx); else next.add(idx);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selected.size === pageItems.length && pageItems.length > 0) {
      setSelected(new Set());
    } else {
      setSelected(new Set(pageItems.map((_, i) => i)));
    }
  };

  const markSelected = () => {
    const fps: string[] = [];
    selected.forEach((i) => {
      const tx = pageItems[i];
      if (tx) fps.push(hashTx(tx));
    });
    if (fps.length > 0) {
      onMarkInternal(fps);
      setSelected(new Set());
    }
  };

  const tableTitle = txType === "income" ? "收入详情" : "支出详情";
  const emoji = txType === "income" ? "💰" : "💸";

  // Reset selection when page/filters change
  const handlePlatformChange = (p: string) => {
    setPlatform(p);
    setSelected(new Set());
  };

  return (
    <div className="section">
      <h2>{emoji} {tableTitle}</h2>

      <div className="income-tabs">
        {activePlatforms.map((p) => {
          const meta = PLATFORM_META[p];
          const count = preFiltered.filter((t) => t.platform === p).length;
          return (
            <button
              key={p}
              className={`income-tab${platform === p ? " active" : ""}`}
              onClick={() => handlePlatformChange(p)}
            >
              {meta.name}
              <span className="tab-count">{count} 笔</span>
            </button>
          );
        })}
      </div>

      <div className="income-filters">
        <div className="f-row">
          <div className="f-group">
            <label>时间：</label>
            <input type="date" value={filters.dateStart}
              onChange={(e) => { setFilters((p) => ({ ...p, dateStart: e.target.value })); setPage(1); setSelected(new Set()); }} />
            <span>—</span>
            <input type="date" value={filters.dateEnd}
              onChange={(e) => { setFilters((p) => ({ ...p, dateEnd: e.target.value })); setPage(1); setSelected(new Set()); }} />
          </div>
          <div className="f-group">
            <label>金额：</label>
            <input type="number" placeholder="最小值" step="0.01" style={{ maxWidth: 110 }}
              onChange={(e) => { setFilters((p) => ({ ...p, amountMin: e.target.value ? parseFloat(e.target.value) : null })); setPage(1); setSelected(new Set()); }} />
            <span>—</span>
            <input type="number" placeholder="最大值" step="0.01" style={{ maxWidth: 110 }}
              onChange={(e) => { setFilters((p) => ({ ...p, amountMax: e.target.value ? parseFloat(e.target.value) : null })); setPage(1); setSelected(new Set()); }} />
          </div>
          <button className="reset-btn" onClick={() => { resetFilters(); setSelected(new Set()); }}>重置</button>
        </div>
        <div className="f-row">
          <div className="f-group">
            <label>{labels.category}：</label>
            <TagSelect placeholder="输入筛选..." values={filters.categories} suggestions={getUniqueValues("category")}
              onChange={(vals) => { setFilters((p) => ({ ...p, categories: vals })); setPage(1); setSelected(new Set()); }} />
          </div>
          <div className="f-group">
            <label>{labels.counterparty}：</label>
            <TagSelect placeholder="输入筛选..." values={filters.counterparties} suggestions={getUniqueValues("counterparty")}
              onChange={(vals) => { setFilters((p) => ({ ...p, counterparties: vals })); setPage(1); setSelected(new Set()); }} />
          </div>
          <div className="f-group">
            <label>{labels.description}：</label>
            <TagSelect placeholder="输入筛选..." values={filters.descriptions} suggestions={getUniqueValues("description")}
              onChange={(vals) => { setFilters((p) => ({ ...p, descriptions: vals })); setPage(1); setSelected(new Set()); }} />
          </div>
          <div className="f-group">
            <label>{labels.payment_method}：</label>
            <TagSelect placeholder="输入筛选..." values={filters.paymentMethods} suggestions={getUniqueValues("payment_method")}
              onChange={(vals) => { setFilters((p) => ({ ...p, paymentMethods: vals })); setPage(1); setSelected(new Set()); }} />
          </div>
        </div>
        {isBank && (
          <>
            <div className="f-row">
              <div className="f-group">
                <label>余额：</label>
                <input type="number" placeholder="最小值" step="0.01" style={{ maxWidth: 110 }}
                  onChange={(e) => { setFilters((p) => ({ ...p, balanceMin: e.target.value ? parseFloat(e.target.value) : null })); setPage(1); }} />
                <span>—</span>
                <input type="number" placeholder="最大值" step="0.01" style={{ maxWidth: 110 }}
                  onChange={(e) => { setFilters((p) => ({ ...p, balanceMax: e.target.value ? parseFloat(e.target.value) : null })); setPage(1); }} />
              </div>
              <div className="f-group">
                <label>{labels.currency}：</label>
                <TagSelect placeholder="输入筛选..." values={filters.currencies} suggestions={getUniqueValues("currency")}
                  onChange={(vals) => { setFilters((p) => ({ ...p, currencies: vals })); setPage(1); }} />
              </div>
              <div className="f-group">
                <label>{labels.cp_bank}：</label>
                <TagSelect placeholder="输入筛选..." values={filters.cpBanks} suggestions={getUniqueValues("cp_bank")}
                  onChange={(vals) => { setFilters((p) => ({ ...p, cpBanks: vals })); setPage(1); }} />
              </div>
              <div className="f-group">
                <label>{labels.branch}：</label>
                <TagSelect placeholder="输入筛选..." values={filters.branches} suggestions={getUniqueValues("branch")}
                  onChange={(vals) => { setFilters((p) => ({ ...p, branches: vals })); setPage(1); }} />
              </div>
            </div>
            <div className="f-row">
              <div className="f-group">
                <label>{labels.cp_account}：</label>
                <input type="text" placeholder="筛选卡号..." style={{ maxWidth: 200 }}
                  onChange={(e) => { setFilters((p) => ({ ...p, cpAccount: e.target.value })); setPage(1); }} />
              </div>
            </div>
          </>
        )}
      </div>

      {selected.size > 0 && (
        <div style={{ marginBottom: 12, padding: "8px 12px", background: "#fff7e6", borderRadius: 8, border: "1px solid #ffd591", display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ fontSize: 13 }}>已选 {selected.size} 笔</span>
          <button onClick={markSelected} style={{ padding: "4px 12px", border: "1px solid #d9d9d9", background: "#fff", borderRadius: 4, cursor: "pointer", fontSize: 13 }}>
            标记为内部转账
          </button>
        </div>
      )}

      <div style={{ fontSize: 13, color: "#666", marginBottom: 10 }}>
        共 <strong>{totalFiltered}</strong> 笔，合计 {fmtYuan(totalAmount)}
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th style={{ width: 40 }}>
                <input type="checkbox" checked={selected.size === pageItems.length && pageItems.length > 0}
                  onChange={toggleSelectAll} />
              </th>
              {columns.map((col) => (
                <th key={col.field}>{col.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageItems.length === 0 ? (
              <tr><td colSpan={columns.length + 1} style={{ textAlign: "center", color: "#999", padding: 20 }}>暂无匹配记录</td></tr>
            ) : (
              pageItems.map((tx, i) => (
                <tr key={i}>
                  <td>
                    <input type="checkbox" checked={selected.has(i)} onChange={() => toggleSelect(i)} />
                  </td>
                  {columns.map((col) => {
                    const val = txField(tx, col.field);
                    if (col.field === "amount") {
                      return (
                        <td key={col.field} style={{ color: txType === "income" ? "#389e0d" : "#cf1322", fontWeight: 600, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
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
              ))
            )}
          </tbody>
        </table>
      </div>

      <Pagination page={page} totalPages={totalPages} pageSize={pageSize}
        onPageChange={setPage} onPageSizeChange={(s) => { setPageSize(s); setPage(1); }} />
    </div>
  );
}
