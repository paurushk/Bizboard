import type { QueryClient } from '@tanstack/react-query';

/**
 * Every cached view of a customer. Call after any change to a customer master row so the invoice,
 * receipt, POS and 360° screens do not keep serving the old state, GSTIN or credit terms.
 */
export function invalidateCustomerQueries(qc: QueryClient, id?: number | string) {
  for (const key of [
    'customers',
    'customers-summary',
    'customers-search',
    'customers-receipt-lookup',
    'customers-reassign-lookup',
    'customers-mini',
  ]) {
    void qc.invalidateQueries({ queryKey: [key] });
  }
  if (id != null) {
    void qc.invalidateQueries({ queryKey: ['customer', id] });
    void qc.invalidateQueries({ queryKey: ['customer', String(id)] });
    void qc.invalidateQueries({ queryKey: ['customer-360', id] });
    void qc.invalidateQueries({ queryKey: ['customer-360', String(id)] });
    void qc.invalidateQueries({ queryKey: ['customer-history', id] });
  } else {
    void qc.invalidateQueries({ queryKey: ['customer'] });
    void qc.invalidateQueries({ queryKey: ['customer-360'] });
  }
}
