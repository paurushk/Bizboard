import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { OutboxDraft } from '@/offline/invoiceDraftCache';

const completeSalesInvoice = vi.fn();
const createAllocation = vi.fn();
const createCustomer = vi.fn();
const createReceipt = vi.fn();
const createSalesInvoice = vi.fn();
const deleteSalesInvoice = vi.fn();
const getCompany = vi.fn();
const getSalesInvoice = vi.fn();
const updateDraft = vi.fn();

vi.mock('@/api/resources', () => ({
  completeSalesInvoice: (...args: unknown[]) => completeSalesInvoice(...args),
  createAllocation: (...args: unknown[]) => createAllocation(...args),
  createCustomer: (...args: unknown[]) => createCustomer(...args),
  createReceipt: (...args: unknown[]) => createReceipt(...args),
  createSalesInvoice: (...args: unknown[]) => createSalesInvoice(...args),
  deleteSalesInvoice: (...args: unknown[]) => deleteSalesInvoice(...args),
  getCompany: (...args: unknown[]) => getCompany(...args),
  getSalesInvoice: (...args: unknown[]) => getSalesInvoice(...args),
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

describe('flushPosDraft (F1-001)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getCompany.mockResolvedValue({ registrationType: 'REGULAR', priceMode: 'EXCLUSIVE' });
    createSalesInvoice.mockResolvedValue({ id: 501 });
    createReceipt.mockResolvedValue({ id: 901 });
    createAllocation.mockResolvedValue({ id: 1101 });
    updateDraft.mockResolvedValue({});
  });

  it('completes normally and passes a stable derived idempotency key to complete/receipt/alloc', async () => {
    completeSalesInvoice.mockResolvedValue({ id: 501, grandTotal: '236.00', number: 'INV-501', status: 'COMPLETED' });
    await flushPosDraft(baseDraft());

    expect(completeSalesInvoice).toHaveBeenCalledWith(
      501,
      expect.objectContaining({ idempotencyKey: 'key-1-complete' }),
    );
    expect(createReceipt).toHaveBeenCalledWith(
      expect.objectContaining({ amount: 236 }),
      { idempotencyKey: 'key-1-receipt' },
    );
    expect(createAllocation).toHaveBeenCalledWith(
      expect.objectContaining({ salesInvoice: 501, amount: 236 }),
      { idempotencyKey: 'key-1-alloc' },
    );
    expect(deleteSalesInvoice).not.toHaveBeenCalled();
    expect(getSalesInvoice).not.toHaveBeenCalled();
  });

  it('pins the invoice date on the draft at the first attempt and persists it', async () => {
    completeSalesInvoice.mockResolvedValue({ id: 501, grandTotal: '236.00', number: 'INV-501', status: 'COMPLETED' });
    await flushPosDraft(baseDraft());
    const created = createSalesInvoice.mock.calls[0][0] as { invoiceDate: string; dueDate: string };
    expect(created.invoiceDate).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(created.dueDate).toBe(created.invoiceDate);
    expect(updateDraft).toHaveBeenCalledWith(
      1, 9, 'key-1',
      expect.objectContaining({ payload: expect.objectContaining({ invoiceDate: created.invoiceDate }) }),
    );
  });

  it('a retry sends the SAME create body even after midnight (server refuses a reused key with a changed body)', async () => {
    completeSalesInvoice.mockResolvedValue({ id: 501, grandTotal: '236.00', number: 'INV-501', status: 'COMPLETED' });
    // First attempt happened yesterday and pinned its date on the draft.
    const pinned = baseDraft({ payload: { invoiceDate: '2026-10-01' } });
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-10-02T00:05:00'));
    try {
      await flushPosDraft(pinned);
    } finally {
      vi.useRealTimers();
    }
    const body = createSalesInvoice.mock.calls[0][0] as { invoiceDate: string; dueDate: string };
    expect(body.invoiceDate).toBe('2026-10-01');
    expect(body.dueDate).toBe('2026-10-01');
  });

  it('forwards warehouse and serials from the draft (R-009)', async () => {
    completeSalesInvoice.mockResolvedValue({ id: 501, grandTotal: '236.00', number: 'INV-501', status: 'COMPLETED' });
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
          },
        ],
      }),
    );
    expect(createSalesInvoice).toHaveBeenCalledWith(
      expect.objectContaining({
        warehouse: 12,
        items: [expect.objectContaining({ serialNumbers: ['SN-99'] })],
      }),
      expect.anything(),
    );
  });

  it('recovers a stranded COMPLETED invoice instead of deleting it and rethrowing', async () => {
    // The response to the first complete() call was lost, but it actually
    // succeeded server-side. A retry pass calls flushPosDraft again;
    // completeSalesInvoice this time fails (e.g. the idempotency record
    // round-trips a benign error, or the client-side call itself errors),
    // and the invoice's own status confirms it is already COMPLETED.
    completeSalesInvoice.mockRejectedValue(new Error('Cannot complete an invoice in status COMPLETED.'));
    getSalesInvoice.mockResolvedValue({
      id: 501, status: 'COMPLETED', grandTotal: '236.00', number: 'INV-501',
    });

    await flushPosDraft(baseDraft());

    // Must NOT delete a genuinely-completed invoice, and must NOT rethrow
    // -- the receipt/allocation steps must still run for it.
    expect(deleteSalesInvoice).not.toHaveBeenCalled();
    expect(createReceipt).toHaveBeenCalledWith(
      expect.objectContaining({ amount: 236 }),
      { idempotencyKey: 'key-1-receipt' },
    );
    expect(createAllocation).toHaveBeenCalledWith(
      expect.objectContaining({ salesInvoice: 501, amount: 236 }),
      { idempotencyKey: 'key-1-alloc' },
    );
  });

  it('deletes and rethrows when the invoice genuinely never completed (still DRAFT)', async () => {
    const failure = new Error('boom');
    completeSalesInvoice.mockRejectedValue(failure);
    getSalesInvoice.mockResolvedValue({ id: 501, status: 'DRAFT' });

    await expect(flushPosDraft(baseDraft())).rejects.toThrow('boom');

    expect(deleteSalesInvoice).toHaveBeenCalledWith(501);
    expect(createReceipt).not.toHaveBeenCalled();
    expect(createAllocation).not.toHaveBeenCalled();
  });

  it('rethrows the original error (without deleting) when the status probe itself also fails', async () => {
    const failure = new Error('network down');
    completeSalesInvoice.mockRejectedValue(failure);
    getSalesInvoice.mockRejectedValue(new Error('also offline'));

    await expect(flushPosDraft(baseDraft())).rejects.toThrow('network down');

    // Can't confirm either way -- must not guess by deleting a possibly-real sale.
    expect(deleteSalesInvoice).not.toHaveBeenCalled();
    expect(createReceipt).not.toHaveBeenCalled();
  });

  it('flushPosDraft_pending_customer_retry_does_not_duplicate_customer', async () => {
    createCustomer.mockResolvedValue({ id: 77, name: 'Ravi Cash' });
    completeSalesInvoice.mockResolvedValue({
      id: 501,
      grandTotal: '236.00',
      number: 'INV-501',
      status: 'COMPLETED',
    });

    await flushPosDraft(
      baseDraft({
        customerId: undefined,
        pendingCustomerName: 'Ravi Cash',
        payload: { pendingCustomerName: 'Ravi Cash' },
      }),
    );

    expect(createCustomer).toHaveBeenCalledTimes(1);
    expect(createCustomer).toHaveBeenCalledWith({ name: 'Ravi Cash', status: 'ACTIVE' });
    expect(updateDraft).toHaveBeenCalledWith(
      1,
      9,
      'key-1',
      expect.objectContaining({
        customerId: 77,
        payload: expect.objectContaining({ customer: 77 }),
      }),
    );
    expect(createSalesInvoice).toHaveBeenCalledWith(
      expect.objectContaining({ customer: 77 }),
      expect.anything(),
    );

    // Retry after draft was bound — must not mint another party.
    await flushPosDraft(
      baseDraft({
        customerId: 77,
        pendingCustomerName: 'Ravi Cash',
        payload: { customer: 77, pendingCustomerName: 'Ravi Cash' },
      }),
    );
    expect(createCustomer).toHaveBeenCalledTimes(1);
    // The customer is bound onto the draft exactly once. (updateDraft is also used to pin the
    // invoice date, so count only the customer-binding writes.)
    const customerBindings = updateDraft.mock.calls.filter(
      (c) => (c[3] as { customerId?: number }).customerId !== undefined,
    );
    expect(customerBindings).toHaveLength(1);
  });

  it('creates one customer per draft, never merging two drafts that typed the same name', async () => {
    createCustomer.mockResolvedValue({ id: 88, name: 'Walk In' });
    completeSalesInvoice.mockResolvedValue({
      id: 501,
      grandTotal: '236.00',
      number: 'INV-501',
      status: 'COMPLETED',
    });
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
    // Two different people can both be "Walk In": sharing one id would merge their ledgers.
    expect(createCustomer).toHaveBeenCalledTimes(3);
  });

  it('flushPendingDraft_triggers_thermal_for_each_flushed_sale (CR-006)', async () => {
    completeSalesInvoice.mockResolvedValue({
      id: 502,
      grandTotal: '150.00',
      number: 'INV-502',
      status: 'COMPLETED',
    });

    const completed = await flushPosDraft(baseDraft({ idempotencyKey: 'key-thermal' }));
    expect(completed).toEqual(
      expect.objectContaining({
        id: 502,
        number: 'INV-502',
        grandTotal: '150.00',
      }),
    );
  });
});

