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
});
