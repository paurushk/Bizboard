import { AxiosError } from 'axios';
import { describe, expect, it } from 'vitest';
import { AttemptKeys } from './attemptKeys';

function httpError(status: number, data: unknown = {}): AxiosError {
  const error = new AxiosError('failed');
  error.response = { status, data, statusText: '', headers: {}, config: {} as never };
  return error;
}

describe('AttemptKeys', () => {
  it('hands out the same key until the attempt is settled', () => {
    const keys = new AttemptKeys();
    expect(keys.get('dispatch-5')).toBe(keys.get('dispatch-5'));
  });

  it('gives a different key per action name', () => {
    const keys = new AttemptKeys();
    expect(keys.get('dispatch-5')).not.toBe(keys.get('dispatch-6'));
  });

  it('starts a new attempt after success', () => {
    const keys = new AttemptKeys();
    const first = keys.get('a');
    keys.settle('a');
    expect(keys.get('a')).not.toBe(first);
  });

  it('starts a new attempt after the server refused (4xx), so a corrected retry is not blocked', () => {
    const keys = new AttemptKeys();
    const first = keys.get('a');
    keys.settle('a', httpError(400, { error: { code: 'insufficient_stock' } }));
    expect(keys.get('a')).not.toBe(first);
  });

  it('keeps the key when the outcome is unknown: network error, 5xx, 429, in-flight 409', () => {
    const keys = new AttemptKeys();
    const first = keys.get('a');
    keys.settle('a', new AxiosError('Network Error', 'ERR_NETWORK'));
    keys.settle('a', httpError(502));
    keys.settle('a', httpError(429));
    keys.settle('a', httpError(409, { error: { code: 'idempotency_in_flight' } }));
    expect(keys.get('a')).toBe(first);
  });
});
