import { useCallback, useEffect, useState } from 'react';
import { dateRangeForPreset, type DateRangePresetId } from '@/components/HistoryFilterBar';

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

interface StoredRange {
  dateFrom: string;
  dateTo: string;
}

function storageKeyFor(key: string): string {
  return `bb.reportPeriod.${key}`;
}

function readStored(key: string): StoredRange | null {
  try {
    const raw = window.localStorage.getItem(storageKeyFor(key));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<StoredRange>;
    if (typeof parsed.dateFrom !== 'string' || typeof parsed.dateTo !== 'string') return null;
    if (!ISO_DATE.test(parsed.dateFrom) || !ISO_DATE.test(parsed.dateTo)) return null;
    if (parsed.dateFrom > parsed.dateTo) return null;
    return { dateFrom: parsed.dateFrom, dateTo: parsed.dateTo };
  } catch {
    return null;
  }
}

function writeStored(key: string, range: StoredRange): void {
  try {
    window.localStorage.setItem(storageKeyFor(key), JSON.stringify(range));
  } catch {
    // Private windows and blocked storage are fine: the choice just is not remembered.
  }
}

/**
 * RPT-06: the date range a report opens on. It starts on a bounded preset (never "everything"),
 * remembers the last valid choice per report in this browser, and tells the page when the range
 * is back to front so the page can stop asking the server and explain why.
 */
export function useReportPeriod(key: string, defaultPreset: DateRangePresetId) {
  const [range, setRangeState] = useState<StoredRange>(() => readStored(key) ?? dateRangeForPreset(defaultPreset));
  const { dateFrom, dateTo } = range;
  const invalid = Boolean(dateFrom && dateTo && dateFrom > dateTo);

  useEffect(() => {
    if (!invalid && ISO_DATE.test(dateFrom) && ISO_DATE.test(dateTo)) writeStored(key, { dateFrom, dateTo });
  }, [key, dateFrom, dateTo, invalid]);

  const setDateFrom = useCallback((value: string) => setRangeState((r) => ({ ...r, dateFrom: value })), []);
  const setDateTo = useCallback((value: string) => setRangeState((r) => ({ ...r, dateTo: value })), []);
  const setRange = useCallback((next: StoredRange) => setRangeState(next), []);

  return { dateFrom, dateTo, setDateFrom, setDateTo, setRange, invalid };
}
