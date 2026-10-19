import type { QueryClient } from '@tanstack/react-query';

/**
 * SET-11b: the "last changed" time of the record a settings form opened, read from the cache at the
 * moment of saving. Several sections of one page write to the same company record, so each save
 * must send the newest time known (the previous section's save refreshed it), not the time the page
 * first loaded. `null` means "overwrite": the form asked to replace whatever is there.
 */
export function savedStamp(
  qc: QueryClient,
  queryKey: readonly unknown[],
  ctxExpected: string | null,
  fallback?: string | null,
): string | null {
  if (!ctxExpected) return null;
  const cached = qc.getQueryData<{ updatedAt?: string | null }>(queryKey);
  return cached?.updatedAt ?? fallback ?? null;
}
