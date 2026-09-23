import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useCustomerSearch } from '@/hooks/usePartySearch';

const listCustomersPage = vi.fn();

vi.mock('@/api/resources', () => ({
  listCustomersPage: (...args: unknown[]) => listCustomersPage(...args),
  listSuppliersPage: vi.fn(),
}));

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe('useCustomerSearch (#32)', () => {
  beforeEach(() => {
    listCustomersPage.mockReset();
    listCustomersPage.mockResolvedValue({
      results: [{ id: 1, name: 'Recent Party', status: 'ACTIVE' }],
      count: 1,
      next: null,
      previous: null,
    });
  });

  it('fetches a default page when the typed query is empty', async () => {
    const { result } = renderHook(() => useCustomerSearch(), { wrapper });
    await waitFor(() => expect(listCustomersPage).toHaveBeenCalled());
    expect(listCustomersPage).toHaveBeenCalledWith(
      expect.objectContaining({ page: 1, q: undefined }),
    );
    await waitFor(() => expect(result.current.options[0]?.name).toBe('Recent Party'));
  });
});
