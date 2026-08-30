import { useCallback, useEffect, useMemo, useState } from 'react';

export type ColumnSpec = {
  id: string;
  label: string;
  group: 'standard' | 'custom';
  removable?: boolean;
};

type StoredPrefs = { hidden: string[] };

function storageKey(companyId: number | string, userId: number | string, tableId: string) {
  return `bb:cols:${companyId}:${userId}:${tableId}`;
}

function readPrefs(key: string): StoredPrefs | null {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredPrefs;
    if (!parsed || !Array.isArray(parsed.hidden)) return null;
    return { hidden: parsed.hidden.map(String) };
  } catch {
    return null;
  }
}

function writePrefs(key: string, prefs: StoredPrefs) {
  try {
    localStorage.setItem(key, JSON.stringify(prefs));
  } catch {
    // ignore quota / private-mode failures
  }
}

export function useColumnPrefs(
  tableId: string,
  allColumns: ColumnSpec[],
  companyId?: number | string | null,
  userId?: number | string | null,
) {
  const key = companyId && userId ? storageKey(companyId, userId, tableId) : '';
  const [hidden, setHidden] = useState<string[]>(() => (key ? readPrefs(key)?.hidden ?? [] : []));

  useEffect(() => {
    setHidden(key ? readPrefs(key)?.hidden ?? [] : []);
  }, [key]);

  const visibleIds = useMemo(() => {
    const hide = new Set(hidden);
    return allColumns.filter((col) => !hide.has(col.id) || col.removable === false).map((col) => col.id);
  }, [allColumns, hidden]);

  const isVisible = useCallback((id: string) => visibleIds.includes(id), [visibleIds]);

  const toggle = useCallback(
    (id: string) => {
      const column = allColumns.find((col) => col.id === id);
      if (column?.removable === false) return;
      setHidden((current) => {
        const next = current.includes(id) ? current.filter((item) => item !== id) : [...current, id];
        if (key) writePrefs(key, { hidden: next });
        return next;
      });
    },
    [allColumns, key],
  );

  const reset = useCallback(() => {
    setHidden([]);
    if (key) writePrefs(key, { hidden: [] });
  }, [key]);

  return { visibleIds, isVisible, toggle, reset, hidden };
}
