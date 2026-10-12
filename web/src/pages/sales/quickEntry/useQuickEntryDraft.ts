import { useCallback, useEffect, useState } from 'react';
import { readDraft, removeDraft, writeDraft } from '@/lib/deviceDraft';
import type { QuickMode } from './types';

export interface QuickEntryDraft {
  customerId: number | null;
  customerName: string;
  mode: QuickMode;
  note: string;
  shipToId?: number | null;
  lines: Array<{ productId: number; quantity: number }>;
}

/**
 * Keeps an in-progress order across a reload, app switch or the browser killing the tab (QOE-14).
 * Prices are never stored. Offline queued submission is out of scope; this only prevents data loss.
 */
export function useQuickEntryDraft(companyId: number, userId: number, current: QuickEntryDraft | null) {
  const [resumable, setResumable] = useState<QuickEntryDraft | null>(null);
  const [seenKey, setSeenKey] = useState('');

  // Look for a saved draft once per company+user (adjusting state during render, not in an effect).
  const key = `${companyId}:${userId}`;
  if (seenKey !== key) {
    setSeenKey(key);
    if (companyId && userId) {
      const found = readDraft<QuickEntryDraft>(companyId, userId, 'quick-entry');
      setResumable(found.ok && found.payload?.lines?.length ? found.payload : null);
    } else {
      setResumable(null);
    }
  }

  useEffect(() => {
    if (!companyId || !userId || resumable) return undefined;
    const timer = window.setTimeout(() => {
      if (current && current.lines.length > 0) writeDraft(companyId, userId, 'quick-entry', current);
      else removeDraft(companyId, userId, 'quick-entry');
    }, 400);
    return () => window.clearTimeout(timer);
  }, [companyId, userId, current, resumable]);

  const clear = useCallback(() => {
    if (companyId && userId) removeDraft(companyId, userId, 'quick-entry');
    setResumable(null);
  }, [companyId, userId]);

  return { resumable, clear };
}
