import { QueryClient } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';
import { invalidateInvoiceSideEffects, invalidateSalesOrderSideEffects } from '@/pages/sales/invalidateInvoiceSideEffects';

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

describe('invalidateSalesOrderSideEffects', () => {
  it('refreshes orders, the open-orders picker, routes, customer views and stock', () => {
    const qc = new QueryClient();
    const spy = vi.spyOn(qc, 'invalidateQueries');
    invalidateSalesOrderSideEffects(qc, 9, 3);
    const keys = spy.mock.calls.map((call) => (call[0] as { queryKey?: unknown[] }).queryKey);
    for (const key of [
      ['sales-orders'],
      ['sales-orders-open'],
      ['sales-order-stock'],
      ['sales-order', 9],
      ['delivery-routes'],
      ['route-combine'],
      ['customer-360'],
      ['customers'],
      ['customer', 3],
      ['dashboard'],
      ['attention-rows'],
      ['stock-balance'],
      ['stock'],
      ['products'],
    ]) {
      expect(keys).toContainEqual(key);
    }
  });
});
