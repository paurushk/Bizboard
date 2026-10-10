import type { QueryClient } from '@tanstack/react-query';

/** Refresh every surface that reads an invoice after it is posted, paid, or cancelled. */
export function invalidateInvoiceSideEffects(qc: QueryClient, invoiceId?: number): void {
  void qc.invalidateQueries({ queryKey: ['sales-invoices'] });
  void qc.invalidateQueries({ queryKey: ['sales-invoice-payment-stats'] });
  if (invoiceId != null) {
    void qc.invalidateQueries({ queryKey: ['sales-invoice', invoiceId] });
  }
  void qc.invalidateQueries({ queryKey: ['customers'] });
  void qc.invalidateQueries({ queryKey: ['customer'] });
  void qc.invalidateQueries({ queryKey: ['customer-360'] });
  void qc.invalidateQueries({ queryKey: ['dashboard'] });
  void qc.invalidateQueries({ queryKey: ['products'] });
  void qc.invalidateQueries({ queryKey: ['stock-balance'] });
  void qc.invalidateQueries({ queryKey: ['stock'] });
  void qc.invalidateQueries({ queryKey: ['receipts'] });
  void qc.invalidateQueries({ queryKey: ['sales-invoices-open'] });
  void qc.invalidateQueries({ queryKey: ['receipt-allocate-invoices'] });
  void qc.invalidateQueries({ queryKey: ['sales-returns'] });
  void qc.invalidateQueries({ queryKey: ['sales-credit-notes'] });
  void qc.invalidateQueries({ queryKey: ['payment-promises'] });
  void qc.invalidateQueries({ queryKey: ['payment-links'] });
  void qc.invalidateQueries({ queryKey: ['attention-rows'] });
  void qc.invalidateQueries({ queryKey: ['payment-health'] });
  void qc.invalidateQueries({ queryKey: ['journals'] });
}
