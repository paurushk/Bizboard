import { beforeEach, describe, expect, it } from 'vitest';
import {
  clearAllDrafts,
  enqueueDraft,
  flushOutbox,
  isPermanentConflict,
  listDrafts,
  removeDraft,
  setOutboxStorageMode,
  updateDraft,
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

  it('updateDraft binds customerId onto an existing POS draft (CR-004)', async () => {
    await enqueueDraft(1, 2, {
      kind: 'pos',
      payload: { pendingCustomerName: 'Ravi Cash' },
      pendingCustomerName: 'Ravi Cash',
      idempotencyKey: 'pos-bind',
    });
    const updated = await updateDraft(1, 2, 'pos-bind', {
      customerId: 88,
      payload: { pendingCustomerName: 'Ravi Cash', customer: 88 },
    });
    expect(updated.customerId).toBe(88);
    expect(updated.payload.customer).toBe(88);
    const listed = await listDrafts(1, 2);
    expect(listed.find((d) => d.idempotencyKey === 'pos-bind')?.customerId).toBe(88);
  });

  it('persists POS pending customer name and invoice complete intent', async () => {
    const pos = await enqueueDraft(1, 2, {
      kind: 'pos',
      payload: { items: [] },
      pendingCustomerName: 'Ravi Cash',
      idempotencyKey: 'pos-pending',
    });
    expect(pos.pendingCustomerName).toBe('Ravi Cash');

    const invoice = await enqueueDraft(1, 2, {
      kind: 'invoice',
      payload: { _completeIntent: true },
      completeIntent: true,
      idempotencyKey: 'inv-complete',
    });
    expect(invoice.completeIntent).toBe(true);

    const listed = await listDrafts(1, 2);
    expect(listed.find((d) => d.idempotencyKey === 'pos-pending')?.pendingCustomerName).toBe(
      'Ravi Cash',
    );
    expect(listed.find((d) => d.idempotencyKey === 'inv-complete')?.completeIntent).toBe(true);
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

  it('throws OUTBOX_STORAGE_FULL when localStorage quota is exceeded', async () => {
    const proto = Object.getPrototypeOf(localStorage);
    const orig = proto.setItem.bind(localStorage);
    proto.setItem = () => {
      throw new DOMException('The quota has been exceeded.', 'QuotaExceededError');
    };
    try {
      await expect(
        enqueueDraft(1, 1, { kind: 'invoice', payload: {}, idempotencyKey: 'quota' }),
      ).rejects.toThrow('OUTBOX_STORAGE_FULL');
    } finally {
      proto.setItem = orig;
    }
  });
});

describe('SR-51 — outbox flush conflict handling', () => {
  beforeEach(() => {
    localStorage.clear();
    setOutboxStorageMode('localStorage');
  });

  const httpErr = (status: number) => ({ response: { status } });

  it('classifies permanent conflicts vs transient failures', () => {
    expect(isPermanentConflict(httpErr(409))).toBe(true);
    expect(isPermanentConflict(httpErr(400))).toBe(true);
    expect(isPermanentConflict(httpErr(422))).toBe(true);
    expect(isPermanentConflict(httpErr(500))).toBe(false);
    expect(isPermanentConflict(httpErr(429))).toBe(false);
    expect(isPermanentConflict(new Error('Network Error'))).toBe(false);
  });

  it('parks a conflicting draft — flagged, kept, and not retried', async () => {
    await enqueueDraft(1, 7, { kind: 'invoice', payload: { customer: 3 }, idempotencyKey: 'conf-1' });

    const first = await flushOutbox(1, 7, async () => {
      throw httpErr(409);
    });
    expect(first).toMatchObject({ flushed: 0, failed: 0, conflicts: 1 });

    const [parked] = await listDrafts(1, 7);
    expect(parked?.conflict?.code).toBeTruthy();
    expect(parked?.conflict?.at).toBeTruthy();

    // a second flush must not re-send it (would only fail the same way)
    let calls = 0;
    const second = await flushOutbox(1, 7, async () => {
      calls += 1;
    });
    expect(calls).toBe(0);
    expect(second).toMatchObject({ flushed: 0, failed: 0, conflicts: 0 });
    expect(await listDrafts(1, 7)).toHaveLength(1);
  });

  it('keeps retrying a transient failure', async () => {
    await enqueueDraft(1, 7, { kind: 'invoice', payload: { customer: 3 }, idempotencyKey: 'tmp-1' });

    const r = await flushOutbox(1, 7, async () => {
      throw new Error('Network Error');
    });
    expect(r).toMatchObject({ flushed: 0, failed: 1, conflicts: 0 });
    const [d] = await listDrafts(1, 7);
    expect(d?.conflict ?? null).toBeNull();

    // next flush retries and succeeds
    const ok = await flushOutbox(1, 7, async () => {});
    expect(ok).toMatchObject({ flushed: 1, failed: 0, conflicts: 0 });
    expect(await listDrafts(1, 7)).toHaveLength(0);
  });

  it('editing a parked draft clears the conflict and lets it flush again', async () => {
    await enqueueDraft(1, 7, { kind: 'invoice', payload: { customer: 3 }, idempotencyKey: 'fix-1' });
    await flushOutbox(1, 7, async () => {
      throw httpErr(409);
    });

    await updateDraft(1, 7, 'fix-1', { payload: { customer: 4 } });
    const [edited] = await listDrafts(1, 7);
    expect(edited?.conflict ?? null).toBeNull();

    const ok = await flushOutbox(1, 7, async () => {});
    expect(ok).toMatchObject({ flushed: 1, conflicts: 0 });
  });
});
