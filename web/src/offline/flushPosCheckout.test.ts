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
});
