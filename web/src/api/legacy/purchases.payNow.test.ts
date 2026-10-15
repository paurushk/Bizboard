import { beforeEach, describe, expect, it, vi } from 'vitest';

const { post } = vi.hoisted(() => ({ post: vi.fn() }));

vi.mock('./common', async (orig) => ({
  ...(await orig<typeof import('./common')>()),
  withMocks: <T>(fn: () => Promise<T>) => fn(),
}));
vi.mock('../client', async (orig) => ({
  ...(await orig<typeof import('../client')>()),
  apiClient: { post },
}));

import { completePurchase, recordPurchasePayment } from './purchases';

beforeEach(() => {
  post.mockReset();
  post.mockResolvedValue({ data: { id: 1, status: 'COMPLETED' } });
});

describe('completePurchase pay-at-entry', () => {
  it('sends payNow in the same request as Complete', async () => {
    await completePurchase(1, { payNow: { amount: 40, mode: 'CASH' }, idempotencyKey: 'k1' });
    const [url, body, config] = post.mock.calls[0];
    expect(url).toBe('/purchases/invoices/1/complete/');
    expect(body.payNow).toEqual({ amount: 40, mode: 'CASH' });
    expect(config.headers['Idempotency-Key']).toBe('k1:0000');
  });

  it('gives a confirm-code retry its own key so the first 4xx is not replayed', async () => {
    await completePurchase(1, { payNow: { amount: 40, mode: 'CASH' }, idempotencyKey: 'k1' });
    await completePurchase(1, { payNow: { amount: 40, mode: 'CASH' }, idempotencyKey: 'k1', confirmNoRcm: true });
    const keys = post.mock.calls.map((c) => c[2].headers['Idempotency-Key']);
    expect(new Set(keys).size).toBe(2);
  });

  it('omits payNow and the key when there is no payment', async () => {
    await completePurchase(1, {});
    const [, body, config] = post.mock.calls[0];
    expect('payNow' in body).toBe(false);
    expect(config).toBeUndefined();
  });
});

describe('recordPurchasePayment', () => {
  it('posts one request to record-payment with the key', async () => {
    await recordPurchasePayment(7, { amount: 25, mode: 'UPI' }, { idempotencyKey: 'kp' });
    const [url, body, config] = post.mock.calls[0];
    expect(url).toBe('/purchases/invoices/7/record-payment/');
    expect(body).toEqual({ amount: 25, mode: 'UPI' });
    expect(config.headers['Idempotency-Key']).toBe('kp');
  });
});
