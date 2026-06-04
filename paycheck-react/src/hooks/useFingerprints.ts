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
  } catch {
    // ignore
  }
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

  return { fingerprints, addFingerprint, addFingerprints, removeFingerprint };
}
