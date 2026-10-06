import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { apiClient, resetApiClientTestState } from '@/api/client';
import { clearSession, setAccessToken } from '@/auth/session';

// F-SEC-02: a wrong authenticator code answers 401. That is a credential failure, exactly like a
// wrong password on /auth/login/, NOT an expired session: the client must not try to refresh the
// session (which would also fire the session-expired logout path) before showing "wrong code".

function unauthorized(config: InternalAxiosRequestConfig): AxiosError {
  const error = new AxiosError('Unauthorized');
  error.config = config;
  error.response = {
    status: 401,
    data: { success: false, error: { code: 'authentication_failed', message: 'That verification code is not valid.' } },
    headers: {},
    config,
    statusText: 'Unauthorized',
  };
  return error;
}

describe('401 handling for credential endpoints', () => {
  const originalAdapter = apiClient.defaults.adapter;

  beforeEach(() => {
    clearSession();
    resetApiClientTestState();
    setAccessToken('stale-access');
    document.cookie = 'csrftoken=test-csrf';
  });

  afterEach(() => {
    clearSession();
    resetApiClientTestState();
    apiClient.defaults.adapter = originalAdapter;
    vi.restoreAllMocks();
  });

  async function run(url: string) {
    const refresh = vi.spyOn(axios, 'post').mockRejectedValue(new Error('refresh blocked in test'));
    let expired = false;
    const onExpired = () => {
      expired = true;
    };
    window.addEventListener('bizboard:session-expired', onExpired);
    apiClient.defaults.adapter = async (config) => {
      throw unauthorized(config as InternalAxiosRequestConfig);
    };
    await expect(apiClient.post(url, {})).rejects.toBeTruthy();
    window.removeEventListener('bizboard:session-expired', onExpired);
    return { refreshCalls: refresh.mock.calls.length, expired };
  }

  it('a wrong MFA code (401 on /auth/mfa/verify/) does not trigger a session refresh or logout', async () => {
    const { refreshCalls, expired } = await run('/auth/mfa/verify/');
    expect(refreshCalls).toBe(0);
    expect(expired).toBe(false);
  });

  it('the same holds for the existing credential endpoints (login stays excluded)', async () => {
    const { refreshCalls, expired } = await run('/auth/login/');
    expect(refreshCalls).toBe(0);
    expect(expired).toBe(false);
  });

  it('other MFA management endpoints are NOT credential urls: a 401 there is a real expired session', async () => {
    // /auth/mfa/status/ needs a session, so an expired one should be refreshed like any other call.
    const { refreshCalls } = await run('/auth/mfa/status/');
    expect(refreshCalls).toBeGreaterThan(0);
  });
});
