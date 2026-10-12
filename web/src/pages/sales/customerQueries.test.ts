import { QueryClient } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';
import { invalidateCustomerQueries } from '@/pages/sales/customerQueries';

function keysInvalidated(id?: number | string) {
  const qc = new QueryClient();
  const spy = vi.spyOn(qc, 'invalidateQueries');
  invalidateCustomerQueries(qc, id);
  return spy.mock.calls.map(([filters]) => JSON.stringify((filters as { queryKey: unknown[] }).queryKey));
}

describe('invalidateCustomerQueries', () => {
  it('refreshes every list, picker and summary that shows customers', () => {
    const keys = keysInvalidated();
    for (const key of [
      'customers',
      'customers-summary',
      'customers-search',
      'customers-receipt-lookup',
      'customers-reassign-lookup',
      'customers-mini',
    ]) {
      expect(keys, key).toContain(JSON.stringify([key]));
    }
  });

  it('refreshes one customer everywhere it is cached, as a number or a route string', () => {
    const keys = keysInvalidated(12);
    for (const expected of [
      ['customer', 12],
      ['customer', '12'],
      ['customer-360', 12],
      ['customer-360', '12'],
      ['customer-history', 12],
    ]) {
      expect(keys).toContain(JSON.stringify(expected));
    }
  });

  it('without an id refreshes all customer and snapshot caches', () => {
    const keys = keysInvalidated();
    expect(keys).toContain(JSON.stringify(['customer']));
    expect(keys).toContain(JSON.stringify(['customer-360']));
  });
});
