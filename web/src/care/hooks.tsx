import { useCallback, useState } from 'react';
import Alert from '@mui/material/Alert';
import axios from 'axios';
import { useLocation, useSearchParams } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';

/** Filters held in the address bar so Back, refresh and shared links all keep them. */
export function useUrlFilters<T extends Record<string, string>>(defaults: T) {
  const [params, setParams] = useSearchParams();
  const values: Record<string, string> = {};
  for (const key of Object.keys(defaults)) values[key] = params.get(key) ?? defaults[key];
  const set = (patch: Partial<T>) => {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        for (const [key, value] of Object.entries(patch)) {
          if (value == null || value === '' || value === defaults[key]) next.delete(key);
          else next.set(key, String(value));
        }
        // A new filter starts again at page 1.
        if (!('page' in patch)) next.delete('page');
        return next;
      },
      { replace: true },
    );
  };
  return { values: values as T, set };
}

/** Path of the list with its current filters, for "back" links and row links (FND-02). */
export function useListPath(base: string) {
  const { search } = useLocation();
  return useCallback((suffix = '') => ({ pathname: `${base}${suffix}`, search }), [base, search]);
}

// ---- feedback beside the action (FND-05) -------------------------------------------------------------------------------

type Notice = { kind: 'success' | 'error'; text: string } | null;

export type ConflictInfo = { code: string; message: string; extra: Record<string, unknown> } | null;

/** The structured part of a 409/400 answer, for flows that ask "do you want to go ahead anyway?". */
export function conflictInfo(error: unknown): ConflictInfo {
  if (!axios.isAxiosError(error) || error.response?.status !== 409) return null;
  const body = error.response.data as { error?: { details?: Record<string, unknown> } } | undefined;
  const details = body?.error?.details;
  if (!details || typeof details.code !== 'string') return null;
  return { code: details.code, message: String(details.message ?? ''), extra: details };
}

/** Success and failure messages shown next to the thing that was done, never at the top of a long page. */
export function useNotice() {
  const [notice, setNotice] = useState<Notice>(null);
  const ok = useCallback((text: string) => setNotice({ kind: 'success', text }), []);
  const fail = useCallback((error: unknown) => {
    const text = getErrorMessage(error);
    setNotice(text ? { kind: 'error', text } : null);
  }, []);
  const clear = useCallback(() => setNotice(null), []);
  const node = notice ? (
    <Alert
      severity={notice.kind}
      role={notice.kind === 'error' ? 'alert' : 'status'}
      onClose={clear}
      sx={{ alignItems: 'center' }}
    >
      {notice.text}
    </Alert>
  ) : null;
  return { notice, ok, fail, clear, node };
}


/** Whether this person may change records here (a viewer reads only). */
export function canChangeCare(user: { role?: string; canCreateSales?: boolean; canCreatePurchases?: boolean } | null, kind: 'sales' | 'purchases' = 'sales'): boolean {
  if (!user || user.role === 'VIEWER') return false;
  if (user.role === 'OWNER') return true;
  return kind === 'purchases' ? user.canCreatePurchases === true : user.canCreateSales === true;
}
