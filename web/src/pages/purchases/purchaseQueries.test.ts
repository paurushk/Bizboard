import { QueryClient } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';
import { invalidatePurchaseSideEffects } from './purchaseQueries';

function keysFor(opts?: Parameters<typeof invalidatePurchaseSideEffects>[1]) {
  const qc = new QueryClient();
  const spy = vi.spyOn(qc, 'invalidateQueries');
  invalidatePurchaseSideEffects(qc, opts);
  return spy.mock.calls.map((c) => JSON.stringify((c[0] as { queryKey: unknown[] }).queryKey));
}

describe('invalidatePurchaseSideEffects', () => {
  it('refreshes lists, supplier balances and the dashboard without stock by default', () => {
    const keys = keysFor();
    expect(keys).toEqual(expect.arrayContaining(['["purchases"]', '["suppliers"]', '["supplier-payments"]', '["dashboard"]']));
    expect(keys).not.toContain('["stock-balance"]');
  });

  it('adds the bill and the stock views when asked', () => {
    const keys = keysFor({ invoiceId: 7, stock: true });
    expect(keys).toEqual(
      expect.arrayContaining(['["purchase-invoice",7]', '["products"]', '["stock-balance"]', '["stock"]', '["low-stock"]']),
    );
  });
});

// F2-001 / F2-026: `['purchases']` is a *prefix* that invalidations match. If a page reads data with the
// bare key it collides with the paged list (`['purchases', page, ...]`) and crashes on the wrong shape.
describe('purchases query-key shapes', () => {
  const sources = import.meta.glob('/src/**/*.tsx', { query: '?raw', import: 'default', eager: true }) as Record<
    string,
    string
  >;

  it('no page reads data with the bare [\'purchases\'] key', () => {
    expect(Object.keys(sources).length).toBeGreaterThan(50);
    const offenders = Object.entries(sources)
      .filter(([path]) => !path.endsWith('.test.tsx'))
      .filter(([, text]) => /useQuery\(\{\s*queryKey:\s*\['purchases'\]\s*[,}]/.test(text))
      .map(([path]) => path);
    expect(offenders).toEqual([]);
  });
});
