import { useState, useEffect, useCallback } from "react";

/**
 * Hook to persist and sanitize an ordered array of indices in localStorage.
 * Keeps entries unique, in-range and appends any missing indices so UI always
 * renders all items in a stable order.
 *
 * @param {string} key - localStorage key
 * @param {number} length - expected length (number of items)
 * @returns {[number[], Function]} [order, setOrder]
 */
export function usePersistentOrder(key, length) {
  const makeDefault = useCallback(
    (len) => Array.from({ length: Math.max(0, len) }, (_, i) => i),
    [],
  );

  const sanitize = useCallback((arr, len) => {
    const max = Math.max(0, len);
    const seen = new Set();
    const result = [];

    if (Array.isArray(arr)) {
      for (const v of arr) {
        if (typeof v === "number" && v >= 0 && v < max && !seen.has(v)) {
          result.push(v);
          seen.add(v);
        }
      }
    }
    for (let i = 0; i < max; i++) {
      if (!seen.has(i)) result.push(i);
    }

    return result;
  }, []);

  const readInitial = useCallback(() => {
    try {
      const raw = globalThis.window?.localStorage?.getItem(key);
      if (!raw) return makeDefault(length);
      const parsed = JSON.parse(raw);
      return sanitize(parsed, length);
    } catch (e) {
      return makeDefault(length);
    }
  }, [key, length, makeDefault, sanitize]);

  const [order, setOrderState] = useState(readInitial);

  useEffect(() => {
    const cleaned = sanitize(order, length);
    try {
      const asString = JSON.stringify(cleaned);
      const existing = globalThis.window?.localStorage?.getItem(key);
      if (existing !== asString) {
        globalThis.window?.localStorage?.setItem(key, asString);
      }
    } catch (e) {
      // ignore persistent failures
    }

    if (JSON.stringify(cleaned) !== JSON.stringify(order)) {
      setOrderState(cleaned);
    }
  }, [key, length, order, sanitize]);

  const setOrder = useCallback(
    (next) => {
      try {
        const resolved = typeof next === "function" ? next(order) : next;
        const cleaned = sanitize(resolved, length);
        globalThis.window?.localStorage?.setItem(key, JSON.stringify(cleaned));
        setOrderState(cleaned);
      } catch (e) {
        // ignore failures
      }
    },
    [key, length, order, sanitize],
  );

  return [order, setOrder];
}
