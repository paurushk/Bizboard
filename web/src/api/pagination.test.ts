import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/api/client', () => ({
  apiClient: {
    get: vi.fn(),
  },
  unwrapData: <T>(data: T) => data,
  shouldUseMocks: () => false,
}));

import { apiClient } from '@/api/client';
import { fetchNextPage, listCustomers, listPage } from '@/api/resources';

describe('list pagination helpers', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('listPage returns results and next cursor', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: {
        results: [{ id: 1 }, { id: 2 }],
        next: 'http://localhost/api/v1/sales/invoices/?cursor=abc',
        previous: null,
        count: 52,
      },
    });
    const page = await listPage('/sales/invoices/');
    expect(page.results).toHaveLength(2);
    expect(page.next).toContain('cursor=abc');
  });

  it('fetchNextPage strips /api/v1 prefix from absolute next URL', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: { results: [{ id: 3 }], next: null, previous: null, count: 3 },
    });
    const page = await fetchNextPage<{ id: number }>(
      'http://127.0.0.1:8000/api/v1/sales/invoices/?cursor=xyz',
    );
    expect(apiClient.get).toHaveBeenCalledWith('/sales/invoices/?cursor=xyz');
    expect(page.results[0].id).toBe(3);
    expect(page.next).toBeNull();
  });

  it('BUG-521/606-609: listCustomers walks every page instead of returning only page 1', async () => {
    const page1 = { id: 1, name: 'Customer 1' };
    const page2 = { id: 2, name: 'Customer 2 (page 2)' };
    vi.mocked(apiClient.get)
      .mockResolvedValueOnce({
        data: {
          results: [page1],
          next: 'http://localhost/api/v1/customers/?cursor=page2',
          previous: null,
          count: 2,
        },
      })
      .mockResolvedValueOnce({
        data: { results: [page2], next: null, previous: null, count: 2 },
      });

    const customers = await listCustomers();
    expect(customers).toHaveLength(2);
    expect(customers.map((c) => c.id)).toEqual([1, 2]);
  });
});
