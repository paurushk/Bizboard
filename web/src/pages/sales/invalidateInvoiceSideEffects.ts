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
  void qc.invalidateQueries({ queryKey: ['receipts-summary'] });
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

/** Refresh every surface that reads a sales order after Quick Entry (or the editor) creates or confirms one. */
export function invalidateSalesOrderSideEffects(qc: QueryClient, orderId?: number, customerId?: number): void {
  void qc.invalidateQueries({ queryKey: ['sales-orders'] });
  void qc.invalidateQueries({ queryKey: ['sales-orders-open'] });
  void qc.invalidateQueries({ queryKey: ['sales-order-stock'] });
  if (orderId != null) void qc.invalidateQueries({ queryKey: ['sales-order', orderId] });
  void qc.invalidateQueries({ queryKey: ['delivery-routes'] });
  void qc.invalidateQueries({ queryKey: ['route-combine'] });
  void qc.invalidateQueries({ queryKey: ['customer-360'] });
  void qc.invalidateQueries({ queryKey: ['customers'] });
  void qc.invalidateQueries({ queryKey: customerId != null ? ['customer', customerId] : ['customer'] });
  void qc.invalidateQueries({ queryKey: ['dashboard'] });
  void qc.invalidateQueries({ queryKey: ['attention-rows'] });
  void qc.invalidateQueries({ queryKey: ['stock-balance'] });
  void qc.invalidateQueries({ queryKey: ['stock'] });
  void qc.invalidateQueries({ queryKey: ['products'] });
}
