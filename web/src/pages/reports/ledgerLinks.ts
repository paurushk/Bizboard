import type { LedgerEntry } from '@/types/domain';

/** Where a ledger row's document lives; null when the app has no page for it. */
export function ledgerEntryPath(entry: LedgerEntry, supplierId?: number): string | null {
  const id = entry.sourceId ?? entry.referenceId;
  if (id == null) return null;
  switch (entry.type) {
    case 'PURCHASE_INVOICE':
      return `/purchases/history/${id}`;
    case 'PURCHASE_CREDIT_NOTE':
      return `/purchases/credit-notes/${id}`;
    case 'PURCHASE_DEBIT_NOTE':
      return `/purchases/debit-notes/${id}`;
    case 'PURCHASE_RETURN':
      return '/purchases/returns';
    case 'PAYMENT':
    case 'SUPPLIER_PAYMENT':
      return supplierId != null ? `/purchases/payments?supplier=${supplierId}` : '/purchases/payments';
    default:
      return null;
  }
}
