import { beforeEach, describe, expect, it } from 'vitest';
import {
  clearAllDrafts,
  enqueueDraft,
  listDrafts,
  removeDraft,
  setOutboxStorageMode,
} from './invoiceDraftCache';

describe('invoice outbox v2 (localStorage path)', () => {
  beforeEach(() => {
    localStorage.clear();
    setOutboxStorageMode('localStorage');
  });

  it('enqueues, lists, and removes drafts for a company/user scope', async () => {
    const saved = await enqueueDraft(1, 9, {
      kind: 'invoice',
      payload: { customer: 3, items: [{ product: 1, quantity: 1 }] },
      idempotencyKey: 'key-a',
    });
    expect(saved.idempotencyKey).toBe('key-a');
    expect(saved.companyId).toBe(1);

    const listed = await listDrafts(1, 9);
    expect(listed).toHaveLength(1);
    expect(listed[0]?.payload.customer).toBe(3);

    expect(await listDrafts(1, 8)).toHaveLength(0);
    expect(await listDrafts(2, 9)).toHaveLength(0);

    await removeDraft(1, 9, 'key-a');
    expect(await listDrafts(1, 9)).toHaveLength(0);
  });

  it('replaces a draft with the same idempotency key', async () => {
    await enqueueDraft(1, 1, {
      kind: 'invoice',
      payload: { notes: 'first' },
      idempotencyKey: 'same',
    });
    await enqueueDraft(1, 1, {
      kind: 'invoice',
      payload: { notes: 'second' },
      idempotencyKey: 'same',
    });
    const listed = await listDrafts(1, 1);
    expect(listed).toHaveLength(1);
    expect(listed[0]?.payload.notes).toBe('second');
  });

  it('round-trips cessRate / discount / serials / supplyType (BB-000577)', async () => {
    await enqueueDraft(1, 2, {
      kind: 'pos',
      payload: {},
      idempotencyKey: 'cess-line',
      lines: [
        {
          productId: 9,
          productName: 'Cess good',
          sku: 'CESS',
          quantity: 1,
          unitPrice: 100,
          gstRate: 18,
          cessRate: 1,
          discountPercent: 0,
          discountAmount: 0,
          serials: ['SN-1'],
          supplyType: 'B2C',
        },
      ],
    });
    const listed = await listDrafts(1, 2);
    expect(listed[0]?.lines?.[0]?.cessRate).toBe(1);
    expect(listed[0]?.lines?.[0]?.serials).toEqual(['SN-1']);
    expect(listed[0]?.lines?.[0]?.supplyType).toBe('B2C');
  });

  it('clears all drafts on logout wipe (BB-000572)', async () => {
    await enqueueDraft(3, 4, { kind: 'invoice', payload: { a: 1 }, idempotencyKey: 'wipe-me' });
    await clearAllDrafts(3, 4);
    expect(await listDrafts(3, 4)).toHaveLength(0);
  });
});
