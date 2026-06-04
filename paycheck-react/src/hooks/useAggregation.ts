// paycheck-react/src/hooks/useAggregation.ts
import { useMemo } from "react";
import type { AggregatedData, Transaction } from "../types";
import { hashTx } from "../utils/hash";
import { aggregate, type AggregationResult } from "../utils/aggregation";

export function useAggregation(
  data: AggregatedData | null,
  fingerprints: Set<string>
): {
  externalTxs: Transaction[];
  internalTxs: Transaction[];
  stats: AggregationResult | null;
  incomeTxs: Transaction[];
} {
  return useMemo(() => {
    if (!data) return { externalTxs: [], internalTxs: [], stats: null, incomeTxs: [] };

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

    const incomeTxs = (data.income_details || []).filter(
      (t) => !fingerprints.has(hashTx(t))
    );

    const stats = aggregate(externalTxs);

    return { externalTxs, internalTxs, stats, incomeTxs };
  }, [data, fingerprints]);
}
