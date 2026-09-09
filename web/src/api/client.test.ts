import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  apiClient,
  getErrorCode,
  getErrorMessage,
  isNetworkError,
  resetApiClientTestState,
  userGestureIdempotencyKey,
} from '@/api/client';
import { clearSession, getAccessToken, getRefreshToken, setAccessToken } from '@/auth/session';

function networkError(message = 'Network Error'): AxiosError {
  return Object.assign(new AxiosError(message), { code: 'ERR_NETWORK' });
}

function unauthorizedConfig(config: InternalAxiosRequestConfig): AxiosError {
  const error = new AxiosError('Unauthorized');
  error.config = config;
  error.response = {
    status: 401,
    data: { detail: 'token expired' },
    headers: {},
    config,
    statusText: 'Unauthorized',
  };
  return error;
}

function clearCsrfCookie(): void {
  document.cookie = 'csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
  resetApiClientTestState();
}

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

describe('refresh token rejection (BUG-407 / P0-111 / R-045)', () => {
  const originalAdapter = apiClient.defaults.adapter;

  beforeEach(() => {
    clearSession();
    resetApiClientTestState();
    setAccessToken('stale-access');
    document.cookie = 'csrftoken=test-csrf';
  });

  afterEach(() => {
    clearSession();
    clearCsrfCookie();
    apiClient.defaults.adapter = originalAdapter;
    vi.restoreAllMocks();
  });

  it('clears tokens and dispatches session-expired on 401 invalid-token', async () => {
    let expired = false;
    const onExpired = () => {
      expired = true;
    };
    window.addEventListener('bizboard:session-expired', onExpired);

    vi.spyOn(axios, 'post').mockRejectedValueOnce(
      Object.assign(new Error('refresh rejected'), {
        response: {
          status: 401,
          data: { error: { code: 'token_not_valid', message: 'Invalid refresh token.' } },
        },
      }),
    );

    apiClient.defaults.adapter = async (config) => {
      throw unauthorizedConfig(config as InternalAxiosRequestConfig);
    };

    await expect(apiClient.get('/customers/')).rejects.toBeTruthy();
    expect(getAccessToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();
    expect(expired).toBe(true);

    window.removeEventListener('bizboard:session-expired', onExpired);
  });

  it('R-045: retries refresh once on network error and does not clear session', async () => {
    let expired = false;
    const onExpired = () => {
      expired = true;
    };
    window.addEventListener('bizboard:session-expired', onExpired);

    const postSpy = vi.spyOn(axios, 'post').mockRejectedValue(networkError());

    apiClient.defaults.adapter = async (config) => {
      throw unauthorizedConfig(config as InternalAxiosRequestConfig);
    };

    await expect(apiClient.get('/customers/')).rejects.toBeTruthy();
    expect(postSpy).toHaveBeenCalledTimes(2);
    expect(getAccessToken()).toBe('cookie');
    expect(expired).toBe(false);

    window.removeEventListener('bizboard:session-expired', onExpired);
  });

  it('R-045: network then successful refresh retries the original request', async () => {
    const postSpy = vi
      .spyOn(axios, 'post')
      .mockRejectedValueOnce(networkError())
      .mockResolvedValueOnce({ status: 200, data: { access: 'fresh-access' } } as never);

    let calls = 0;
    apiClient.defaults.adapter = async (config) => {
      calls += 1;
      if (calls === 1) throw unauthorizedConfig(config as InternalAxiosRequestConfig);
      return {
        status: 200,
        statusText: 'OK',
        headers: {},
        config: config as InternalAxiosRequestConfig,
        data: { success: true, data: [{ id: 1 }] },
      };
    };

    const resp = await apiClient.get('/customers/');
    expect(postSpy).toHaveBeenCalledTimes(2);
    expect(calls).toBe(2);
    expect(resp.data).toEqual({ success: true, data: [{ id: 1 }] });
    expect(getAccessToken()).toBe('cookie');
  });

  it('R-045: 403 CSRF on refresh does not logout or purge session', async () => {
    let expired = false;
    const onExpired = () => {
      expired = true;
    };
    window.addEventListener('bizboard:session-expired', onExpired);

    vi.spyOn(axios, 'post').mockRejectedValueOnce(
      Object.assign(new AxiosError('Forbidden'), {
        response: { status: 403, data: { detail: 'CSRF Failed: CSRF token missing.' } },
      }),
    );

    apiClient.defaults.adapter = async (config) => {
      throw unauthorizedConfig(config as InternalAxiosRequestConfig);
    };

    await expect(apiClient.get('/customers/')).rejects.toBeTruthy();
    expect(getAccessToken()).toBe('cookie');
    expect(expired).toBe(false);

    window.removeEventListener('bizboard:session-expired', onExpired);
  });

  it('R-045: 401 without invalid-token language does not logout', async () => {
    let expired = false;
    const onExpired = () => {
      expired = true;
    };
    window.addEventListener('bizboard:session-expired', onExpired);

    vi.spyOn(axios, 'post').mockRejectedValueOnce(
      Object.assign(new AxiosError('Unauthorized'), {
        response: {
          status: 401,
          data: { error: { code: 'authentication_failed', message: 'Refresh token required.' } },
        },
      }),
    );

    apiClient.defaults.adapter = async (config) => {
      throw unauthorizedConfig(config as InternalAxiosRequestConfig);
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
    clearCsrfCookie();
    const getSpy = vi.spyOn(axios, 'get').mockResolvedValue({
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
    expect(getSpy).toHaveBeenCalled();
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

  it('R-046: CSRF fetch failure does not send the mutate without a header', async () => {
    clearCsrfCookie();
    const getSpy = vi.spyOn(axios, 'get').mockRejectedValue(networkError());

    let mutateCalls = 0;
    apiClient.defaults.adapter = async () => {
      mutateCalls += 1;
      return {
        status: 200,
        statusText: 'OK',
        headers: {},
        config: {} as InternalAxiosRequestConfig,
        data: { success: true },
      };
    };

    await expect(apiClient.post('/customers/', { name: 'X' })).rejects.toMatchObject({
      code: 'ERR_NETWORK',
    });
    expect(mutateCalls).toBe(0);
    expect(getSpy).toHaveBeenCalled();
    expect(getAccessToken()).toBe('cookie');
  });

  it('R-046: CSRF unavailable Error is treated as queueable by isNetworkError', async () => {
    clearCsrfCookie();
    vi.spyOn(axios, 'get').mockResolvedValue({
      status: 200,
      data: {},
    } as never);

    let mutateCalls = 0;
    apiClient.defaults.adapter = async () => {
      mutateCalls += 1;
      return {
        status: 200,
        statusText: 'OK',
        headers: {},
        config: {} as InternalAxiosRequestConfig,
        data: { success: true },
      };
    };

    let caught: unknown;
    try {
      await apiClient.post('/customers/', { name: 'X' });
    } catch (err) {
      caught = err;
    }
    expect(mutateCalls).toBe(0);
    expect(caught).toBeInstanceOf(Error);
    expect(isNetworkError(caught)).toBe(true);
  });
});

describe('isNetworkError', () => {
  it('returns true for CSRF unavailable rejects so outbox callers queue', () => {
    expect(
      isNetworkError(
        new Error(
          'CSRF token is unavailable. If the app and API are on different domains, ' +
            'your browser may be blocking third-party cookies — host them on the same ' +
            'site, or refresh the page and try again.',
        ),
      ),
    ).toBe(true);
  });

  it('returns true for Axios network errors and false for business 400s', () => {
    expect(isNetworkError(networkError())).toBe(true);
    const bad = new AxiosError('Bad Request');
    bad.response = { status: 400, data: {}, headers: {}, config: {} as never, statusText: 'Bad' };
    expect(isNetworkError(bad)).toBe(false);
    expect(isNetworkError(new Error('unrelated'))).toBe(false);
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
