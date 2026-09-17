import { AxiosError } from 'axios';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { classifyCompleteFailure, trackJourneyFailed, trackJourneyStarted } from './telemetry';

vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>();
  return {
    ...actual,
    getLastRequestId: () => 'rid-from-complete',
    apiClient: { post: vi.fn().mockResolvedValue({ data: { ok: true } }), get: vi.fn() },
  };
});

describe('classifyCompleteFailure', () => {
  it('maps 5xx / timeout / offline / 4xx', () => {
    const five = new AxiosError('server');
    five.response = { status: 500, data: {}, headers: {}, config: {} as never, statusText: 'E' };
    expect(classifyCompleteFailure(five)).toBe('5xx');

    const timeout = new AxiosError('timeout of 60000ms exceeded');
    timeout.code = 'ECONNABORTED';
    expect(classifyCompleteFailure(timeout)).toBe('timeout');

    const offline = Object.assign(new AxiosError('Network Error'), { code: 'ERR_NETWORK' });
    expect(classifyCompleteFailure(offline)).toBe('offline');

    const four = new AxiosError('bad');
    four.response = {
      status: 400,
      data: { error: { code: 'validation_error', message: 'Validation failed.' } },
      headers: {},
      config: {} as never,
      statusText: 'Bad',
    };
    expect(classifyCompleteFailure(four)).toBe('validation');

    const help = new AxiosError('blocked');
    help.response = {
      status: 400,
      data: { error: { code: 'insufficient_stock', message: 'Insufficient stock' } },
      headers: {},
      config: {} as never,
      statusText: 'Bad',
    };
    expect(classifyCompleteFailure(help)).toBe('help_code');
  });
});

describe('journey events', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('POSTs journey_started and journey_failed with request_id and required reason', async () => {
    const { apiClient } = await import('@/api/client');
    const post = apiClient.post as ReturnType<typeof vi.fn>;
    trackJourneyStarted('invoice_complete', 'pos');
    trackJourneyFailed('invoice_complete', 'validation', { durationMs: 12, feature: 'pos' });
    await Promise.resolve();
    const events = post.mock.calls.map((c) => c[1] as Record<string, unknown>);
    expect(events[0]).toMatchObject({
      event: 'journey_started',
      journey: 'invoice_complete',
      feature: 'pos',
      request_id: 'rid-from-complete',
    });
    expect(events[1]).toMatchObject({
      event: 'journey_failed',
      journey: 'invoice_complete',
      failure_reason: 'validation',
      success: false,
      request_id: 'rid-from-complete',
    });
    expect(events[0]).not.toHaveProperty('gstin');
    expect(events[0]).not.toHaveProperty('company_id');
    expect(events[1]).not.toHaveProperty('company_hash');
  });
});
