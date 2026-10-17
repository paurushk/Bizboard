import type { QueryClient } from '@tanstack/react-query';

/**
 * Everything the Money hub (or a screen it links to) shows that a money action can change.
 * Invalidating only marks a query stale and refetches it if it is on screen, so this costs
 * nothing on pages that do not use these keys.
 */
export const MONEY_QUERY_KEYS: ReadonlyArray<readonly string[]> = [
  ['money-position'],
  ['money-timeline'],
  ['money-statutory'],
  ['supplier-payments-summary'],
  ['dashboard'],
  ['collections-open-invoices'],
  ['collections-worklist'],
  ['payment-promises'],
];

export function invalidateMoney(qc: QueryClient): void {
  for (const queryKey of MONEY_QUERY_KEYS) {
    void qc.invalidateQueries({ queryKey: [...queryKey] });
  }
}
