import type { QueryClient } from '@tanstack/react-query';

/** Everything a completed/cancelled credit or debit note can change (CN-12 / DN-11). */
export function invalidateNoteQueries(qc: QueryClient, kind: 'credit' | 'debit') {
  const keys: unknown[][] = [
    [kind === 'credit' ? 'sales-credit-notes' : 'sales-debit-notes'],
    ['sales-invoices'],
    ['sales-invoice'],
    ['sales-invoices-open'],
    ['sales-invoice-payment-stats'],
    ['invoice-allocations'],
    ['customer'],
    ['customers'],
    ['customer-360'],
    ['customer-history'],
    ['customer-ledger-tabs'],
    ['receipts'],
    ['receipts-summary'],
    ['note-source-invoices'],
    ['invoice-notes'],
  ];
  for (const queryKey of keys) void qc.invalidateQueries({ queryKey });
}

/** Purchase-side twin: what a completed/cancelled purchase credit or debit note can change. */
export function invalidatePurchaseNoteQueries(qc: QueryClient, kind: 'credit' | 'debit') {
  const keys: unknown[][] = [
    [kind === 'credit' ? 'purchase-credit-notes' : 'purchase-debit-notes'],
    ['purchases'],
    ['purchase-invoice'],
    ['suppliers'],
    ['supplier'],
    ['supplier-ledger'],
    ['supplier-payments'],
    ['stock'],
    // Same surfaces a purchase bill refreshes: the note moves payables, the dashboard and the books.
    ['dashboard'],
    ['attention-rows'],
    ['journals'],
  ];
  for (const queryKey of keys) void qc.invalidateQueries({ queryKey });
}
