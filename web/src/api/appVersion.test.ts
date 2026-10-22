import { AxiosHeaders, type InternalAxiosRequestConfig } from 'axios';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { apiClient, nativeAppVersion } from '@/api/client';

async function runRequestInterceptors(): Promise<InternalAxiosRequestConfig> {
  let config = { method: 'get', url: '/auth/me/', headers: new AxiosHeaders() } as InternalAxiosRequestConfig;
  const handlers = (apiClient.interceptors.request as unknown as {
    handlers: ({ fulfilled: (c: InternalAxiosRequestConfig) => Promise<InternalAxiosRequestConfig> } | null)[];
  }).handlers;
  for (const h of handlers) {
    if (h) config = await h.fulfilled(config);
  }
  return config;
}

describe('X-App-Version (WP-L1)', () => {
  afterEach(() => {
    delete (window as unknown as { Capacitor?: unknown }).Capacitor;
  });

  it('is not sent from the browser', async () => {
    const config = await runRequestInterceptors();
    expect(config.headers.get('X-App-Version')).toBeUndefined();
  });

  it('is sent from the native shell, with the build from its user agent', async () => {
    (window as unknown as { Capacitor: unknown }).Capacitor = { isNativePlatform: () => true };
    const ua = vi.spyOn(navigator, 'userAgent', 'get').mockReturnValue('Mozilla/5.0 (Linux; Android 14) BizBoardApp/1.4.2');
    expect(nativeAppVersion()).toBe('1.4.2');
    const config = await runRequestInterceptors();
    expect(config.headers.get('X-App-Version')).toBe('1.4.2');
    ua.mockRestore();
  });
});
