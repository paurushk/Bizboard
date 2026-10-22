import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/api/client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    defaults: { baseURL: '/api/v1' },
  },
  unwrapData: <T>(data: T) => data,
  idempotencyHeaders: (key?: string) => ({ 'Idempotency-Key': key ?? 'generated' }),
}));

import { apiClient } from '@/api/client';
import { errorCode, getReport, importRecipes, listWorkOrders, quickProduction } from '@/api/mfg';

describe('manufacturing API client', () => {
  beforeEach(() => vi.clearAllMocks());

  it('sends list filters as snake_case query parameters and drops empty ones', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: { results: [], next: null, previous: null, count: 0 } });
    await listWorkOrders({ status: 'RELEASED', dueBefore: '2026-11-01', product: undefined });
    const [, options] = vi.mocked(apiClient.get).mock.calls[0];
    const params = (options as { params: Record<string, string> }).params;
    expect(params.status).toBe('RELEASED');
    expect(params.due_before).toBe('2026-11-01');
    expect(params).not.toHaveProperty('product');
  });

  it('turns asOf into as_of for reports', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: {} });
    await getReport('wip', { asOf: '2026-10-31' });
    expect(vi.mocked(apiClient.get).mock.calls[0][1]).toEqual({ params: { as_of: '2026-10-31' } });
  });

  it('quick production carries the idempotency key it was given', async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: { id: 5, number: 'WO-1' } });
    await quickProduction({ product: 3, qty: '10' }, 'attempt-1');
    const [url, , config] = vi.mocked(apiClient.post).mock.calls[0];
    expect(url).toContain('/manufacturing/quick-production/');
    expect((config as { headers: Record<string, string> }).headers['Idempotency-Key']).toBe('attempt-1');
  });

  it('reads the rule code off an error response', () => {
    const err = Object.assign(new Error('x'), { isAxiosError: true, response: { data: { error: { code: 'MFG_REVERSAL_ORDER' } } } });
    expect(errorCode(err)).toBe('MFG_REVERSAL_ORDER');
    expect(errorCode(new Error('plain'))).toBe('');
  });

  it('shows the row list of a rejected import file instead of throwing', async () => {
    const rejected = Object.assign(new Error('bad'), {
      isAxiosError: true,
      response: { status: 422, data: { recipes: [], errors: [{ row: 3, message: 'Unknown item' }], created: 0, committed: false } },
    });
    vi.mocked(apiClient.post).mockRejectedValue(rejected);
    const result = await importRecipes(new File(['x'], 'r.csv'), false);
    expect(result.errors).toEqual([{ row: 3, message: 'Unknown item' }]);
    expect(result.committed).toBe(false);
  });
});
