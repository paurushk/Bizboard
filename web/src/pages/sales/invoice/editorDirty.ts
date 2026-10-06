import { useState } from 'react';

export function jsonSnapshot(value: unknown): string {
  return JSON.stringify(value);
}

export function snapshotDirty(current: string, baseline: string | null): boolean {
  return baseline !== null && current !== baseline;
}

/**
 * Treat `snapshot` as clean once `ready` is true (after mount, and after an
 * existing bill has loaded). Call `rearm()` in the same turn as a state update
 * that should become the new baseline, such as restoring a device draft.
 *
 * A rearm that does not change the snapshot must not swallow the next edit.
 * Dropping `ready` (switching from a new bill to an existing one) discards the
 * previous baseline so the loaded bill is not immediately dirty.
 */
export function useEditorBaseline(snapshot: string, ready: boolean) {
  // Baseline and "armed" are state, adjusted during render (React's supported
  // derive-from-props pattern), so the dirty flag never reads a ref in render
  // and no effect has to set state.
  const [baseline, setBaseline] = useState<string | null>(null);
  const [armed, setArmed] = useState(true);

  if (!ready) {
    if (baseline !== null) setBaseline(null);
    if (!armed) setArmed(true);
  } else if (armed) {
    setArmed(false);
    setBaseline(snapshot);
  }

  return {
    dirty: snapshotDirty(snapshot, baseline),
    rearm: () => setArmed(true),
  };
}
