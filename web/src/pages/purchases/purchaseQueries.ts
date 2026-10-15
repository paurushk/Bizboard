import type { QueryClient } from '@tanstack/react-query';

/**
 * Refresh every surface that reads a purchase bill after it is created, edited,
 * completed, paid or cancelled. Mirrors sales/invalidateInvoiceSideEffects.
 *
 * `stock` is true when the change posts or reverses stock (complete, cancel,
 * goods-receipt complete); a plain draft save does not need the stock views.
 */
export function invalidatePurchaseSideEffects(
  qc: QueryClient,
  opts: { invoiceId?: number; stock?: boolean } = {},
): void {
  void qc.invalidateQueries({ queryKey: ['purchases'] });
  if (opts.invoiceId != null) {
    void qc.invalidateQueries({ queryKey: ['purchase-invoice', opts.invoiceId] });
  }
  void qc.invalidateQueries({ queryKey: ['purchase-invoice-number-series'] });
  void qc.invalidateQueries({ queryKey: ['suppliers'] });
  void qc.invalidateQueries({ queryKey: ['supplier'] });
  void qc.invalidateQueries({ queryKey: ['supplier-payments'] });
  void qc.invalidateQueries({ queryKey: ['dashboard'] });
  void qc.invalidateQueries({ queryKey: ['attention-rows'] });
  void qc.invalidateQueries({ queryKey: ['journals'] });
  if (opts.stock) {
    void qc.invalidateQueries({ queryKey: ['products'] });
    void qc.invalidateQueries({ queryKey: ['stock-balance'] });
    void qc.invalidateQueries({ queryKey: ['stock'] });
    void qc.invalidateQueries({ queryKey: ['low-stock'] });
  }
}
