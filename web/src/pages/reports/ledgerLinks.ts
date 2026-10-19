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

type RegisterRow = Record<string, unknown>;

/** Where a sales or purchase register row lives: the invoice, or the credit or debit note it is. */
export function registerRowPath(kind: 'sales' | 'purchases', row: RegisterRow): string | null {
  const id = row.id;
  if (typeof id !== 'number' && typeof id !== 'string') return null;
  const docType = String(row.doc_type ?? row.docType ?? '');
  const base = kind === 'sales' ? '/sales' : '/purchases';
  if (docType.endsWith('CREDIT_NOTE')) return `${base}/credit-notes/${id}`;
  if (docType.endsWith('DEBIT_NOTE')) return `${base}/debit-notes/${id}`;
  return `${base}/history/${id}`;
}

/** The ledger lines behind one trial balance row: the Day Book for that account over the year to the as-of date. */
export function trialBalanceRowPath(accountId: unknown, from: string, to: string): string | null {
  if (typeof accountId !== 'number' && typeof accountId !== 'string') return null;
  return `/reports/day-book?account=${accountId}&from=${from}&to=${to}`;
}

/** The receipt or supplier payment behind a Cash Book row. Receipts open on their number; payments on that supplier. */
export function cashBookRowPath(row: RegisterRow): string | null {
  const type = String(row.type ?? '');
  if (type === 'RECEIPT') {
    const number = typeof row.number === 'string' ? row.number : '';
    return number ? `/sales/receipts?q=${encodeURIComponent(number)}` : null;
  }
  if (type === 'SUPPLIER_PAYMENT') {
    const id = row.party_id ?? row.partyId;
    return typeof id === 'number' || typeof id === 'string' ? `/purchases/payments?supplier=${id}` : '/purchases/payments';
  }
  return null;
}

/** The invoice a rate back-scan row is about. */
export function rateScanRowPath(row: RegisterRow): string | null {
  const id = row.invoiceId ?? row.invoice_id;
  return typeof id === 'number' || typeof id === 'string' ? `/sales/history/${id}` : null;
}
