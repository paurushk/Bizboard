/** Backend collection_status values that block Complete (G-23 / auto credit hold). */
const HOLD_STATUSES = new Set(['stop_credit', 'overdue_severe']);

export function isCollectionHoldStatus(status?: string | null): boolean {
  const normalized = String(status ?? '')
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, '_');
  return HOLD_STATUSES.has(normalized);
}
