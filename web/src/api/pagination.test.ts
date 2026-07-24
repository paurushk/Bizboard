import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/api/client', () => ({
  apiClient: {
    get: vi.fn(),
  },
  unwrapData: <T>(data: T) => data,
}));

import { apiClient } from '@/api/client';
import { fetchNextPage, listPage } from '@/api/resources';

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
});
