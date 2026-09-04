import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { apiClient, getErrorCode, getErrorMessage, userGestureIdempotencyKey } from '@/api/client';
import { clearSession, getAccessToken, getRefreshToken, setAccessToken } from '@/auth/session';

describe('getErrorMessage', () => {
  it('reads message from Bizboard error envelope', () => {
    const err = new axios.AxiosError('Request failed with status code 400');
    err.response = {
      data: {
        success: false,
        error: {
          code: 'business_rule_violation',
          message: 'Insufficient stock for Demo Widget',
          details: { detail: 'Insufficient stock for Demo Widget' },
        },
      },
    } as never;
    expect(getErrorMessage(err)).toBe('Insufficient stock for Demo Widget');
  });

  it('never returns a non-string object when error payload is nested', () => {
    const err = new axios.AxiosError('Request failed with status code 400');
    err.response = {
      data: {
        error: { code: 'x', message: 'Nope', details: { a: 1 } },
      },
    } as never;
    const msg = getErrorMessage(err);
    expect(typeof msg).toBe('string');
    expect(msg).toBe('Nope');
  });

  it('joins field details when message is generic Validation failed', () => {
    const err = new axios.AxiosError('Request failed with status code 400');
    err.response = {
      data: {
        success: false,
        error: {
          code: 'validation_error',
          message: 'Validation failed.',
          details: { gstin: ['Enter a valid GSTIN.'], phone: ['Required.'] },
        },
      },
    } as never;
    expect(getErrorMessage(err)).toBe('gstin: Enter a valid GSTIN.; phone: Required.');
  });

  it('falls back for plain errors', () => {
    expect(getErrorMessage(new Error('boom'))).toBe('boom');
    expect(getErrorMessage('plain')).toBe('plain');
  });
});

describe('getErrorCode', () => {
  it('reads code from the Bizboard error envelope', () => {
    const err = new axios.AxiosError('Request failed with status code 400');
    err.response = {
      data: {
        success: false,
        error: { code: 'insufficient_stock', message: 'No stock' },
      },
    } as never;
    expect(getErrorCode(err)).toBe('insufficient_stock');
  });

  it('maps HTTP 403 to permission_denied', () => {
    const err = new axios.AxiosError('Request failed with status code 403');
    err.response = { status: 403, data: {} } as never;
    expect(getErrorCode(err)).toBe('permission_denied');
  });

  it('returns null when unmapped', () => {
    expect(getErrorCode(new Error('boom'))).toBeNull();
  });
});

describe('refresh token rejection (BUG-407 / P0-111)', () => {
  const originalAdapter = apiClient.defaults.adapter;

  beforeEach(() => {
    clearSession();
    setAccessToken('stale-access');
  });

  afterEach(() => {
    clearSession();
    apiClient.defaults.adapter = originalAdapter;
    vi.restoreAllMocks();
  });

  it('clears tokens and dispatches session-expired when refresh returns 401', async () => {
    document.cookie = 'csrftoken=test-csrf';
    let expired = false;
    const onExpired = () => {
      expired = true;
    };
    window.addEventListener('bizboard:session-expired', onExpired);

    vi.spyOn(axios, 'post').mockRejectedValueOnce(
      Object.assign(new Error('refresh rejected'), { response: { status: 401 } }),
    );

    apiClient.defaults.adapter = async (config) => {
      const error = new AxiosError('Unauthorized');
      error.config = config as InternalAxiosRequestConfig;
      error.response = {
        status: 401,
        data: { detail: 'token expired' },
        headers: {},
        config: config as InternalAxiosRequestConfig,
        statusText: 'Unauthorized',
      };
      throw error;
    };

    await expect(apiClient.get('/customers/')).rejects.toBeTruthy();
    expect(getAccessToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();
    expect(expired).toBe(true);

    window.removeEventListener('bizboard:session-expired', onExpired);
  });

  it('does not clear session on a transient network error (no response)', async () => {
    document.cookie = 'csrftoken=test-csrf';
    let expired = false;
    const onExpired = () => {
      expired = true;
    };
    window.addEventListener('bizboard:session-expired', onExpired);

    vi.spyOn(axios, 'post').mockRejectedValueOnce(
      Object.assign(new AxiosError('Network Error'), { code: 'ERR_NETWORK' }),
    );

    apiClient.defaults.adapter = async (config) => {
      const error = new AxiosError('Unauthorized');
      error.config = config as InternalAxiosRequestConfig;
      error.response = {
        status: 401,
        data: { detail: 'token expired' },
        headers: {},
        config: config as InternalAxiosRequestConfig,
        statusText: 'Unauthorized',
      };
      throw error;
    };

    await expect(apiClient.get('/customers/')).rejects.toBeTruthy();
    expect(getAccessToken()).toBe('cookie');
    expect(expired).toBe(false);

    window.removeEventListener('bizboard:session-expired', onExpired);
  });

  it('F1-016: retries the original request after a successful 401 refresh', async () => {
    document.cookie = 'csrftoken=test-csrf';
    vi.spyOn(axios, 'post').mockResolvedValueOnce({
      status: 200,
      data: { access: 'fresh-access' },
    } as never);

    let calls = 0;
    apiClient.defaults.adapter = async (config) => {
      calls += 1;
      if (calls === 1) {
        const error = new AxiosError('Unauthorized');
        error.config = config as InternalAxiosRequestConfig;
        error.response = {
          status: 401,
          data: { detail: 'token expired' },
          headers: {},
          config: config as InternalAxiosRequestConfig,
          statusText: 'Unauthorized',
        };
        throw error;
      }
      return {
        status: 200,
        statusText: 'OK',
        headers: {},
        config: config as InternalAxiosRequestConfig,
        data: { success: true, data: [{ id: 1 }] },
      };
    };

    const resp = await apiClient.get('/customers/');
    expect(calls).toBe(2);
    expect(resp.data).toEqual({ success: true, data: [{ id: 1 }] });
    // getAccessToken() is a "session established" sentinel under cookie auth
    // (see auth/session.ts setAccessToken — the actual token string is never
    // surfaced/stored), so the only meaningful assertion here is that a
    // session was established at all, not the literal refreshed value.
    expect(getAccessToken()).toBe('cookie');
  });

  it('F1-016: the _retry guard stops a second refresh when the retried request still 401s', async () => {
    document.cookie = 'csrftoken=test-csrf';
    const postSpy = vi
      .spyOn(axios, 'post')
      .mockResolvedValueOnce({ status: 200, data: { access: 'fresh-access' } } as never);

    apiClient.defaults.adapter = async (config) => {
      const error = new AxiosError('Unauthorized');
      error.config = config as InternalAxiosRequestConfig;
      error.response = {
        status: 401,
        data: { detail: 'token expired' },
        headers: {},
        config: config as InternalAxiosRequestConfig,
        statusText: 'Unauthorized',
      };
      throw error;
    };

    await expect(apiClient.get('/customers/')).rejects.toBeTruthy();
    // Refresh fired exactly once — the retried request's own 401 does not
    // trigger a second refresh (original._retry is already set), so this
    // never loops.
    expect(postSpy).toHaveBeenCalledTimes(1);
  });

  it('F1-016: a CSRF-shaped 403 auto-retries once after re-fetching the CSRF cookie', async () => {
    document.cookie = '';
    const getSpy = vi.spyOn(axios, 'get').mockResolvedValueOnce({
      status: 200,
      data: { csrfToken: 'fresh-csrf' },
    } as never);

    let calls = 0;
    apiClient.defaults.adapter = async (config) => {
      calls += 1;
      if (calls === 1) {
        const error = new AxiosError('Forbidden');
        error.config = config as InternalAxiosRequestConfig;
        error.response = {
          status: 403,
          data: { error: { code: 'csrf_failed', message: 'CSRF Failed: CSRF token missing.' } },
          headers: {},
          config: config as InternalAxiosRequestConfig,
          statusText: 'Forbidden',
        };
        throw error;
      }
      return {
        status: 200,
        statusText: 'OK',
        headers: {},
        config: config as InternalAxiosRequestConfig,
        data: { success: true },
      };
    };

    const resp = await apiClient.post('/customers/', { name: 'X' });
    expect(calls).toBe(2);
    expect(resp.data).toEqual({ success: true });
    expect(getSpy).toHaveBeenCalledTimes(1);
  });

  it('F1-016: silentRefreshAccessToken debounces within MIN_REFRESH_INTERVAL_MS and returns "cookie"', async () => {
    document.cookie = 'csrftoken=test-csrf';
    // `mockResolvedValue` (not `...Once`): a debounce bug that lets a second
    // network call through must not fall out of the mock and hit a real URL.
    const postSpy = vi
      .spyOn(axios, 'post')
      .mockResolvedValue({ status: 200, data: { access: 'fresh-access' } } as never);

    const { silentRefreshAccessToken } = await import('@/api/client');
    // `force: true` guarantees a real refresh here regardless of whatever
    // `lastRefreshSuccessTime` a previous test in this file left behind —
    // the debounce guarantee under test is about the *next* call only.
    await silentRefreshAccessToken({ force: true });
    const callsAfterFirst = postSpy.mock.calls.length;

    const second = await silentRefreshAccessToken();
    expect(second).toBe('cookie');
    expect(postSpy.mock.calls.length).toBe(callsAfterFirst);
  });

  it('BB-000229: does not refresh-retry failed login', async () => {
    const postSpy = vi.spyOn(axios, 'post');

    apiClient.defaults.adapter = async (config) => {
      const error = new AxiosError('Unauthorized');
      error.config = config as InternalAxiosRequestConfig;
      error.response = {
        status: 401,
        data: { detail: 'bad credentials' },
        headers: {},
        config: config as InternalAxiosRequestConfig,
        statusText: 'Unauthorized',
      };
      throw error;
    };

    await expect(apiClient.post('/auth/login/', { email: 'a', password: 'b' })).rejects.toBeTruthy();
    expect(postSpy).not.toHaveBeenCalled();
  });
});

describe('PD-01 user-gesture idempotency keys', () => {
  it('second Complete click is not the same UUID', () => {
    const a = userGestureIdempotencyKey();
    const b = userGestureIdempotencyKey();
    expect(a).not.toBe(b);
    expect(a.length).toBeGreaterThan(8);
  });
});
