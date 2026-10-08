import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const post = vi.fn();
const get = vi.fn();
vi.mock('@/api/client', () => ({
  apiClient: {
    post: (...args: unknown[]) => post(...args),
    get: (...args: unknown[]) => get(...args),
    delete: vi.fn(),
  },
  unwrapData: <T,>(data: unknown) => data as T,
}));

const { openTodayShift, returnPosBill } = await import('./posCounterApi');

beforeEach(() => {
  post.mockReset();
  get.mockReset();
  post.mockResolvedValue({ data: {} });
});

afterEach(() => vi.useRealTimers());

describe('counter API', () => {
  it('opens the till on the local calendar date, not the UTC date', async () => {
    vi.useFakeTimers();
    // 00:30 on 8 Oct local time. In India that is still 7 Oct in UTC.
    vi.setSystemTime(new Date(2026, 9, 8, 0, 30));
    await openTodayShift('100', { id: 'drawer-a', label: 'Counter 1' });
    const body = post.mock.calls[0][1] as { business_date: string; terminal_id: string; terminal_label: string };
    expect(body.business_date).toBe('2026-10-08');
    expect(body.terminal_id).toBe('drawer-a');
    expect(body.terminal_label).toBe('Counter 1');
  });

  it('sends the owner PIN with a return', async () => {
    post.mockResolvedValue({ data: { id: 1, exchange: false, customerId: 2 } });
    await returnPosBill({ invoice: 9, reason: 'Counter return', ownerPin: '2468' });
    const body = post.mock.calls[0][1] as { owner_pin?: string; invoice: number };
    expect(body.owner_pin).toBe('2468');
    expect(body.invoice).toBe(9);
  });

  it('leaves the PIN out when none was typed', async () => {
    post.mockResolvedValue({ data: { id: 1, exchange: false, customerId: 2 } });
    await returnPosBill({ invoice: 9 });
    const body = post.mock.calls[0][1] as Record<string, unknown>;
    expect(body.owner_pin).toBeUndefined();
  });
});
