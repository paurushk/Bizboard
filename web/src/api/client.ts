import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios';
import { clearTokens, getAccessToken, getRefreshToken, setTokens } from '@/auth/session';

const baseURL = import.meta.env.VITE_API_BASE_URL || '/api/v1';

export const apiClient = axios.create({
  baseURL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 30000,
});

apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  // Default JSON Content-Type breaks multipart uploads (missing boundary).
  if (typeof FormData !== 'undefined' && config.data instanceof FormData) {
    if (typeof config.headers.set === 'function') {
      config.headers.set('Content-Type', false as unknown as string);
    } else {
      delete (config.headers as Record<string, unknown>)['Content-Type'];
      delete (config.headers as Record<string, unknown>)['content-type'];
    }
  }
  return config;
});

let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  const refresh = getRefreshToken();
  if (!refresh) return null;
  try {
    const { data } = await axios.post(`${baseURL}/auth/refresh/`, { refresh });
    const access = data?.data?.access ?? data?.access;
    const nextRefresh = data?.data?.refresh ?? data?.refresh ?? refresh;
    if (!access) return null;
    setTokens({ access, refresh: nextRefresh });
    return access as string;
  } catch {
    clearTokens();
    // BUG-407: previously nothing told AuthContext the session died here —
    // the app kept rendering as "logged in" while every subsequent request
    // silently 401'd, with no forced navigation back to /login.
    window.dispatchEvent(new Event('bizboard:session-expired'));
    return null;
  }
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as InternalAxiosRequestConfig & { _retry?: boolean };
    if (error.response?.status === 401 && original && !original._retry) {
      original._retry = true;
      refreshPromise = refreshPromise ?? refreshAccessToken().finally(() => {
        refreshPromise = null;
      });
      const access = await refreshPromise;
      if (access) {
        original.headers.Authorization = `Bearer ${access}`;
        return apiClient(original);
      }
    }
    return Promise.reject(error);
  },
);

export function unwrapData<T>(payload: unknown): T {
  if (payload && typeof payload === 'object' && 'data' in payload) {
    return (payload as { data: T }).data;
  }
  return payload as T;
}

export function getErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as Record<string, unknown> | undefined;
    const nested = data?.error;
    if (nested && typeof nested === 'object' && nested !== null) {
      const msg = (nested as { message?: unknown }).message;
      if (typeof msg === 'string' && msg.trim()) return msg;
    }
    for (const candidate of [data?.detail, data?.message, data?.error]) {
      if (typeof candidate === 'string' && candidate.trim()) return candidate;
    }
    if (error.message) return error.message;
    return 'Request failed';
  }
  if (error instanceof Error) return error.message;
  if (typeof error === 'string' && error.trim()) return error;
  return 'Unexpected error';
}

export function shouldUseMocks(): boolean {
  return import.meta.env.VITE_USE_MOCKS === 'true';
}
