import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useProductSearch } from '@/hooks/useProductSearch';

const listProductsPage = vi.fn();

vi.mock('@/api/resources', () => ({
  listProductsPage: (...args: unknown[]) => listProductsPage(...args),
}));

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe('useProductSearch (#32)', () => {
  beforeEach(() => {
    listProductsPage.mockReset();
    listProductsPage.mockResolvedValue({
      results: [{ id: 1, name: 'Recent Widget', sku: 'RW-1', status: 'ACTIVE' }],
      count: 1,
      next: null,
      previous: null,
    });
  });

  it('fetches a default page when the typed query is empty', async () => {
    const { result } = renderHook(() => useProductSearch(), { wrapper });
    await waitFor(() => expect(listProductsPage).toHaveBeenCalled());
    expect(listProductsPage).toHaveBeenCalledWith(
      expect.objectContaining({ page: 1, q: undefined }),
    );
    await waitFor(() => expect(result.current.options[0]?.name).toBe('Recent Widget'));
  });
});
