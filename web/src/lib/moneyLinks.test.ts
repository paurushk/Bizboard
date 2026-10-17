import { QueryClient } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';
import { MONEY_QUERY_KEYS, invalidateMoney } from '@/lib/moneyInvalidate';
import { moneyHref, moneyLinkHref } from '@/lib/moneyLinks';

describe('moneyHref', () => {
  it('adds the via flag the target page uses to offer the way back', () => {
    expect(moneyHref('/sales/receipts', { advance: '1' })).toBe('/sales/receipts?advance=1&via=money');
    expect(moneyHref('/payments/links')).toBe('/payments/links?via=money');
  });

  it('keeps snake_case filter names, which the API sends as text', () => {
    expect(moneyLinkHref({ route: '/purchases/payments', query: 'cheque_status=PENDING_CLEARANCE&supplier=4' })).toBe(
      '/purchases/payments?cheque_status=PENDING_CLEARANCE&supplier=4&via=money',
    );
  });

  it('encodes values that need it', () => {
    expect(moneyLinkHref({ route: '/sales/receipts', query: 'q=RCT%2F0001' })).toBe(
      '/sales/receipts?q=RCT%2F0001&via=money',
    );
  });
});

describe('invalidateMoney', () => {
  it('marks every money query stale so the hub and the screens that foot to it refetch', () => {
    const qc = new QueryClient();
    const spy = vi.spyOn(qc, 'invalidateQueries');
    invalidateMoney(qc);
    const keys = spy.mock.calls.map((call) => (call[0] as { queryKey: string[] }).queryKey[0]);
    for (const expected of [
      'money-position',
      'money-timeline',
      'money-statutory',
      'supplier-payments-summary',
      'dashboard',
      'collections-open-invoices',
      'payment-promises',
    ]) {
      expect(keys).toContain(expected);
    }
    expect(keys).toHaveLength(MONEY_QUERY_KEYS.length);
  });

  it('makes an already-loaded hub query stale after any write', async () => {
    const qc = new QueryClient();
    const query = qc.getQueryCache().build(qc, { queryKey: ['money-position'], queryFn: async () => 'x' });
    await query.fetch();
    expect(query.state.isInvalidated).toBe(false);
    invalidateMoney(qc);
    expect(query.state.isInvalidated).toBe(true);
  });
});
