import { useEffect, useState } from 'react';
import { getErrorMessage } from '@/api/client';
import { previewPurchaseTotals, previewSalesTotals, type PreviewTotals } from '@/api/resources';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';

export type { PreviewTotals };

export function usePreviewTotals(
  kind: 'sales' | 'purchase',
  body: Record<string, unknown> | null,
): {
  totals: PreviewTotals | null;
  error: string | null;
  pending: boolean;
  ready: boolean;
} {
  const serialized = body ? JSON.stringify(body) : '';
  const debounced = useDebouncedValue(serialized, 280);
  const [totals, setTotals] = useState<PreviewTotals | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [readyKey, setReadyKey] = useState('');

  useEffect(() => {
    if (!debounced) {
      setTotals(null);
      setError(null);
      setPending(false);
      setReadyKey('');
      return;
    }
    let cancelled = false;
    setPending(true);
    setError(null);
    const parsed = JSON.parse(debounced) as Record<string, unknown>;
    const run = kind === 'purchase' ? previewPurchaseTotals : previewSalesTotals;
    void run(parsed)
      .then((next) => {
        if (cancelled) return;
        setTotals(next);
        setReadyKey(debounced);
        setPending(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setTotals(null);
        setReadyKey('');
        setError(getErrorMessage(err));
        setPending(false);
      });
    return () => {
      cancelled = true;
    };
  }, [debounced, kind]);

  const ready = Boolean(debounced) && readyKey === debounced && !error && totals != null;
  return { totals, error, pending, ready };
}
