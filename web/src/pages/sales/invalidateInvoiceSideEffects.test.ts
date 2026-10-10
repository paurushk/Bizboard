import { QueryClient } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';
import { invalidateInvoiceSideEffects } from '@/pages/sales/invalidateInvoiceSideEffects';

describe('invalidateInvoiceSideEffects', () => {
  it('refreshes the invoice and every surface that reads it', () => {
    const qc = new QueryClient();
    const spy = vi.spyOn(qc, 'invalidateQueries');
    invalidateInvoiceSideEffects(qc, 4);
    const keys = spy.mock.calls.map((call) => (call[0] as { queryKey?: unknown[] }).queryKey);
    expect(keys).toContainEqual(['sales-invoices']);
    expect(keys).toContainEqual(['sales-invoice-payment-stats']);
    expect(keys).toContainEqual(['sales-invoice', 4]);
    expect(keys).toContainEqual(['customers']);
    expect(keys).toContainEqual(['dashboard']);
    expect(keys).toContainEqual(['stock-balance']);
    expect(keys).toContainEqual(['receipt-allocate-invoices']);
    expect(keys).toContainEqual(['payment-promises']);
    expect(keys).toContainEqual(['payment-links']);
    expect(keys).toContainEqual(['sales-returns']);
  });
});
