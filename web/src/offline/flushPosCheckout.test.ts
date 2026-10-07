import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { OutboxDraft } from '@/offline/invoiceDraftCache';

const createCustomer = vi.fn();
const getCompany = vi.fn();
const ensurePosWalkIn = vi.fn();
const posCheckout = vi.fn();
const updateDraft = vi.fn();

vi.mock('@/api/resources', () => ({
  createCustomer: (...args: unknown[]) => createCustomer(...args),
  getCompany: (...args: unknown[]) => getCompany(...args),
  ensurePosWalkIn: (...args: unknown[]) => ensurePosWalkIn(...args),
  posCheckout: (...args: unknown[]) => posCheckout(...args),
}));

vi.mock('@/offline/invoiceDraftCache', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/offline/invoiceDraftCache')>();
  return {
    ...actual,
    updateDraft: (...args: unknown[]) => updateDraft(...args),
  };
});

const { flushPosDraft } = await import('./flushPosCheckout');

function baseDraft(overrides: Partial<OutboxDraft> = {}): OutboxDraft {
  return {
    version: 2,
    id: 'scope:key-1',
    companyId: 1,
    userId: 9,
    kind: 'pos',
    idempotencyKey: 'key-1',
    savedAt: new Date().toISOString(),
    payload: {},
    customerId: 5,
    paymentMode: 'CASH',
    lines: [
      {
        productId: 1,
        productName: 'Widget',
        sku: 'W-1',
        quantity: 2,
        unitPrice: 100,
        gstRate: 18,
      },
    ],
    ...overrides,
  };
}

describe('flushPosDraft', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getCompany.mockResolvedValue({ registrationType: 'REGULAR', priceMode: 'EXCLUSIVE' });
    posCheckout.mockResolvedValue({ invoice: { id: 501, number: 'INV-501', grandTotal: '236.00' } });
    ensurePosWalkIn.mockResolvedValue({ id: 3 });
    updateDraft.mockResolvedValue({});
  });

  it('sends one atomic checkout under the draft idempotency key with a cash payment', async () => {
    const completed = await flushPosDraft(baseDraft());
    expect(posCheckout).toHaveBeenCalledTimes(1);
    expect(posCheckout).toHaveBeenCalledWith(
      expect.objectContaining({ payment: { mode: 'CASH' } }),
      { idempotencyKey: 'key-1' },
    );
    expect(completed).toEqual(expect.objectContaining({ id: 501, number: 'INV-501' }));
  });

  it.each(['CARD', 'UPI', 'BANK', 'CHEQUE', 'CREDIT'])(
    'refuses an offline %s sale and never posts it as cash',
    async (mode) => {
      await expect(flushPosDraft(baseDraft({ paymentMode: mode as OutboxDraft['paymentMode'] }))).rejects.toThrow(
        /cannot be synced/,
      );
      expect(posCheckout).not.toHaveBeenCalled();
    },
  );

  it('pins the invoice date on the draft at the first attempt and persists it', async () => {
    await flushPosDraft(baseDraft());
    const body = posCheckout.mock.calls[0][0] as { invoice: { invoice_date: string; due_date: string } };
    expect(body.invoice.invoice_date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(body.invoice.due_date).toBe(body.invoice.invoice_date);
    expect(updateDraft).toHaveBeenCalledWith(
      1, 9, 'key-1',
      expect.objectContaining({ payload: expect.objectContaining({ invoiceDate: body.invoice.invoice_date }) }),
    );
  });

  it('a retry sends the SAME body even after midnight (the server refuses a reused key with a changed body)', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-10-02T00:05:00'));
    try {
      await flushPosDraft(baseDraft({ payload: { invoiceDate: '2026-10-01' } }));
    } finally {
      vi.useRealTimers();
    }
    const body = posCheckout.mock.calls[0][0] as { invoice: { invoice_date: string; due_date: string } };
    expect(body.invoice.invoice_date).toBe('2026-10-01');
    expect(body.invoice.due_date).toBe('2026-10-01');
  });

  it('forwards warehouse, serials, and the chosen batch from the draft', async () => {
    await flushPosDraft(
      baseDraft({
        payload: { warehouse: 12 },
        lines: [
          {
            productId: 1,
            productName: 'Serial widget',
            sku: 'S-1',
            quantity: 1,
            unitPrice: 100,
            gstRate: 18,
            serials: ['SN-99'],
            batchNo: 'LOT-B',
          },
        ],
      }),
    );
    expect(posCheckout).toHaveBeenCalledWith(
      expect.objectContaining({
        invoice: expect.objectContaining({
          warehouse: 12,
          items: [expect.objectContaining({ serial_numbers: ['SN-99'], batch_no: 'LOT-B' })],
        }),
      }),
      expect.anything(),
    );
  });

  it('propagates a checkout failure so the draft stays queued', async () => {
    posCheckout.mockRejectedValue(new Error('network down'));
    await expect(flushPosDraft(baseDraft())).rejects.toThrow('network down');
  });

  it('creates the typed customer once and binds it to the draft', async () => {
    createCustomer.mockResolvedValue({ id: 77, name: 'Ravi Cash' });
    await flushPosDraft(
      baseDraft({
        customerId: undefined,
        pendingCustomerName: 'Ravi Cash',
        payload: { pendingCustomerName: 'Ravi Cash' },
      }),
    );
    expect(createCustomer).toHaveBeenCalledTimes(1);
    expect(createCustomer).toHaveBeenCalledWith({ name: 'Ravi Cash', status: 'ACTIVE' });
    expect(posCheckout).toHaveBeenCalledWith(
      expect.objectContaining({ invoice: expect.objectContaining({ customer: 77 }) }),
      expect.anything(),
    );
    // Retry after the draft was bound must not mint another party.
    await flushPosDraft(
      baseDraft({
        customerId: 77,
        pendingCustomerName: 'Ravi Cash',
        payload: { customer: 77, pendingCustomerName: 'Ravi Cash' },
      }),
    );
    expect(createCustomer).toHaveBeenCalledTimes(1);
  });

  it('creates one customer per draft, never merging two drafts that typed the same name', async () => {
    createCustomer.mockResolvedValue({ id: 88, name: 'Walk In' });
    for (const key of ['a', 'b', 'c']) {
      await flushPosDraft(
        baseDraft({
          id: `scope:${key}`,
          idempotencyKey: key,
          customerId: undefined,
          pendingCustomerName: 'Walk In',
          payload: { pendingCustomerName: 'Walk In' },
        }),
      );
    }
    expect(createCustomer).toHaveBeenCalledTimes(3);
  });

  it('binds an unnamed draft to the walk-in party the server gives back', async () => {
    ensurePosWalkIn.mockResolvedValue({ id: 3 });
    await flushPosDraft(baseDraft({ customerId: undefined }));
    expect(ensurePosWalkIn).toHaveBeenCalledTimes(1);
    expect(createCustomer).not.toHaveBeenCalled();
    expect(posCheckout).toHaveBeenCalledWith(
      expect.objectContaining({ invoice: expect.objectContaining({ customer: 3 }) }),
      expect.anything(),
    );
  });

  it('queues named credit only when the draft was accepted as offline credit', async () => {
    await expect(
      flushPosDraft(baseDraft({ paymentMode: 'CREDIT', payload: {} })),
    ).rejects.toThrow(/cannot be synced/);
    await flushPosDraft(baseDraft({ paymentMode: 'CREDIT', payload: { offlineCredit: true } }));
    expect(posCheckout).toHaveBeenCalledWith(
      expect.objectContaining({ offline_credit: true, payment: { mode: 'CREDIT' } }),
      expect.anything(),
    );
  });
});
