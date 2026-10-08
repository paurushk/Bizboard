import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { OutboxDraft } from '@/offline/invoiceDraftCache';

const post = vi.fn();
const getCompany = vi.fn();

vi.mock('@/api/client', () => ({
  apiClient: { post: (...args: unknown[]) => post(...args) },
  unwrapData: <T,>(data: unknown) => data as T,
}));
vi.mock('@/api/resources', () => ({
  createCustomer: vi.fn(),
  ensurePosWalkIn: vi.fn(),
  getCompany: (...args: unknown[]) => getCompany(...args),
  posCheckout: vi.fn(),
}));

const { flushPosBatch } = await import('./flushPosCheckout');

function draft(key: string, overrides: Partial<OutboxDraft> = {}): OutboxDraft {
  return {
    version: 2,
    id: `scope:${key}`,
    companyId: 1,
    userId: 9,
    kind: 'pos',
    idempotencyKey: key,
    savedAt: new Date().toISOString(),
    payload: { terminalId: 'drawer-a', outageId: 'outage-1', shiftId: 4 },
    customerId: 5,
    paymentMode: 'CASH',
    lines: [{ productId: 1, productName: 'Widget', sku: 'W', quantity: 1, unitPrice: 10, gstRate: 0, batchNo: 'LOT-B' }],
    ...overrides,
  };
}

beforeEach(() => {
  post.mockReset();
  getCompany.mockResolvedValue({ registrationType: 'REGULAR', priceMode: 'EXCLUSIVE' });
});

describe('flushPosBatch', () => {
  it('sends each bill under its own key with the outage, terminal, shift, and lot', async () => {
    post.mockResolvedValue({
      data: { results: [{ invoice: { id: 11 } }, { invoice: { id: 12 } }], errors: [] },
    });
    const out = await flushPosBatch([draft('a'), draft('b')]);
    expect(post).toHaveBeenCalledWith('/sales/pos/batch-sync/', expect.anything());
    const sent = post.mock.calls[0][1].checkouts as Array<Record<string, unknown>>;
    expect(sent.map((row) => row.idempotency_key)).toEqual(['a', 'b']);
    expect(sent[0]).toMatchObject({ offline: true, terminal_id: 'drawer-a', outage_id: 'outage-1', shift_id: 4 });
    const items = (sent[0].invoice as { items: Array<Record<string, unknown>> }).items;
    expect(items[0].batch_no).toBe('LOT-B');
    expect(out.invoices.map((row) => row.id)).toEqual([11, 12]);
  });

  it('marks only a credit draft accepted as offline credit', async () => {
    post.mockResolvedValue({ data: { results: [], errors: [] } });
    await flushPosBatch([
      draft('credit-ok', { paymentMode: 'CREDIT', payload: { offlineCredit: true } }),
      draft('credit-plain', { paymentMode: 'CREDIT', payload: {} }),
      draft('cash'),
    ]);
    const sent = post.mock.calls[0][1].checkouts as Array<Record<string, unknown>>;
    expect(sent.map((row) => row.offline_credit)).toEqual([true, false, false]);
  });

  it('reports which bills the server refused, by position', async () => {
    post.mockResolvedValue({
      data: { results: [{ invoice: { id: 11 } }], errors: [{ index: 1, detail: 'credit cap' }] },
    });
    const out = await flushPosBatch([draft('a'), draft('b')]);
    expect(out.errors).toEqual([{ index: 1, detail: 'credit cap' }]);
  });

  it('never sends more than 50 bills at once', async () => {
    post.mockResolvedValue({ data: { results: [], errors: [] } });
    await flushPosBatch(Array.from({ length: 60 }, (_, i) => draft(`k${i}`)));
    expect(post.mock.calls[0][1].checkouts).toHaveLength(50);
  });
});
