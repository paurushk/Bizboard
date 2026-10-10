import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useQuotationConvert } from '@/pages/sales/useQuotationConvert';
import type { Quotation } from '@/types/domain';

const api = vi.hoisted(() => ({ convertQuotation: vi.fn(), convertQuotationToOrder: vi.fn() }));

vi.mock('@/api/resources', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/resources')>();
  return {
    ...actual,
    convertQuotation: (...a: unknown[]) => api.convertQuotation(...a),
    convertQuotationToOrder: (...a: unknown[]) => api.convertQuotationToOrder(...a),
    listSalesInvoicesPage: async () => ({ results: [], count: 0, next: null, previous: null }),
  };
});

const quote = {
  id: 5,
  items: [{ id: 11, product: 2, quantity: '10', convertedQuantity: '0' }],
} as unknown as Quotation;

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

const keyOf = (call: unknown[]) => (call[1] as { idempotencyKey: string }).idempotencyKey;

describe('useQuotationConvert idempotency', () => {
  beforeEach(() => {
    api.convertQuotation.mockReset();
    api.convertQuotationToOrder.mockReset();
  });

  it('two successful conversions with the same quantities never share a key', async () => {
    api.convertQuotationToOrder.mockResolvedValue({ id: 1 });
    const onDone = vi.fn();
    const { result } = renderHook(() => useQuotationConvert({ onDone }), { wrapper });
    for (let round = 0; round < 2; round += 1) {
      act(() => result.current.open(quote, 'order'));
      act(() => result.current.confirm([{ id: 11, quantity: 2 }]));
      await waitFor(() => expect(api.convertQuotationToOrder).toHaveBeenCalledTimes(round + 1));
      await waitFor(() => expect(onDone).toHaveBeenCalledTimes(round + 1));
    }
    const [first, second] = api.convertQuotationToOrder.mock.calls;
    expect(keyOf(first)).not.toBe(keyOf(second));
  });

  it('an identical retry after a failure reuses the key, a changed request gets a new one', async () => {
    api.convertQuotationToOrder.mockRejectedValueOnce(new Error('network')).mockResolvedValue({ id: 1 });
    const { result } = renderHook(() => useQuotationConvert({ onDone: vi.fn() }), { wrapper });
    act(() => result.current.open(quote, 'order'));
    act(() => result.current.confirm([{ id: 11, quantity: 2 }]));
    await waitFor(() => expect(result.current.error).toBeTruthy());
    act(() => result.current.confirm([{ id: 11, quantity: 2 }]));
    await waitFor(() => expect(api.convertQuotationToOrder).toHaveBeenCalledTimes(2));
    expect(keyOf(api.convertQuotationToOrder.mock.calls[0])).toBe(keyOf(api.convertQuotationToOrder.mock.calls[1]));
    act(() => result.current.open(quote, 'order'));
    act(() => result.current.confirm([{ id: 11, quantity: 3 }]));
    await waitFor(() => expect(api.convertQuotationToOrder).toHaveBeenCalledTimes(3));
    expect(keyOf(api.convertQuotationToOrder.mock.calls[2])).not.toBe(keyOf(api.convertQuotationToOrder.mock.calls[1]));
  });

  it('a partial invoice conversion reports through onDone and closes the dialog', async () => {
    api.convertQuotation.mockResolvedValue({ id: 9 });
    const onDone = vi.fn();
    const { result } = renderHook(() => useQuotationConvert({ onDone }), { wrapper });
    act(() => result.current.open(quote, 'invoice'));
    act(() => result.current.confirm([{ id: 11, quantity: 4 }]));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(result.current.target).toBeNull();
  });
});
