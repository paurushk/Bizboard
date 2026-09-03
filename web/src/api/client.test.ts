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
