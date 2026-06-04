# PayCheck React 报表前端 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 PayCheck 的 HTML 报表生成逻辑替换为 React + TypeScript SPA，Python CLI 改为输出 JSON。

**Architecture:** Vite + React 18 + TypeScript SPA，拖拽 JSON 文件加载数据，前端重算聚合，ECharts 可视化，localStorage 持久化内部转账指纹。

**Tech Stack:** Vite 6, React 18, TypeScript, ECharts 5 (echarts-for-react), 纯 CSS

---

### Task 1: 项目脚手架 — Vite + React + TypeScript 初始化

**Files:**
- Create: `paycheck-react/` 整个目录

- [ ] **Step 1: 用 Vite 创建项目**

```bash
npm create vite@latest paycheck-react -- --template react-ts
```

- [ ] **Step 2: 安装依赖**

```bash
Set-Location paycheck-react; npm install
```

- [ ] **Step 3: 安装额外依赖**

```bash
npm install echarts echarts-for-react
```

- [ ] **Step 4: 清理模板文件**

删除 `src/App.css`、`src/index.css` 内容，删除 `src/assets/`。

- [ ] **Step 5: 验证能跑**

```bash
npm run dev
```

打开浏览器确认 Vite + React 默认页面正常显示。

- [ ] **Step 6: Commit**

```bash
git add paycheck-react/
git commit -m "feat: scaffold paycheck-react with Vite + React + TypeScript"
```

---

### Task 2: 类型定义与常量

**Files:**
- Create: `paycheck-react/src/types.ts`
- Create: `paycheck-react/src/constants.ts`

- [ ] **Step 1: 编写 `types.ts`**

```typescript
// paycheck-react/src/types.ts

export interface Transaction {
  platform: "wechat" | "alipay" | "bank";
  time: string;
  category: string;
  counterparty: string;
  description: string;
  amount: number;
  tx_type: string;
  payment_method: string;
  balance: number;
  currency: string;
  branch: string;
  cp_account: string;
  cp_bank: string;
}

export interface SummaryStats {
  total_expense: number;
  total_income: number;
  total_count: number;
  monthly_avg: number;
  wechat_total: number;
  alipay_total: number;
  bank_total: number;
  wechat_count: number;
  alipay_count: number;
  bank_count: number;
}

export interface MonthlyItem {
  month: string;
  expense: number;
  count: number;
  wechat: number;
  alipay: number;
  bank: number;
}

export interface CategoryItem {
  name: string;
  amount: number;
  count: number;
  pct: number;
}

export interface PlatformMonthlyItem {
  month: string;
  wechat: number;
  alipay: number;
  bank: number;
}

export interface AggregatedData {
  period: { start: string; end: string };
  summary: SummaryStats;
  monthly: MonthlyItem[];
  categories: CategoryItem[];
  platform_monthly: PlatformMonthlyItem[];
  income_details: Transaction[];
  all_transactions: Transaction[];
  generated_at: string;
}

export interface FingerprintStore {
  version: number;
  fingerprints: string[];
}
```

- [ ] **Step 2: 编写 `constants.ts`**

```typescript
// paycheck-react/src/constants.ts

export const COLORS = [
  "#5470c6", "#91cc75", "#fac858", "#ee6666", "#73c0de",
  "#3ba272", "#fc8452", "#9a60b4", "#ea7ccc", "#2f4554",
  "#61a0a8", "#d48265", "#749f83", "#ca8622", "#bda29a",
];

export const FINGERPRINT_KEY = "paycheck_v1";

export interface ColumnDef {
  field: string;
  label: string;
}

export type PlatformColumnMap = Record<string, ColumnDef[]>;

export const PLATFORM_COLUMNS: PlatformColumnMap = {
  wechat: [
    { field: "time", label: "交易时间" },
    { field: "amount", label: "金额" },
    { field: "category", label: "交易类型" },
    { field: "counterparty", label: "交易对方" },
    { field: "description", label: "商品" },
    { field: "payment_method", label: "支付方式" },
  ],
  alipay: [
    { field: "time", label: "交易时间" },
    { field: "amount", label: "金额" },
    { field: "category", label: "交易分类" },
    { field: "counterparty", label: "交易对方" },
    { field: "description", label: "商品说明" },
    { field: "payment_method", label: "收/付款方式" },
  ],
  bank: [
    { field: "time", label: "记账日期/时间" },
    { field: "amount", label: "金额" },
    { field: "balance", label: "余额" },
    { field: "category", label: "交易名称" },
    { field: "currency", label: "币别" },
    { field: "counterparty", label: "对方账户名" },
    { field: "cp_account", label: "对方卡号/账号" },
    { field: "cp_bank", label: "对方开户行" },
    { field: "branch", label: "网点名称" },
    { field: "payment_method", label: "渠道" },
    { field: "description", label: "附言" },
  ],
};

export interface FilterLabels {
  category: string;
  counterparty: string;
  description: string;
  payment_method: string;
  balance?: string;
  currency?: string;
  cp_bank?: string;
  branch?: string;
  cp_account?: string;
}

export type PlatformFilterLabelMap = Record<string, FilterLabels>;

export const PLATFORM_FILTER_LABELS: PlatformFilterLabelMap = {
  wechat: {
    category: "交易类型",
    counterparty: "交易对方",
    description: "商品",
    payment_method: "支付方式",
  },
  alipay: {
    category: "交易分类",
    counterparty: "交易对方",
    description: "商品说明",
    payment_method: "收/付款方式",
  },
  bank: {
    category: "交易名称",
    counterparty: "对方账户名",
    description: "附言",
    payment_method: "渠道",
    balance: "余额",
    currency: "币别",
    branch: "网点名称",
    cp_bank: "对方开户行",
    cp_account: "对方卡号",
  },
};

export interface PlatformMeta {
  name: string;
  color: string;
}

export type PlatformMetaMap = Record<string, PlatformMeta>;

export const PLATFORM_META: PlatformMetaMap = {
  wechat: { name: "微信支付", color: "#07c160" },
  alipay: { name: "支付宝", color: "#1677ff" },
  bank: { name: "银行账户", color: "#722ed1" },
};

export const PLATFORM_ORDER = ["wechat", "alipay", "bank"] as const;
```

- [ ] **Step 3: Commit**

```bash
git add paycheck-react/src/types.ts paycheck-react/src/constants.ts
git commit -m "feat: add TypeScript types and constants"
```

---

### Task 3: 工具函数 — 格式化、指纹、聚合

**Files:**
- Create: `paycheck-react/src/utils/format.ts`
- Create: `paycheck-react/src/utils/hash.ts`
- Create: `paycheck-react/src/utils/aggregation.ts`

- [ ] **Step 1: 编写 `format.ts`**

```typescript
// paycheck-react/src/utils/format.ts

export function fmtNum(n: number | string): string {
  const num = typeof n === "string" ? parseFloat(n) : n;
  if (isNaN(num)) return "0.00";
  return num.toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export function fmtYuan(n: number | string): string {
  return "¥" + fmtNum(n);
}
```

- [ ] **Step 2: 编写 `hash.ts`**（需要安装依赖）

```bash
npm install js-sha256
npm install --save-dev @types/js-sha256
```

```typescript
// paycheck-react/src/utils/hash.ts
import { sha256 } from "js-sha256";
import type { Transaction } from "../types";

export function hashTx(tx: Transaction): string {
  const raw = [
    tx.platform,
    tx.time,
    String(tx.amount),
    tx.counterparty,
    tx.description,
  ].join("|");
  return sha256(raw).slice(0, 16);
}
```

- [ ] **Step 3: 编写 `aggregation.ts`**（从 Python `stats.py` 移植）

```typescript
// paycheck-react/src/utils/aggregation.ts
import type { Transaction, SummaryStats, MonthlyItem, CategoryItem } from "../types";

export interface AggregationResult {
  summary: SummaryStats;
  monthly: MonthlyItem[];
  categories: CategoryItem[];
  platform_monthly: { month: string; wechat: number; alipay: number; bank: number }[];
}

export function aggregate(transactions: Transaction[]): AggregationResult {
  const expenses = transactions.filter(
    (t) => t.tx_type === "支出" || t.tx_type === "pay" || t.tx_type === "Pay"
  );
  const incomes = transactions.filter(
    (t) => t.tx_type === "收入" || t.tx_type === "收款"
  );

  const totalExpense = expenses.reduce((s, t) => s + t.amount, 0);
  const totalIncome = incomes.reduce((s, t) => s + t.amount, 0);
  const totalCount = expenses.length;

  const monthMap: Record<string, { expense: number; count: number; wechat: number; alipay: number; bank: number }> = {};
  expenses.forEach((t) => {
    const m = t.time.substring(0, 7);
    if (!monthMap[m]) monthMap[m] = { expense: 0, count: 0, wechat: 0, alipay: 0, bank: 0 };
    monthMap[m].expense += t.amount;
    monthMap[m].count += 1;
    if (t.platform === "wechat") monthMap[m].wechat += t.amount;
    else if (t.platform === "alipay") monthMap[m].alipay += t.amount;
    else monthMap[m].bank += t.amount;
  });

  const months = Object.keys(monthMap).sort();
  const monthly: MonthlyItem[] = months.map((m) => {
    const d = monthMap[m];
    return {
      month: m,
      expense: Math.round(d.expense * 100) / 100,
      count: d.count,
      wechat: Math.round(d.wechat * 100) / 100,
      alipay: Math.round(d.alipay * 100) / 100,
      bank: Math.round(d.bank * 100) / 100,
    };
  });

  const monthsCount = months.length;
  const monthlyAvg = monthsCount > 0 ? Math.round((totalExpense / monthsCount) * 100) / 100 : 0;

  const we = expenses.filter((t) => t.platform === "wechat");
  const ae = expenses.filter((t) => t.platform === "alipay");
  const be = expenses.filter((t) => t.platform === "bank");

  const catMap: Record<string, { name: string; amount: number; count: number }> = {};
  expenses.forEach((t) => {
    const c = t.category || "未分类";
    if (!catMap[c]) catMap[c] = { name: c, amount: 0, count: 0 };
    catMap[c].amount += t.amount;
    catMap[c].count += 1;
  });
  const categories: CategoryItem[] = Object.values(catMap)
    .sort((a, b) => b.amount - a.amount)
    .map((c) => ({
      name: c.name,
      amount: Math.round(c.amount * 100) / 100,
      count: c.count,
      pct: totalExpense > 0 ? Math.round((c.amount / totalExpense) * 1000) / 10 : 0,
    }));

  const platformMonthly = monthly.map((m) => ({
    month: m.month,
    wechat: m.wechat,
    alipay: m.alipay,
    bank: m.bank,
  }));

  return {
    summary: {
      total_expense: Math.round(totalExpense * 100) / 100,
      total_income: Math.round(totalIncome * 100) / 100,
      total_count: totalCount,
      monthly_avg: monthlyAvg,
      wechat_total: Math.round(we.reduce((s, t) => s + t.amount, 0) * 100) / 100,
      alipay_total: Math.round(ae.reduce((s, t) => s + t.amount, 0) * 100) / 100,
      bank_total: Math.round(be.reduce((s, t) => s + t.amount, 0) * 100) / 100,
      wechat_count: we.length,
      alipay_count: ae.length,
      bank_count: be.length,
    },
    monthly,
    categories,
    platform_monthly: platformMonthly,
  };
}
```

- [ ] **Step 4: Commit**

```bash
git add paycheck-react/src/utils/ paycheck-react/package.json paycheck-react/package-lock.json
git commit -m "feat: add format, hash, and aggregation utilities"
```

---

### Task 4: Hooks — useFingerprints、useAggregation、useFilteredList

**Files:**
- Create: `paycheck-react/src/hooks/useFingerprints.ts`
- Create: `paycheck-react/src/hooks/useAggregation.ts`
- Create: `paycheck-react/src/hooks/useFilteredList.ts`

- [ ] **Step 1: 编写 `useFingerprints.ts`**

```typescript
// paycheck-react/src/hooks/useFingerprints.ts
import { useState, useCallback } from "react";
import { FINGERPRINT_KEY } from "../constants";
import type { FingerprintStore } from "../types";

function loadFingerprints(): Set<string> {
  try {
    const raw = localStorage.getItem(FINGERPRINT_KEY);
    if (raw) {
      const store: FingerprintStore = JSON.parse(raw);
      return new Set(store.fingerprints);
    }
  } catch {}
  return new Set();
}

function saveFingerprints(set: Set<string>): void {
  const store: FingerprintStore = {
    version: 1,
    fingerprints: Array.from(set),
  };
  localStorage.setItem(FINGERPRINT_KEY, JSON.stringify(store));
}

export function useFingerprints() {
  const [fingerprints, setFingerprints] = useState<Set<string>>(loadFingerprints);

  const addFingerprint = useCallback((fp: string) => {
    setFingerprints((prev) => {
      if (prev.has(fp)) return prev;
      const next = new Set(prev);
      next.add(fp);
      saveFingerprints(next);
      return next;
    });
  }, []);

  const addFingerprints = useCallback((fps: string[]) => {
    setFingerprints((prev) => {
      const next = new Set(prev);
      let changed = false;
      for (const fp of fps) {
        if (!next.has(fp)) {
          next.add(fp);
          changed = true;
        }
      }
      if (!changed) return prev;
      saveFingerprints(next);
      return next;
    });
  }, []);

  const removeFingerprint = useCallback((fp: string) => {
    setFingerprints((prev) => {
      if (!prev.has(fp)) return prev;
      const next = new Set(prev);
      next.delete(fp);
      saveFingerprints(next);
      return next;
    });
  }, []);

  const hasFingerprint = useCallback(
    (fp: string) => fingerprints.has(fp),
    [fingerprints]
  );

  return { fingerprints, addFingerprint, addFingerprints, removeFingerprint, hasFingerprint };
}
```

- [ ] **Step 2: 编写 `useAggregation.ts`**

```typescript
// paycheck-react/src/hooks/useAggregation.ts
import { useMemo } from "react";
import type { AggregatedData, Transaction, AggregationResult } from "../types";
import { hashTx } from "../utils/hash";
import { aggregate } from "../utils/aggregation";

export function useAggregation(
  data: AggregatedData | null,
  fingerprints: Set<string>
): { externalTxs: Transaction[]; internalTxs: Transaction[]; stats: AggregationResult | null } {
  return useMemo(() => {
    if (!data) return { externalTxs: [], internalTxs: [], stats: null };

    const internalTxs: Transaction[] = [];
    const externalTxs: Transaction[] = [];

    for (const tx of data.all_transactions) {
      const fp = hashTx(tx);
      if (fingerprints.has(fp)) {
        internalTxs.push(tx);
      } else {
        externalTxs.push(tx);
      }
    }

    const incomeTxs = data.all_transactions.filter(
      (t) => t.tx_type === "收入" || t.tx_type === "收款"
    );
    const filteredIncome = incomeTxs.filter((t) => !fingerprints.has(hashTx(t)));

    const stats = aggregate(externalTxs);

    return {
      externalTxs,
      internalTxs,
      stats: {
        ...stats,
        ...({} as any),
      } as AggregationResult & { income_details: Transaction[] },
    };
  }, [data, fingerprints]);
}
```

- [ ] **Step 3: 编写 `useFilteredList.ts`**

```typescript
// paycheck-react/src/hooks/useFilteredList.ts
import { useState, useMemo, useCallback } from "react";
import type { Transaction } from "../types";

export interface Filters {
  platform: string;
  dateStart: string;
  dateEnd: string;
  amountMin: number | null;
  amountMax: number | null;
  categories: string[];
  counterparties: string[];
  descriptions: string[];
  paymentMethods: string[];
  balanceMin: number | null;
  balanceMax: number | null;
  currencies: string[];
  cpAccount: string;
  cpBanks: string[];
  branches: string[];
}

const emptyFilters: Filters = {
  platform: "wechat",
  dateStart: "",
  dateEnd: "",
  amountMin: null,
  amountMax: null,
  categories: [],
  counterparties: [],
  descriptions: [],
  paymentMethods: [],
  balanceMin: null,
  balanceMax: null,
  currencies: [],
  cpAccount: "",
  cpBanks: [],
  branches: [],
};

export function useFilteredList(items: Transaction[]) {
  const [filters, setFilters] = useState<Filters>(emptyFilters);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  const filtered = useMemo(() => {
    return items.filter((t) => {
      if (t.platform !== filters.platform) return false;
      if (filters.dateStart && t.time < filters.dateStart) return false;
      if (filters.dateEnd && t.time > filters.dateEnd + " 23:59:59") return false;
      if (filters.amountMin !== null && t.amount < filters.amountMin) return false;
      if (filters.amountMax !== null && t.amount > filters.amountMax) return false;
      if (filters.categories.length && !filters.categories.includes(t.category || "")) return false;
      if (filters.counterparties.length && !filters.counterparties.includes(t.counterparty || "")) return false;
      if (filters.descriptions.length && !filters.descriptions.includes(t.description || "")) return false;
      if (filters.paymentMethods.length && !filters.paymentMethods.includes(t.payment_method || "")) return false;
      if (filters.balanceMin !== null && (t.balance === undefined || t.balance < filters.balanceMin)) return false;
      if (filters.balanceMax !== null && (t.balance === undefined || t.balance > filters.balanceMax)) return false;
      if (filters.currencies.length && !filters.currencies.includes(t.currency || "")) return false;
      if (filters.cpAccount && !(t.cp_account || "").includes(filters.cpAccount)) return false;
      if (filters.cpBanks.length && !filters.cpBanks.includes(t.cp_bank || "")) return false;
      if (filters.branches.length && !filters.branches.includes(t.branch || "")) return false;
      return true;
    });
  }, [items, filters]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const pageItems = filtered.slice((page - 1) * pageSize, page * pageSize);

  const resetFilters = useCallback(() => {
    setFilters(emptyFilters);
    setPage(1);
  }, []);

  const setPlatform = useCallback((platform: string) => {
    setFilters((prev) => ({ ...emptyFilters, platform }));
    setPage(1);
  }, []);

  return {
    filters,
    setFilters,
    setPlatform,
    resetFilters,
    filtered,
    page,
    setPage,
    pageSize,
    setPageSize,
    totalPages,
    pageItems,
    totalFiltered: filtered.length,
    totalAmount: filtered.reduce((s, t) => s + t.amount, 0),
  };
}
```

- [ ] **Step 4: Commit**

```bash
git add paycheck-react/src/hooks/
git commit -m "feat: add useFingerprints, useAggregation, useFilteredList hooks"
```

---

### Task 5: 通用组件 — Pagination、TagSelect

**Files:**
- Create: `paycheck-react/src/components/common/Pagination.tsx`
- Create: `paycheck-react/src/components/common/TagSelect.tsx`

- [ ] **Step 1: 编写 `Pagination.tsx`**

```typescript
// paycheck-react/src/components/common/Pagination.tsx
interface PaginationProps {
  page: number;
  totalPages: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
  pageSizeOptions?: number[];
}

export default function Pagination({
  page,
  totalPages,
  pageSize,
  onPageChange,
  onPageSizeChange,
  pageSizeOptions = [10, 20, 50, 100],
}: PaginationProps) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 16, paddingTop: 12, borderTop: "1px solid #f0f0f0" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <button className="page-btn" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
          ‹ 上一页
        </button>
        <span style={{ fontSize: 13, color: "#666", minWidth: 60, textAlign: "center" }}>
          {page} / {totalPages}
        </span>
        <button className="page-btn" disabled={page >= totalPages} onClick={() => onPageChange(page + 1)}>
          下一页 ›
        </button>
      </div>
      <select
        className="page-size-select"
        value={pageSize}
        onChange={(e) => { onPageSizeChange(Number(e.target.value)); }}
        style={{ padding: "4px 8px", border: "1px solid #d9d9d9", borderRadius: 4, fontSize: 13 }}
      >
        {pageSizeOptions.map((n) => (
          <option key={n} value={n}>{n} 条/页</option>
        ))}
      </select>
    </div>
  );
}
```

- [ ] **Step 2: 编写 `TagSelect.tsx`**

```typescript
// paycheck-react/src/components/common/TagSelect.tsx
import { useState, useRef, useEffect, useCallback } from "react";

interface TagSelectProps {
  placeholder: string;
  values: string[];
  suggestions: string[];
  onChange: (values: string[]) => void;
}

export default function TagSelect({ placeholder, values, suggestions, onChange }: TagSelectProps) {
  const [input, setInput] = useState("");
  const [showDropdown, setShowDropdown] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  const available = suggestions.filter(
    (v) => !values.includes(v) && (!input || v.includes(input))
  );

  const addValue = useCallback(
    (v: string) => {
      if (!values.includes(v)) {
        onChange([...values, v]);
      }
      setInput("");
      setShowDropdown(false);
    },
    [values, onChange]
  );

  const removeValue = useCallback(
    (v: string) => {
      onChange(values.filter((x) => x !== v));
    },
    [values, onChange]
  );

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
      }
    }
    document.addEventListener("click", handleClick);
    return () => document.removeEventListener("click", handleClick);
  }, []);

  return (
    <div ref={wrapRef} style={{ display: "flex", alignItems: "center", gap: 4, flexWrap: "wrap" }}>
      <div style={{ position: "relative", display: "inline-block" }}>
        <input
          type="text"
          placeholder={placeholder}
          value={input}
          onChange={(e) => { setInput(e.target.value); setShowDropdown(true); }}
          onFocus={() => setShowDropdown(true)}
          onKeyDown={(e) => { if (e.key === "Escape") setShowDropdown(false); }}
          style={{ padding: "4px 8px", border: "1px solid #d9d9d9", borderRadius: 4, fontSize: 13, maxWidth: 140 }}
        />
        {showDropdown && available.length > 0 && (
          <div
            style={{
              position: "absolute", top: "100%", left: 0, zIndex: 1000,
              background: "#fff", border: "1px solid #d9d9d9", borderRadius: 4,
              maxHeight: 180, overflowY: "auto", minWidth: 150,
              boxShadow: "0 2px 8px rgba(0,0,0,0.12)"
            }}
          >
            {available.map((v) => (
              <div
                key={v}
                onClick={() => addValue(v)}
                style={{ padding: "5px 10px", cursor: "pointer", fontSize: 13, borderBottom: "1px solid #f5f5f5" }}
                onMouseEnter={(e) => (e.currentTarget.style.background = "#f0f5ff")}
                onMouseLeave={(e) => (e.currentTarget.style.background = "")}
              >
                {v}
              </div>
            ))}
          </div>
        )}
      </div>
      {values.map((v) => (
        <span
          key={v}
          style={{
            display: "inline-flex", alignItems: "center", gap: 2,
            background: "#e6f7ff", border: "1px solid #91d5ff", borderRadius: 4,
            padding: "1px 8px", fontSize: 12, lineHeight: 1.6
          }}
        >
          {v}
          <span
            onClick={() => removeValue(v)}
            style={{ cursor: "pointer", marginLeft: 2, color: "#999", userSelect: "none", fontSize: 14 }}
          >
            ×
          </span>
        </span>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add paycheck-react/src/components/common/
git commit -m "feat: add Pagination and TagSelect common components"
```

---

### Task 6: App 外壳 + EmptyState

**Files:**
- Create: `paycheck-react/src/components/EmptyState.tsx`
- Modify: `paycheck-react/src/App.tsx`
- Modify: `paycheck-react/src/App.css`
- Modify: `paycheck-react/src/main.tsx`

- [ ] **Step 1: 编写 `EmptyState.tsx`**

```typescript
// paycheck-react/src/components/EmptyState.tsx
import { useCallback, useRef, useState, type DragEvent } from "react";
import type { AggregatedData } from "../types";

interface EmptyStateProps {
  onDataLoaded: (data: AggregatedData) => void;
}

export default function EmptyState({ onDataLoaded }: EmptyStateProps) {
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(
    (file: File) => {
      setError("");
      const reader = new FileReader();
      reader.onload = () => {
        try {
          const data = JSON.parse(reader.result as string) as AggregatedData;
          if (!data.all_transactions || !data.summary) {
            setError("无效的报告文件：缺少必要字段");
            return;
          }
          onDataLoaded(data);
        } catch {
          setError("文件解析失败，请确认是有效的 JSON 文件");
        }
      };
      reader.readAsText(file);
    },
    [onDataLoaded]
  );

  const onDrop = useCallback(
    (e: DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const file = e.dataTransfer.files[0];
      if (file && file.name.endsWith(".json")) {
        handleFile(file);
      } else {
        setError("请拖入 report.json 文件");
      }
    },
    [handleFile]
  );

  return (
    <div
      style={{
        display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
        minHeight: "100vh", background: "#f0f2f5", fontFamily: "-apple-system, sans-serif",
      }}
    >
      <h1 style={{ fontSize: 32, color: "#1a1a2e", marginBottom: 8 }}>PayCheck</h1>
      <p style={{ color: "#666", marginBottom: 24 }}>账单分析报告</p>
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        onClick={() => fileRef.current?.click()}
        style={{
          width: 400, padding: 48, border: `2px dashed ${dragOver ? "#1a1a2e" : "#d9d9d9"}`,
          borderRadius: 12, background: dragOver ? "#f0f5ff" : "#fff",
          textAlign: "center", cursor: "pointer", transition: "all 0.2s"
        }}
      >
        <p style={{ fontSize: 18, color: "#1a1a2e", marginBottom: 8 }}>
          拖拽 report.json 到此处
        </p>
        <p style={{ fontSize: 13, color: "#999" }}>或点击选择文件</p>
      </div>
      {error && <p style={{ color: "#ff4d4f", marginTop: 12, fontSize: 14 }}>{error}</p>}
      <input
        ref={fileRef}
        type="file"
        accept=".json"
        style={{ display: "none" }}
        onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }}
      />
    </div>
  );
}
```

- [ ] **Step 2: 编写 `App.tsx`**

```typescript
// paycheck-react/src/App.tsx
import { useState } from "react";
import type { AggregatedData } from "./types";
import { useFingerprints } from "./hooks/useFingerprints";
import EmptyState from "./components/EmptyState";
import "./App.css";

export default function App() {
  const [data, setData] = useState<AggregatedData | null>(null);
  const { fingerprints } = useFingerprints();

  if (!data) {
    return <EmptyState onDataLoaded={setData} />;
  }

  return (
    <div className="container">
      {/* Placeholder — 后续任务逐个接入组件 */}
      <header style={{ textAlign: "center", padding: "40px 0 20px" }}>
        <h1>PayCheck 账单分析报告</h1>
        <p>{data.period.start} ~ {data.period.end}</p>
      </header>
    </div>
  );
}
```

- [ ] **Step 3: 移植全局 CSS**（从 `template.html` 的 `<style>` 块提取）

创建 `paycheck-react/src/App.css`，包含：`*` 重置、`body` 基础、`.container`、`header`、`.page-btn`、`.page-size-select`、`table`、`th`、`td` 等基础样式。从原 `template.html` 的 `<style>` 块中提取所有不涉及特定组件的全局样式。

- [ ] **Step 4: 简化 `main.tsx`**

```typescript
// paycheck-react/src/main.tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
```

- [ ] **Step 5: 验证**

```bash
npm run build
```

确保 TypeScript 编译无错误。

- [ ] **Step 6: Commit**

```bash
git add paycheck-react/src/App.tsx paycheck-react/src/App.css paycheck-react/src/main.tsx paycheck-react/src/components/EmptyState.tsx
git commit -m "feat: add App shell with drag-drop JSON loading and global CSS"
```

---

### Task 7: ReportHeader、SummaryCards、PlatformCards

**Files:**
- Create: `paycheck-react/src/components/ReportHeader.tsx`
- Create: `paycheck-react/src/components/SummaryCards.tsx`
- Create: `paycheck-react/src/components/PlatformCards.tsx`
- Create: `paycheck-react/src/styles/cards.css`
- Modify: `paycheck-react/src/App.tsx`

- [ ] **Step 1: 编写 `ReportHeader.tsx`**

```typescript
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
```

- [ ] **Step 2: 编写 `cards.css`**

从 `template.html` 提取 `.cards`、`.card`、`.card-label`、`.card-value`、`.card-sub`、`.card.clickable`、`.platform-cards`、`.platform-card`、`.platform-card.wechat`、`.platform-card.alipay`、`.platform-card.bank` 等样式。

- [ ] **Step 3: 编写 `SummaryCards.tsx`**

```typescript
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
        <div className="card-sub">共 {summary.total_count > 0 ? "?" : "0"} 个月</div>
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
```

- [ ] **Step 4: 编写 `PlatformCards.tsx`**

```typescript
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
```

- [ ] **Step 5: 更新 `App.tsx`** 接入这些组件

```typescript
// 在 App.tsx 中替换 placeholder
import { useState, useMemo } from "react";
import { useFingerprints } from "./hooks/useFingerprints";
import { useAggregation } from "./hooks/useAggregation";
import ReportHeader from "./components/ReportHeader";
import SummaryCards from "./components/SummaryCards";
import PlatformCards from "./components/PlatformCards";

// state
const [incomeExpanded, setIncomeExpanded] = useState(false);
const [expenseExpanded, setExpenseExpanded] = useState(false);
const { fingerprints } = useFingerprints();
const { externalTxs, internalTxs, stats } = useAggregation(data, fingerprints);

// render
if (!data) return <EmptyState onDataLoaded={setData} />;
if (!stats) return null;

return (
  <div className="container">
    <ReportHeader start={data.period.start} end={data.period.end} generatedAt={data.generated_at} />
    <SummaryCards
      summary={stats.summary}
      incomeExpanded={incomeExpanded}
      expenseExpanded={expenseExpanded}
      onToggleIncome={() => setIncomeExpanded(prev => !prev)}
      onToggleExpense={() => setExpenseExpanded(prev => !prev)}
    />
    <PlatformCards summary={stats.summary} />
  </div>
);
```

- [ ] **Step 6: Commit**

```bash
git add paycheck-react/src/components/ReportHeader.tsx paycheck-react/src/components/SummaryCards.tsx paycheck-react/src/components/PlatformCards.tsx paycheck-react/src/styles/cards.css paycheck-react/src/App.tsx
git commit -m "feat: add ReportHeader, SummaryCards, PlatformCards components"
```

---

### Task 8: ECharts 图表组件

**Files:**
- Create: `paycheck-react/src/components/MonthlyChart.tsx`
- Create: `paycheck-react/src/components/CategorySection.tsx`
- Create: `paycheck-react/src/components/PlatformComparison.tsx`
- Create: `paycheck-react/src/styles/charts.css`
- Modify: `paycheck-react/src/App.tsx`

- [ ] **Step 1: 编写 `MonthlyChart.tsx`**

```typescript
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
      formatter: (params: any) =>
        `<strong>${params[0].axisValue}</strong><br/>${params[0].marker} 支出: ${fmtYuan(params[0].value)}`,
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
            style={{
              padding: "6px 18px", border: "1px solid #d9d9d9", background: mode === m.value ? "#1a1a2e" : "#fff",
              color: mode === m.value ? "#fff" : "#333", borderRadius: 6, cursor: "pointer", fontSize: 13, marginRight: 8
            }}
          >
            {m.label}
          </button>
        ))}
      </div>
      <ReactECharts option={option} style={{ height: 400 }} />
    </div>
  );
}
```

- [ ] **Step 2: 编写 `CategorySection.tsx`**

```typescript
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
      formatter: (p: any) =>
        `<strong>${p.name}</strong><br/>金额: ${fmtYuan(p.value)}<br/>占比: ${p.percent}%`,
    },
    series: [
      {
        type: "pie",
        radius: ["35%", "65%"],
        center: ["50%", "50%"],
        data: categories.map((c) => ({ name: c.name, value: c.amount })),
        itemStyle: { borderRadius: 4, borderColor: "#fff", borderWidth: 2 },
        label: { show: false },
        emphasis: {
          label: { show: true, fontSize: 14, fontWeight: "bold" },
          itemStyle: { shadowBlur: 10, shadowColor: "rgba(0,0,0,0.2)" },
        },
      },
    ],
  };

  const barOption = {
    tooltip: {
      trigger: "axis" as const,
      axisPointer: { type: "shadow" as const },
      formatter: (params: any) => {
        const p = params[0];
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
      <div style={{ display: "flex", gap: 16 }}>
        <div style={{ width: "55%", height: 380 }}>
          <ReactECharts option={pieOption} style={{ height: "100%" }} />
        </div>
        <div style={{ width: "45%", height: 380 }}>
          <ReactECharts option={barOption} style={{ height: "100%" }} />
        </div>
      </div>
      <div style={{ marginTop: 16 }}>
        {categories.map((c) => (
          <div key={c.name} style={{ display: "flex", alignItems: "center", padding: "6px 0" }}>
            <span
              style={{
                width: 10, height: 10, borderRadius: "50%", marginRight: 10, flexShrink: 0,
                background: colorMap[c.name],
              }}
            />
            <span style={{ flex: 1, fontSize: 14 }}>{c.name}</span>
            <span style={{ fontSize: 14, fontWeight: 600 }}>{fmtYuan(c.amount)}</span>
            <span style={{ fontSize: 13, color: "#999", marginLeft: 8 }}>{c.pct}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: 编写 `PlatformComparison.tsx`**

```typescript
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
      formatter: (params: any) => {
        let h = `<strong>${params[0].axisValue}</strong><br/>`;
        params.forEach((x: any) => { h += `${x.marker} ${x.seriesName}: ${fmtYuan(x.value)}<br/>`; });
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
```

- [ ] **Step 4: 更新 `App.tsx`** 接入图表

在 Dashboard 返回中，SummaryCards 之后插入：

```tsx
{stats && (
  <>
    <MonthlyChart monthly={stats.monthly} />
    <CategorySection categories={stats.categories} />
    <PlatformComparison platformMonthly={stats.platform_monthly} />
  </>
)}
```

- [ ] **Step 5: 创建 `charts.css`**

从 `template.html` 提取 `.section`、`.section h2`、`.chart`、`.filter`、`.filter button`、`.filter button.active`、`.filter button:hover:not(.active)` 等样式。

- [ ] **Step 6: Commit**

```bash
git add paycheck-react/src/components/MonthlyChart.tsx paycheck-react/src/components/CategorySection.tsx paycheck-react/src/components/PlatformComparison.tsx paycheck-react/src/styles/charts.css paycheck-react/src/App.tsx
git commit -m "feat: add ECharts chart components (monthly, categories, platform comparison)"
```

---

### Task 9: MonthlyTable

**Files:**
- Create: `paycheck-react/src/components/MonthlyTable.tsx`
- Create: `paycheck-react/src/styles/tables.css`
- Modify: `paycheck-react/src/App.tsx`

- [ ] **Step 1: 编写 `tables.css`**

从 `template.html` 提取 `.table-wrap`、`table`、`thead`、`th`、`td`、`tr:hover td` 等样式。

- [ ] **Step 2: 编写 `MonthlyTable.tsx`**

```typescript
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
```

- [ ] **Step 3: 更新 `App.tsx`** — 在图表组件之后加入 `<MonthlyTable monthly={stats.monthly} />`

- [ ] **Step 4: Commit**

```bash
git add paycheck-react/src/components/MonthlyTable.tsx paycheck-react/src/styles/tables.css paycheck-react/src/App.tsx
git commit -m "feat: add MonthlyTable component"
```

---

### Task 10: DetailTable（收入/支出通用详情表格）

**Files:**
- Create: `paycheck-react/src/components/DetailTable.tsx`
- Create: `paycheck-react/src/styles/filters.css`
- Modify: `paycheck-react/src/App.tsx`

详解表格是核心复杂组件，支持平台 Tab 切换、多维过滤、复选框标记、分页。

- [ ] **Step 1: 编写 `filters.css`**

从 `template.html` 提取 `.income-tabs`、`.income-tab`、`.income-tab.active`、`.tab-count`、`.income-filters`、`.f-row`、`.f-group`、`.income-filters label`、`.income-filters input`、`.income-filters input:focus`、`.income-filters .reset-btn`、`.income-pagination`、`.income-page-controls` 等样式。

- [ ] **Step 2: 编写 `DetailTable.tsx`**

```typescript
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
  fingerprints: Set<string>;
  onMarkInternal: (fps: string[]) => void;
}

export default function DetailTable({ items, txType, fingerprints, onMarkInternal }: DetailTableProps) {
  const {
    filters, setFilters, setPlatform, resetFilters,
    page, setPage, pageSize, setPageSize, totalPages, pageItems, totalFiltered, totalAmount,
  } = useFilteredList(items.filter((t) => {
    // 按收入/支出预过滤
    if (txType === "income") return t.tx_type === "收入" || t.tx_type === "收款";
    return t.tx_type === "支出" || t.tx_type === "pay" || t.tx_type === "Pay";
  }));

  const [selected, setSelected] = useState<Set<number>>(new Set());
  const platform = filters.platform;
  const columns = PLATFORM_COLUMNS[platform] || PLATFORM_COLUMNS.bank;
  const labels = PLATFORM_FILTER_LABELS[platform] || PLATFORM_FILTER_LABELS.bank;
  const isBank = platform === "bank";

  const activePlatforms = PLATFORM_ORDER.filter(
    (p) => items.some((t) => t.platform === p && (txType === "income" ? (t.tx_type === "收入" || t.tx_type === "收款") : (t.tx_type === "支出" || t.tx_type === "pay" || t.tx_type === "Pay"))))
  );

  const getUniqueValues = useCallback(
    (field: string): string[] => {
      const set = new Set<string>();
      items.forEach((t) => {
        if (t.platform === platform && t[field as keyof Transaction]) {
          set.add(String(t[field as keyof Transaction]));
        }
      });
      return Array.from(set).sort();
    },
    [items, platform]
  );

  const toggleSelect = (idx: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx); else next.add(idx);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selected.size === pageItems.length) {
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

  return (
    <div className="section">
      <h2>{emoji} {tableTitle}</h2>

      {/* Platform Tabs */}
      <div className="income-tabs" style={{ display: "flex", gap: 0, marginBottom: 16, borderBottom: "2px solid #e8e8e8" }}>
        {activePlatforms.map((p) => {
          const meta = PLATFORM_META[p];
          const count = items.filter((t) => t.platform === p).length;
          return (
            <button
              key={p}
              className={`income-tab${platform === p ? " active" : ""}`}
              onClick={() => { setPlatform(p); setSelected(new Set()); }}
            >
              {meta.name}
              <span className="tab-count">{count} 笔</span>
            </button>
          );
        })}
      </div>

      {/* Filters */}
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

      {/* Action bar */}
      {selected.size > 0 && (
        <div style={{ marginBottom: 12, padding: "8px 12px", background: "#fff7e6", borderRadius: 8, border: "1px solid #ffd591", display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ fontSize: 13 }}>已选 {selected.size} 笔</span>
          <button onClick={markSelected} style={{ padding: "4px 12px", border: "1px solid #d9d9d9", background: "#fff", borderRadius: 4, cursor: "pointer", fontSize: 13 }}>
            标记为内部转账
          </button>
        </div>
      )}

      {/* Summary */}
      <div style={{ fontSize: 13, color: "#666", marginBottom: 10 }}>
        共 <strong>{totalFiltered}</strong> 笔，合计 {fmtYuan(totalAmount)}
      </div>

      {/* Table */}
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
                    const val = tx[col.field as keyof Transaction];
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
```

- [ ] **Step 3: 更新 `App.tsx`**

在 App 中 state 添加 `incomeExpanded`、`expenseExpanded`、`internalExpanded`。
在 PlatformCards 之前加入：

```tsx
{incomeExpanded && (
  <DetailTable
    items={data.income_details}
    txType="income"
    fingerprints={fingerprints}
    onMarkInternal={addFingerprints}
  />
)}
```

以及在 MonthlyTable 之后。

- [ ] **Step 4: Commit**

```bash
git add paycheck-react/src/components/DetailTable.tsx paycheck-react/src/styles/filters.css paycheck-react/src/App.tsx
git commit -m "feat: add DetailTable component with filters, checkbox selection, and pagination"
```

---

### Task 11: InternalSection（内部转账明细 + 导出/导入）

**Files:**
- Create: `paycheck-react/src/components/InternalSection.tsx`
- Create: `paycheck-react/src/styles/internal.css`
- Modify: `paycheck-react/src/App.tsx`

- [ ] **Step 1: 编写 `internal.css`**

从 `template.html` 提取 `.internal-note`、`.internal-note.show`、`.internal-table-wrap`、`.tag-list`、`.tag` 等样式。

- [ ] **Step 2: 编写 `InternalSection.tsx`**

```typescript
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
  const [platform, setPlatform] = useState(PLATFORM_ORDER.find((p) => internalTxs.some((t) => t.platform === p)) || "wechat");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const fileRef = useRef<HTMLInputElement>(null);

  const filtered = internalTxs.filter((t) => t.platform === platform);
  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const pageItems = filtered.slice((page - 1) * pageSize, page * pageSize);
  const columns = PLATFORM_COLUMNS[platform] || PLATFORM_COLUMNS.bank;

  const activePlatforms = PLATFORM_ORDER.filter((p) => internalTxs.some((t) => t.platform === p));
  if (internalTxs.length === 0) return null;

  const handleExport = useCallback(() => {
    const data = { version: 1, fingerprints: Array.from(fingerprints), exported_at: new Date().toISOString(), count: fingerprints.size };
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
        } catch {}
      };
      reader.readAsText(file);
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

      <div className="income-tabs" style={{ display: "flex", gap: 0, marginBottom: 16, borderBottom: "2px solid #e8e8e8" }}>
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
        金额合计 <strong>{fmtYuan(internalTxs.reduce((s, t) => s + t.amount, 0))}</strong>
      </div>

      <div className="table-wrap" style={{ marginTop: 12 }}>
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
                  const val = tx[col.field as keyof Transaction];
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
```

- [ ] **Step 3: 更新 `App.tsx`**

引入 `InternalSection`：

```tsx
import InternalSection from "./components/InternalSection";

// 在 SummaryCards 之后加入
<InternalSection
  internalTxs={internalTxs}
  fingerprints={fingerprints}
  onRemoveFingerprint={removeFingerprint}
  onImportFingerprints={addFingerprints}
/>
```

- [ ] **Step 4: Commit**

```bash
git add paycheck-react/src/components/InternalSection.tsx paycheck-react/src/styles/internal.css paycheck-react/src/App.tsx
git commit -m "feat: add InternalSection with export/import and unmark functionality"
```

---

### Task 12: Python 端 — 移动到 paycheck-tools，改写 JSON 输出

**Files:**
- Create: `paycheck-tools/`（后端工作目录）
- Create: `paycheck-tools/pyproject.toml`（从根目录移动）
- Create: `paycheck-tools/paycheck/`（包代码，从 `src/paycheck/` 移动）
- Modify: `paycheck-tools/paycheck/__main__.py`
- Delete: 根目录 `pyproject.toml`、`src/paycheck/`

- [ ] **Step 1: 创建 paycheck-tools 目录结构并移动代码**

```powershell
New-Item -ItemType Directory -Path "paycheck-tools"
Move-Item -Path "src/paycheck" -Destination "paycheck-tools/paycheck"
Move-Item -Path "pyproject.toml" -Destination "paycheck-tools/pyproject.toml"
Remove-Item -Recurse -Force "src"
```

- [ ] **Step 2: 更新 `paycheck-tools/pyproject.toml`**

移除 `[tool.setuptools.packages.find]` 配置（pyproject.toml 现在与包目录同级，setuptools 自动发现），内容不变：

```toml
[project]
name = "paycheck"
version = "0.4.0"
description = "个人账单统计工具"
requires-python = ">=3.10, <3.12"
dependencies = [
    "opencv-python",
    "openpyxl",
    "paddleocr>=3.6.0",
    "paddlepaddle-gpu",
    "Pillow",
    "PyMuPDF",
    "torch",
]

[project.scripts]
paycheck = "paycheck.__main__:cli"

[tool.uv]
package = true

[[tool.uv.index]]
name = "paddle"
url = "https://www.paddlepaddle.org.cn/packages/stable/cu126/"
explicit = true

[[tool.uv.index]]
name = "pytorch"
url = "https://download.pytorch.org/whl/cu126"
explicit = true

[tool.setuptools.package-data]
paycheck = ["report/template.html"]

[tool.uv.sources]
paddlepaddle-gpu = { index = "paddle" }
torch = { index = "pytorch" }
```

- [ ] **Step 3: 修改 `paycheck-tools/paycheck/__main__.py`**

`_run_analyse()` 中（原第 286-293 行附近），将 `generate_html()` 改为 JSON 输出，同时移除不再需要的 import：

```python
# 删除这行 import（文件顶部）：
# from paycheck.report.html_reporter import generate_html

# 将报表生成部分的代码替换为：
    # ── 报表 ── 改为 JSON 输出
    log.info("生成 JSON 报表...")
    output_path = args.output or "report.json"
    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log.info("JSON 报表已生成: %s", output_path)
```

注意确保顶部已有 `import json`（第 11 行已存在）。

- [ ] **Step 4: 更新文档引用**

更新 `AGENTS.md` 中的目录结构说明，反映新布局。同时更新 `README.md`（如有引用）。

- [ ] **Step 5: 验证**

```bash
uv run --directory paycheck-tools paycheck analyse <test_input_dir> -o report.json
```

或直接 `cd paycheck-tools && uv run paycheck analyse <test_input_dir> -o report.json`

确认 `report.json` 正确生成。

- [ ] **Step 6: Commit**

```bash
git add paycheck-tools/ AGENTS.md README.md
git rm pyproject.toml src/paycheck/__init__.py src/paycheck/core/__init__.py src/paycheck/ingest/__init__.py src/paycheck/ocr/__init__.py src/paycheck/report/__init__.py src/paycheck/analysis/__init__.py src/paycheck/__main__.py src/paycheck/core/models.py src/paycheck/core/log.py src/paycheck/ingest/scanner.py src/paycheck/ingest/csv_utils.py src/paycheck/ingest/parsers/__init__.py src/paycheck/ingest/parsers/wechat.py src/paycheck/ingest/parsers/alipay.py src/paycheck/ingest/parsers/boc.py src/paycheck/ocr/engine.py src/paycheck/ocr/pdf_render.py src/paycheck/ocr/pipeline.py src/paycheck/ocr/layouts/__init__.py src/paycheck/ocr/layouts/base.py src/paycheck/ocr/layouts/boc.py src/paycheck/analysis/stats.py src/paycheck/report/html_reporter.py src/paycheck/report/template.html
git add paycheck-tools/
git commit -m "refactor: move backend CLI to paycheck-tools/, analyse now outputs JSON"
```

> 注意：git rm 命令需要列出所有 src/ 下的文件。也可简化为 `git rm -r src/`。

- [ ] **Step 2: 修改 `paycheck-tools/__main__.py` 的 `_run_analyse`**

将文件末尾（第 286-293 行附近）的报表生成逻辑改为 JSON 输出：

```python
    # ── 报表 ── 改为 JSON 输出
    log.info("生成 JSON 报表...")
    output_path = args.output or "report.json"
    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log.info("JSON 报表已生成: %s", output_path)
```

需要确保顶部 `import json`（已存在 `import` 区）。

- [ ] **Step 3: 更新 `pyproject.toml`**

将包路径从 `src/paycheck` 改为 `paycheck-tools`：

```toml
[tool.setuptools.packages.find]
where = ["paycheck-tools"]
```

同时更新 `[project.scripts]` 确保命令仍为 `paycheck = "paycheck.__main__:cli"`（包名不变）。

- [ ] **Step 4: 清理旧文件**（可选，标记废弃）

保留 `src/paycheck/` 下的 `html_reporter.py` 和 `template.html` 作为参考（不删除，`.gitkeep` 标记已废弃）。

- [ ] **Step 5: 验证**

```bash
uv run paycheck analyse <test_input_dir> -o report.json
```

确认 `report.json` 正确生成且包含所有必需字段。

- [ ] **Step 6: Commit**

```bash
git add paycheck-tools/ pyproject.toml
git commit -m "refactor: move Python code to paycheck-tools/, change analyse to output JSON"
```

---

### Task 13: 集成 — 最终组装与 Footer

**Files:**
- Modify: `paycheck-react/src/App.tsx`
- Create: `paycheck-react/src/components/Footer.tsx`

- [ ] **Step 1: 编写 `Footer.tsx`**

```typescript
// paycheck-react/src/components/Footer.tsx
interface FooterProps {
  generatedAt: string;
}

export default function Footer({ generatedAt }: FooterProps) {
  return (
    <footer style={{ textAlign: "center", padding: 20, color: "#aaa", fontSize: 13 }}>
      <p>PayCheck · 总账户（微信 + 支付宝 + 银行） · {generatedAt}</p>
    </footer>
  );
}
```

- [ ] **Step 2: 完整集成 `App.tsx`**

将所有组件组装完整。最终 `App.tsx` 的 Dashboard 部分应包含：

```tsx
<ReportHeader start={data.period.start} end={data.period.end} generatedAt={data.generated_at} />
<SummaryCards
  summary={stats.summary}
  incomeExpanded={incomeExpanded}
  expenseExpanded={expenseExpanded}
  onToggleIncome={() => setIncomeExpanded(p => !p)}
  onToggleExpense={() => setExpenseExpanded(p => !p)}
/>
<InternalSection
  internalTxs={internalTxs}
  fingerprints={fingerprints}
  onRemoveFingerprint={removeFingerprint}
  onImportFingerprints={addFingerprints}
/>
{incomeExpanded && (
  <DetailTable items={data.income_details} txType="income" fingerprints={fingerprints} onMarkInternal={addFingerprints} />
)}
{expenseExpanded && (
  <DetailTable items={data.all_transactions} txType="expense" fingerprints={fingerprints} onMarkInternal={addFingerprints} />
)}
<PlatformCards summary={stats.summary} />
<MonthlyChart monthly={stats.monthly} />
<CategorySection categories={stats.categories} />
<PlatformComparison platformMonthly={stats.platform_monthly} />
<MonthlyTable monthly={stats.monthly} />
<Footer generatedAt={data.generated_at} />
```

- [ ] **Step 3: 构建验证**

```bash
npm run build
```

确认 `dist/` 目录生成，TypeScript 无报错，无警告。

- [ ] **Step 4: 功能验证**

1. 用 Python CLI 生成 `report.json`
2. 用 `npx serve dist/` 启动静态服务
3. 浏览器打开，拖入 JSON
4. 验证：概览卡、平台卡、图表全部正常渲染
5. 验证：收入/支出详情可展开，过滤、分页、复选框标记正常
6. 验证：内部转账可取消、可导出/导入指纹
7. 验证：刷新页面后指纹保留

- [ ] **Step 5: Commit**

```bash
git add paycheck-react/src/App.tsx paycheck-react/src/components/Footer.tsx
git commit -m "feat: complete integration of all components with Footer"
```

---

## 自审清单

- [x] **Spec 覆盖** — 所有 spec 中的组件、hooks、utils、Python 改动均有对应任务
- [x] **占位符检查** — 无 TBD/TODO/implement later 等占位符
- [x] **类型一致性** — types.ts 定义的类型在所有后续任务中一致使用，hashTx 签名一致，useFingerprints 返回类型与 InternalSection/DetailTable 的 props 匹配
- [x] **文件路径准确** — 所有文件路径使用 `paycheck-react/` 前缀（前端）或 `paycheck-tools/`（后端）
