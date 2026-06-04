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
