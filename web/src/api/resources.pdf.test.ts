import { AxiosError } from 'axios';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const get = vi.fn();

vi.mock('@/api/client', () => ({
  apiClient: { get },
  shouldUseMocks: () => false,
  unwrapData: <T,>(data: T) => data,
}));

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
