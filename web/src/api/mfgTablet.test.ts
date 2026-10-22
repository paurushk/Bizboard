import { beforeEach, describe, expect, it, vi } from 'vitest';

const tablet = vi.hoisted(() => ({ post: vi.fn(), get: vi.fn() }));

vi.mock('axios', () => {
  const isAxiosError = (e: unknown) => Boolean((e as { isAxiosError?: boolean })?.isAxiosError);
  return {
    default: { create: () => ({ ...tablet, interceptors: { request: { use: vi.fn() } } }), isAxiosError },
    isAxiosError,
  };
});
vi.mock('@/api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn(), defaults: { baseURL: '/api/v1' } },
  unwrapData: <T>(data: T) => data,
  idempotencyHeaders: () => ({}),
}));

import { applyQueued, flushTabletQueue, rememberTabletOperator, tabletQueue, tabletTap, type JobCard } from '@/api/mfg';

const noSignal = () => Object.assign(new Error('Network Error'), { isAxiosError: true });
const refused = (status: number, message = 'no') =>
  Object.assign(new Error(message), { isAxiosError: true, response: { status, data: { error: { message } } } });
const card = (over: Partial<JobCard> = {}): JobCard =>
  ({ id: 1, status: 'PLANNED', qtyGood: '0', qtyRejected: '0', qtyPlanned: '10', ...over }) as JobCard;

describe('the tablet keeps taps while there is no signal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    sessionStorage.clear();
    rememberTabletOperator(7);
  });

  it('sends a tap with the time it happened and a key', async () => {
    tablet.post.mockResolvedValue({ data: card({ status: 'IN_PROGRESS' }) });
    const out = await tabletTap(1, 'start');
    expect(out.queued).toBe(false);
    const [url, body, config] = tablet.post.mock.calls[0];
    expect(url).toContain('/tablet/cards/1/start/');
    expect(typeof (body as { occurred_at: string }).occurred_at).toBe('string');
    expect(typeof (config as { headers: Record<string, string> }).headers['Idempotency-Key']).toBe('string');
    expect(tabletQueue()).toHaveLength(0);
  });

  it('keeps the tap when the server cannot be reached, and queues what follows behind it', async () => {
    tablet.post.mockRejectedValueOnce(noSignal());
    expect((await tabletTap(1, 'start')).queued).toBe(true);
    expect((await tabletTap(1, 'finish', { qtyGood: '10' })).queued).toBe(true);
    expect(tablet.post).toHaveBeenCalledTimes(1); // the second never tried: order matters
    expect(tabletQueue().map((q) => q.verb)).toEqual(['start', 'finish']);
    expect(tabletQueue().every((q) => q.operator === 7)).toBe(true);
  });

  it.each([500, 503, 429])('keeps a live tap when the server answers %i', async (status) => {
    tablet.post.mockRejectedValueOnce(refused(status, 'down'));
    expect((await tabletTap(1, 'start')).queued).toBe(true);
    expect(tabletQueue()).toHaveLength(1);
  });

  it('shows a sign-out to the operator instead of keeping the tap', async () => {
    tablet.post.mockRejectedValueOnce(refused(403, 'Sign in again'));
    await expect(tabletTap(1, 'start')).rejects.toBeTruthy();
    expect(tabletQueue()).toHaveLength(0);
  });

  it('does not keep a tap the server refused', async () => {
    tablet.post.mockRejectedValueOnce(refused(400, 'The job card is finished.'));
    await expect(tabletTap(1, 'start')).rejects.toBeTruthy();
    expect(tabletQueue()).toHaveLength(0);
  });

  it('sends the queue in order and keeps the same keys on a retry', async () => {
    tablet.post.mockRejectedValueOnce(noSignal());
    await tabletTap(1, 'start');
    await tabletTap(1, 'pause');
    const keys = tabletQueue().map((q) => q.key);
    tablet.post.mockResolvedValue({ data: card() });
    const out = await flushTabletQueue();
    expect(out).toEqual({ sent: 2, left: 0, refused: [] });
    const sentKeys = tablet.post.mock.calls.slice(1).map((c) => (c[2] as { headers: Record<string, string> }).headers['Idempotency-Key']);
    expect(sentKeys).toEqual(keys);
  });

  it('stops at the first tap that cannot get through and keeps the rest', async () => {
    tablet.post.mockRejectedValueOnce(noSignal());
    await tabletTap(1, 'start');
    await tabletTap(1, 'pause');
    tablet.post.mockRejectedValue(noSignal());
    const out = await flushTabletQueue();
    expect(out.sent).toBe(0);
    expect(out.left).toBe(2);
  });

  it('drops a tap the server refuses and reports it, then carries on', async () => {
    tablet.post.mockRejectedValueOnce(noSignal());
    await tabletTap(1, 'start');
    await tabletTap(2, 'start');
    tablet.post.mockRejectedValueOnce(refused(400, 'The job card is finished.')).mockResolvedValue({ data: card() });
    const out = await flushTabletQueue();
    expect(out).toEqual({ sent: 1, left: 0, refused: ['The job card is finished.'] });
  });

  it.each([409, 429, 500, 502, 503, 504])('keeps the tap when the server answers %i, because that is not a refusal', async (status) => {
    tablet.post.mockRejectedValueOnce(noSignal());
    await tabletTap(1, 'start');
    tablet.post.mockRejectedValue(refused(status, 'busy'));
    const out = await flushTabletQueue();
    expect(out).toEqual({ sent: 0, left: 1, refused: [] });
    tablet.post.mockResolvedValue({ data: card() });
    expect((await flushTabletQueue()).sent).toBe(1);                    // and it goes through on the next try
  });

  it('keeps everything when the sign-in has ended', async () => {
    tablet.post.mockRejectedValueOnce(noSignal());
    await tabletTap(1, 'start');
    tablet.post.mockRejectedValue(refused(403, 'Sign in again'));
    const out = await flushTabletQueue();
    expect(out.left).toBe(1);
    expect(out.refused).toEqual([]);
  });

  it('never sends another operator\'s taps', async () => {
    tablet.post.mockRejectedValueOnce(noSignal());
    await tabletTap(1, 'start');
    rememberTabletOperator(8);
    tablet.post.mockResolvedValue({ data: card() });
    const out = await flushTabletQueue();
    expect(out.sent).toBe(0);
    expect(out.left).toBe(1);
  });

  it('sends a tap at once even when another operator has taps still waiting', async () => {
    tablet.post.mockRejectedValueOnce(noSignal());
    await tabletTap(1, 'start'); // operator 7, kept
    rememberTabletOperator(8);
    tablet.post.mockResolvedValue({ data: card({ status: 'IN_PROGRESS' }) });
    const out = await tabletTap(2, 'start');
    expect(out.queued).toBe(false);
    expect(tabletQueue()).toHaveLength(1);
    expect(tabletQueue()[0].operator).toBe(7);
  });

  it('shows the cards as the operator left them', () => {
    const queue = [
      { key: 'a', operator: 7, cardId: 1, verb: 'start' as const, at: 'x' },
      { key: 'b', operator: 7, cardId: 1, verb: 'report' as const, at: 'x', qtyGood: '4', qtyRejected: '1' },
      { key: 'c', operator: 7, cardId: 2, verb: 'finish' as const, at: 'x', qtyGood: '5' },
    ];
    const shown = applyQueued([card({ id: 1 }), card({ id: 2, status: 'IN_PROGRESS' })], queue);
    expect(shown).toHaveLength(1); // the finished one is gone from the list
    expect(shown[0]).toMatchObject({ id: 1, status: 'IN_PROGRESS', qtyGood: '4', qtyRejected: '1' });
  });
});
