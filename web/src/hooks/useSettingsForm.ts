import { useCallback, useRef, useState } from 'react';
import axios from 'axios';
import { idempotencyHeaders, newIdempotencyKey } from '@/api/client';

export type SettingsSaveContext = {
  /** Send as the request headers so a double-click or retry is applied once (Idempotency-Key). */
  headers: Record<string, string>;
  /** `updated_at` of the record this edit started from; null when unknown or when overwriting. */
  expectedUpdatedAt: string | null;
};

export type SettingsForm<TValues extends object, TResult> = {
  values: TValues;
  setValues: (next: TValues | ((prev: TValues) => TValues)) => void;
  dirty: boolean;
  saving: boolean;
  savedAt: number | null;
  error: unknown;
  /** Set after the server answered 409: the record changed since this edit began. */
  conflict: { latest?: unknown } | null;
  save: () => Promise<TResult | undefined>;
  discard: () => void;
  /** Replace the baseline with fresh server data (after a load, reload or conflict reload). */
  load: (values: TValues, updatedAt?: string | null) => void;
  resolveConflict: (choice: 'reload' | 'overwrite') => Promise<void>;
  dismissConflict: () => void;
};

/**
 * SET-11: dirty tracking, one idempotency key per save gesture, and optimistic-lock conflict
 * handling for a settings form. The backend half is SET-11b (a 409 when `updated_at` is stale).
 * Pages pass `save`, which performs the request using the context it is given, and `refetch`,
 * which returns the latest server values for a "reload" after a conflict.
 */
export function useSettingsForm<TValues extends object, TResult extends { updatedAt?: string | null }>({
  initial,
  initialUpdatedAt = null,
  save: doSave,
  refetch,
  onSaved,
}: {
  initial: TValues;
  initialUpdatedAt?: string | null;
  save: (values: TValues, ctx: SettingsSaveContext) => Promise<TResult>;
  refetch?: () => Promise<{ values: TValues; updatedAt?: string | null }>;
  onSaved?: (result: TResult) => void;
}): SettingsForm<TValues, TResult> {
  const [values, setValuesState] = useState<TValues>(initial);
  const [baseline, setBaseline] = useState(() => JSON.stringify(initial));
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [conflict, setConflict] = useState<{ latest?: unknown } | null>(null);
  const updatedAtRef = useRef<string | null>(initialUpdatedAt);
  // One key per save gesture. Kept across a retry after a dropped connection, replaced once the
  // server has answered, so the next edit is a new operation.
  const keyRef = useRef<string>(newIdempotencyKey());
  const inFlightRef = useRef(false);

  const dirty = JSON.stringify(values) !== baseline;

  const setValues = useCallback((next: TValues | ((prev: TValues) => TValues)) => {
    setValuesState((prev) => (typeof next === 'function' ? (next as (p: TValues) => TValues)(prev) : next));
  }, []);

  const load = useCallback((next: TValues, updatedAt: string | null = null) => {
    setValuesState(next);
    setBaseline(JSON.stringify(next));
    updatedAtRef.current = updatedAt;
    keyRef.current = newIdempotencyKey();
    setError(null);
  }, []);

  const run = useCallback(
    async (overwrite: boolean): Promise<TResult | undefined> => {
      if (inFlightRef.current) return undefined;
      inFlightRef.current = true;
      setSaving(true);
      setError(null);
      try {
        const result = await doSave(values, {
          headers: idempotencyHeaders(keyRef.current),
          expectedUpdatedAt: overwrite ? null : updatedAtRef.current,
        });
        setBaseline(JSON.stringify(values));
        updatedAtRef.current = result.updatedAt ?? updatedAtRef.current;
        keyRef.current = newIdempotencyKey();
        setSavedAt(Date.now());
        onSaved?.(result);
        return result;
      } catch (e) {
        if (axios.isAxiosError(e) && e.response?.status === 409) {
          setConflict({ latest: e.response.data });
          keyRef.current = newIdempotencyKey();
        } else {
          setError(e);
          if (axios.isAxiosError(e) && e.response) keyRef.current = newIdempotencyKey();
        }
        return undefined;
      } finally {
        inFlightRef.current = false;
        setSaving(false);
      }
    },
    [doSave, onSaved, values],
  );

  const resolveConflict = useCallback(
    async (choice: 'reload' | 'overwrite') => {
      setConflict(null);
      if (choice === 'overwrite') {
        await run(true);
        return;
      }
      if (refetch) {
        const latest = await refetch();
        load(latest.values, latest.updatedAt ?? null);
      }
    },
    [load, refetch, run],
  );

  return {
    values,
    setValues,
    dirty,
    saving,
    savedAt,
    error,
    conflict,
    save: () => run(false),
    discard: () => setValuesState(JSON.parse(baseline) as TValues),
    load,
    resolveConflict,
    dismissConflict: () => setConflict(null),
  };
}
