import { beforeEach, describe, expect, it, vi } from 'vitest';

const get = vi.fn();
const post = vi.fn();
const patch = vi.fn();
const del = vi.fn();

vi.mock('@/api/client', () => ({
  apiClient: { get, post, patch, delete: del },
  shouldUseMocks: () => false,
  unwrapData: <T,>(data: T) => data,
  idempotencyHeaders: (key?: string) => ({ 'Idempotency-Key': key ?? 'test-key' }),
}));

beforeEach(() => {
  for (const fn of [get, post, patch, del]) fn.mockReset();
});

describe('customer API helpers', () => {
  it('asks for the summary with the list filters', async () => {
    get.mockResolvedValue({ data: { totalCount: 3 } });
    const { getCustomersSummary } = await import('@/api/resources');
    await expect(getCustomersSummary({ q: 'ravi', status: 'ACTIVE' })).resolves.toEqual({ totalCount: 3 });
    expect(get).toHaveBeenCalledWith('/customers/summary/', { params: { q: 'ravi', status: 'ACTIVE' } });
  });

  it('exports with the filters and the sort, as a blob', async () => {
    const blob = new Blob(['csv']);
    get.mockResolvedValue({ data: blob });
    const { exportCustomersCsv } = await import('@/api/resources');
    await expect(exportCustomersCsv({ status: 'BLOCKED', sort: 'balance' })).resolves.toBe(blob);
    expect(get).toHaveBeenCalledWith('/customers/export/', {
      params: { status: 'BLOCKED', sort: 'balance' },
      responseType: 'blob',
    });
  });

  it('turns a failed export into a readable error body', async () => {
    const json = JSON.stringify({ error: { message: 'Too many customers to export at once' } });
    class TextBlob extends Blob {
      text() {
        return Promise.resolve(json);
      }
    }
    const body = new TextBlob([json]);
    const failure = Object.assign(new Error('x'), { response: { data: body as unknown } });
    get.mockRejectedValue(failure);
    const { exportCustomersCsv } = await import('@/api/resources');
    await expect(exportCustomersCsv()).rejects.toBe(failure);
    expect((failure.response.data as { error: { message: string } }).error.message).toMatch(/Too many customers/);
  });

  it('looks a GSTIN up fresh every time the user asks', async () => {
    post.mockResolvedValue({ data: { gstin: '29ABCDE1234F1ZW' } });
    const { lookupCustomerGstin } = await import('@/api/resources');
    await lookupCustomerGstin('29ABCDE1234F1ZW');
    expect(post).toHaveBeenCalledWith('/customers/lookup-gstin/', { gstin: '29ABCDE1234F1ZW', refresh: true });
  });

  it('verifies several customers in one call', async () => {
    post.mockResolvedValue({ data: { results: [{ id: 1, status: 'UNVERIFIED', notice: '', error: '' }] } });
    const { verifyCustomersGstinBulk } = await import('@/api/resources');
    const result = await verifyCustomersGstinBulk([1, 2]);
    expect(post).toHaveBeenCalledWith('/customers/verify-gstin-bulk/', { ids: [1, 2] });
    expect(result.results[0].id).toBe(1);
  });

  it('reads the health check and the history', async () => {
    get.mockResolvedValueOnce({ data: { total: 1, checks: [{ check: 'state_mismatch', label: 'x', count: 1 }] } });
    get.mockResolvedValueOnce({ data: { results: [{ id: 9, changes: {} }] } });
    const { getCustomersHealth, listCustomerHistory } = await import('@/api/resources');
    await expect(getCustomersHealth()).resolves.toMatchObject({ total: 1 });
    expect(get).toHaveBeenCalledWith('/customers/health/');
    await expect(listCustomerHistory(4)).resolves.toEqual([{ id: 9, changes: {} }]);
    expect(get).toHaveBeenLastCalledWith('/customers/4/history/');
  });

  it('tells an archive from a delete by the status code', async () => {
    del.mockResolvedValueOnce({ status: 200, data: { detail: 'marked Inactive' } });
    del.mockResolvedValueOnce({ status: 204, data: '' });
    const { deleteCustomer } = await import('@/api/resources');
    await expect(deleteCustomer(1)).resolves.toEqual({ archived: true, detail: 'marked Inactive' });
    await expect(deleteCustomer(2)).resolves.toEqual({ archived: false, detail: '' });
    expect(del).toHaveBeenCalledWith('/customers/1/');
  });

  it('sets the POS walk-in by customer id', async () => {
    post.mockResolvedValue({ data: { id: 5, isPosWalkIn: true } });
    const { setPosWalkInCustomer } = await import('@/api/resources');
    await setPosWalkInCustomer(5);
    expect(post).toHaveBeenCalledWith('/customers/set-pos-walk-in/', { customer: 5 });
  });

  it('sends the row version on an update so a stale edit is refused', async () => {
    patch.mockResolvedValue({ data: { id: 3, version: 4 } });
    const { updateCustomer } = await import('@/api/resources');
    await updateCustomer(3, { notes: 'x', version: 3 });
    expect(patch).toHaveBeenCalledWith('/customers/3/', { notes: 'x', version: 3 });
  });

  it('returns the verification notice with the customer', async () => {
    post.mockResolvedValue({ data: { id: 1, verificationNotice: 'Live GSTIN verification is not configured.' } });
    const { verifyCustomerGstin } = await import('@/api/resources');
    await expect(verifyCustomerGstin(1)).resolves.toMatchObject({
      verificationNotice: expect.stringContaining('not configured'),
    });
    expect(post).toHaveBeenCalledWith('/customers/1/verify-gstin/');
  });
});
