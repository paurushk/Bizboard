import { afterEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({
  createPurchase: vi.fn(),
  completePurchase: vi.fn(),
  updatePurchase: vi.fn(),
  recordPurchasePayment: vi.fn(),
}));

vi.mock('@/api/resources', () => api);
vi.mock('@/offline/invoiceDraftCache', () => ({
  flushOutbox: vi.fn(),
  isFlushableDraft: vi.fn(),
  listDrafts: vi.fn(),
}));

import { flushPurchaseDraft } from './usePurchaseOffline';
import type { OutboxDraft } from '@/offline/invoiceDraftCache';

function draft(payload: Record<string, unknown>, extra: Partial<OutboxDraft> = {}): OutboxDraft {
  return {
    kind: 'purchase',
    payload: { supplier: 3, invoiceDate: '2026-10-01', items: [], _completeIntent: true, _supplierId: 3, ...payload },
    idempotencyKey: 'queued-key',
    invoiceId: null,
    completeIntent: true,
    ...extra,
  } as OutboxDraft;
}

afterEach(() => vi.clearAllMocks());

describe('flushPurchaseDraft payment (WP-1)', () => {
  it('pays through the one atomic endpoint instead of a payment call plus an allocation call', async () => {
    api.createPurchase.mockResolvedValue({ id: 5, status: 'DRAFT' });
    api.completePurchase.mockResolvedValue({ id: 5, status: 'COMPLETED', paid: '0' });
    await flushPurchaseDraft(draft({ _amountPaid: 40, _paymentMode: 'UPI' }));
    expect(api.createPurchase).toHaveBeenCalledWith(expect.anything(), { idempotencyKey: 'queued-key' });
    expect(api.recordPurchasePayment).toHaveBeenCalledTimes(1);
    expect(api.recordPurchasePayment).toHaveBeenCalledWith(
      5,
      { amount: 40, mode: 'UPI', paymentDate: '2026-10-01' },
      { idempotencyKey: 'purchase-pay-queued-key' },
    );
  });

  it('only pays what is not already paid, so a re-flush after a partial failure cannot double pay', async () => {
    api.createPurchase.mockResolvedValue({ id: 5, status: 'COMPLETED', paid: '25.00' });
    await flushPurchaseDraft(draft({ _amountPaid: 40 }));
    expect(api.recordPurchasePayment.mock.calls[0][1].amount).toBe(15);
  });

  it('records nothing when the bill is already fully paid', async () => {
    api.createPurchase.mockResolvedValue({ id: 5, status: 'COMPLETED', paid: '40.00' });
    await flushPurchaseDraft(draft({ _amountPaid: 40 }));
    expect(api.recordPurchasePayment).not.toHaveBeenCalled();
  });

  it('records nothing for an unpaid bill', async () => {
    api.createPurchase.mockResolvedValue({ id: 5, status: 'DRAFT' });
    api.completePurchase.mockResolvedValue({ id: 5, status: 'COMPLETED', paid: '0' });
    await flushPurchaseDraft(draft({}));
    expect(api.recordPurchasePayment).not.toHaveBeenCalled();
  });

  it('lets a payment failure surface so the outbox keeps the draft and retries it', async () => {
    api.createPurchase.mockResolvedValue({ id: 5, status: 'COMPLETED', paid: '0' });
    api.recordPurchasePayment.mockRejectedValue(new Error('Allocation exceeds invoice open outstanding.'));
    await expect(flushPurchaseDraft(draft({ _amountPaid: 40 }))).rejects.toThrow(/exceeds/);
  });
});
