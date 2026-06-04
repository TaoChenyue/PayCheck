// paycheck-react/src/utils/hash.ts
import type { Transaction } from "../types";

function simpleHash(str: string): string {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = (hash << 5) - hash + char;
    hash = hash & hash;
  }
  return Math.abs(hash).toString(16).padStart(8, "0");
}

export function hashTx(tx: Transaction): string {
  const raw = [
    tx.platform,
    tx.time,
    String(tx.amount),
    tx.counterparty,
    tx.description,
  ].join("|");
  return simpleHash(raw);
}
