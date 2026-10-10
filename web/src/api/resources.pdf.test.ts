import { AxiosError } from 'axios';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const get = vi.fn();
const post = vi.fn();

vi.mock('@/api/client', () => ({
  apiClient: { get, post },
  shouldUseMocks: () => false,
  unwrapData: <T,>(data: T) => data,
  idempotencyHeaders: (key?: string) => ({ 'Idempotency-Key': key ?? 'test-key' }),
}));

describe('downloadBulkInvoicePdfZip', () => {
  it('fetches the zip from the API so the protected media path is never linked', async () => {
    get.mockReset();
    const zip = new Blob(['zip']);
    get.mockResolvedValue({ data: zip });
    const { downloadBulkInvoicePdfZip } = await import('@/api/resources');
    await expect(downloadBulkInvoicePdfZip(77)).resolves.toBe(zip);
    expect(get).toHaveBeenCalledWith('/sales/invoices/bulk-pdf-zip/77/', { responseType: 'blob' });
  });
});

describe('cancelSalesInvoice', () => {
  beforeEach(() => post.mockReset());

  it('sends the reason and maps 202 to a pending approval', async () => {
    post.mockResolvedValue({ status: 202, data: { status: 'PENDING', approval_id: 5 } });
    const { cancelSalesInvoice } = await import('@/api/resources');
    await expect(cancelSalesInvoice(3, { reason: 'wrong bill' })).resolves.toEqual({
      outcome: 'pending',
      invoiceId: 3,
      approvalId: 5,
    });
    expect(post).toHaveBeenCalledWith('/sales/invoices/3/cancel/', { cancelReason: 'wrong bill' });
  });

  it('maps 200 to the cancelled invoice', async () => {
    post.mockResolvedValue({ status: 200, data: { id: 3, status: 'CANCELLED' } });
    const { cancelSalesInvoice } = await import('@/api/resources');
    await expect(cancelSalesInvoice(3)).resolves.toEqual({
      outcome: 'cancelled',
      invoice: { id: 3, status: 'CANCELLED' },
    });
  });

  it('refuses a 202 without an approval and any other status', async () => {
    const { cancelSalesInvoice } = await import('@/api/resources');
    post.mockResolvedValueOnce({ status: 202, data: { status: 'PENDING' } });
    await expect(cancelSalesInvoice(3)).rejects.toThrow(/pending approval/);
    post.mockResolvedValueOnce({ status: 204, data: {} });
    await expect(cancelSalesInvoice(3)).rejects.toThrow(/Unexpected cancel status 204/);
  });
});

describe('downloadInvoicePdf', () => {
  beforeEach(() => {
    get.mockReset();
    get.mockResolvedValue({ data: new Blob(['pdf']) });
  });

  it('passes ORIGINAL by default', async () => {
    const { downloadInvoicePdf } = await import('@/api/resources');
    await downloadInvoicePdf(42);
    expect(get).toHaveBeenCalledWith('/sales/invoices/42/pdf/', {
      responseType: 'blob',
      params: { copy: 'ORIGINAL' },
    });
  });

  it('passes DUPLICATE when requested', async () => {
    const { downloadInvoicePdf } = await import('@/api/resources');
    await downloadInvoicePdf(42, { copy: 'DUPLICATE' });
    expect(get).toHaveBeenCalledWith('/sales/invoices/42/pdf/', {
      responseType: 'blob',
      params: { copy: 'DUPLICATE' },
    });
  });

  it('parses 409 blob JSON into a readable Error', async () => {
    const payload = JSON.stringify({ detail: 'PDF is generating, retry shortly' });
    const blob = new Blob([payload], { type: 'application/json' });
    // jsdom Blob may lack .text(); ensure the path under test can read the body.
    if (typeof blob.text !== 'function') {
      Object.defineProperty(blob, 'text', {
        value: async () => payload,
      });
    }
    const err = new AxiosError('Conflict');
    err.response = {
      status: 409,
      data: blob,
      statusText: 'Conflict',
      headers: {},
      config: {} as never,
    };
    get.mockRejectedValue(err);

    const { downloadInvoicePdf } = await import('@/api/resources');
    await expect(downloadInvoicePdf(42)).rejects.toThrow('PDF is generating, retry shortly');
  });
});
