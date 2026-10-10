import { todayIso } from '@/components/billing';
import type { Quotation } from '@/types/domain';

export const OPEN_QUOTATION_STATUSES: string[] = ['DRAFT', 'SENT', 'ACCEPTED'];

/** The server's date decides when it sends `isExpired`; the browser date is only the fallback. */
export function isQuotationExpired(q: Pick<Quotation, 'status' | 'isExpired' | 'validUntil'>): boolean {
  if (!OPEN_QUOTATION_STATUSES.includes(q.status)) return false;
  if (q.isExpired != null) return q.isExpired;
  return Boolean(q.validUntil && q.validUntil < todayIso());
}
