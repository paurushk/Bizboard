import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios';
import { clearTokens, setAccessToken } from '@/auth/session';

// BB-000518: API shapes are defined by backend OpenAPI — see docs/openapi-snapshot.json (CI-generated).

if (import.meta.env.PROD && import.meta.env.VITE_USE_MOCKS === 'true') {
  throw new Error('VITE_USE_MOCKS must not be enabled for production builds');
}

if (import.meta.env.PROD && import.meta.env.VITE_PILOT_ADVANCED === 'true') {
  throw new Error('VITE_PILOT_ADVANCED must not be enabled for production builds');
}

const baseURL =
  import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_BASE || '/api/v1';

/** BB-000055: persisted by useCompanySwitcher for X-Company-Id header. */
export const ACTIVE_COMPANY_STORAGE_KEY = 'bizboard:active-company-id';

function readActiveCompanyId(): string | null {
  if (typeof localStorage === 'undefined') return null;
  const raw = localStorage.getItem(ACTIVE_COMPANY_STORAGE_KEY);
  if (!raw || !/^\d+$/.test(raw)) return null;
  return raw;
}

/** FE-05: default request timeout. Raised from 30s → 60s so ordinary report
 *  builds (GSTR packs) and bill-OCR calls are not aborted while the server is
 *  still working. For the genuinely long operations (full tenant export, large
 *  multi-page OCR) pass `{ timeout: LONG_TIMEOUT_MS }` on the individual call. */
export const DEFAULT_TIMEOUT_MS = 60000;
export const LONG_TIMEOUT_MS = 180000;

export const apiClient = axios.create({
  baseURL,
  headers: { 'Content-Type': 'application/json' },
  timeout: DEFAULT_TIMEOUT_MS,
  withCredentials: true,
});

function readCsrfToken(): string | null {
  if (typeof document === 'undefined') return null;
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

let csrfPromise: Promise<void> | null = null;

// BB-000751: independent callers (request interceptor per unsafe method,
// AuthContext boot, the refresh flow) used to race this on a fresh page load,
// each seeing no cookie yet and firing its own GET — dedup to one in flight.
// Still propagates failure to every awaiter, same as before.
export async function ensureCsrfCookie(force = false): Promise<void> {
  if (!force && readCsrfToken()) return;
  if (!csrfPromise) {
    csrfPromise = axios
      .get(`${baseURL}/auth/csrf/`, { withCredentials: true, timeout: 15000 })
      .then(() => undefined)
      .finally(() => {
        csrfPromise = null;
      });
  }
  await csrfPromise;
  if (!readCsrfToken()) {
    throw new Error('CSRF token is unavailable. Refresh the page and try again.');
  }
}

function applyCsrfHeader(config: InternalAxiosRequestConfig): void {
  const csrf = readCsrfToken();
  if (!csrf) return;
  if (typeof config.headers.set === 'function') {
    config.headers.set('X-CSRFToken', csrf);
  } else {
    (config.headers as Record<string, unknown>)['X-CSRFToken'] = csrf;
  }
}

apiClient.interceptors.request.use(async (config: InternalAxiosRequestConfig) => {
  // BB-000375: rely on httpOnly access cookie (withCredentials). Do not attach Bearer from memory.
  // BB-000602: cookie JWT requires CSRF on unsafe methods.
  const method = (config.method || 'get').toUpperCase();
  if (!['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(method)) {
    try {
      await ensureCsrfCookie();
    } catch {
      await ensureCsrfCookie(true);
    }
    applyCsrfHeader(config);
  }
  const companyId = readActiveCompanyId();
  if (companyId) {
    const hasHeader =
      typeof config.headers.has === 'function'
        ? config.headers.has('X-Company-Id')
        : Boolean((config.headers as Record<string, unknown>)['X-Company-Id']);
    if (!hasHeader) {
      if (typeof config.headers.set === 'function') {
        config.headers.set('X-Company-Id', companyId);
      } else {
        (config.headers as Record<string, unknown>)['X-Company-Id'] = companyId;
      }
    }
  }
  if (typeof FormData !== 'undefined' && config.data instanceof FormData) {
    if (typeof config.headers.delete === 'function') {
      config.headers.delete('Content-Type');
      config.headers.delete('content-type');
    } else {
      delete (config.headers as Record<string, unknown>)['Content-Type'];
      delete (config.headers as Record<string, unknown>)['content-type'];
    }
  }
  return config;
});

let refreshPromise: Promise<string | null> | null = null;
let activeRefreshNotifyOnFailure = false;

function isCsrfFailure(error: AxiosError): boolean {
  if (error.response?.status !== 403) return false;
  const data = error.response.data;
  const blob =
    typeof data === 'string'
      ? data
      : JSON.stringify(data ?? '') + (error.message ?? '');
  return /csrf/i.test(blob);
}

/** BB-000229: never attempt refresh-retry on credential / token endpoints. */
function isAuthCredentialUrl(url?: string): boolean {
  if (!url) return false;
  const path = url.replace(/^https?:\/\/[^/]+/i, '');
  return (
    /\/auth\/login\/?(\?|$)/.test(path) ||
    /\/auth\/register\/?(\?|$)/.test(path) ||
    /\/auth\/refresh\/?(\?|$)/.test(path) ||
    /\/auth\/otp\//.test(path)
  );
}

let lastRefreshSuccessTime = 0;
const MIN_REFRESH_INTERVAL_MS = 5000;

async function doRefresh(opts?: { notifyOnFailure?: boolean }): Promise<string | null> {
  try {
    await ensureCsrfCookie();
    const csrf = readCsrfToken();
    const { data, status } = await axios.post(
      `${baseURL}/auth/refresh/`,
      {},
      {
        withCredentials: true,
        timeout: 15000,
        headers: csrf ? { 'X-CSRFToken': csrf } : undefined,
      },
    );
    if (status >= 200 && status < 300) {
      lastRefreshSuccessTime = Date.now();
      const access = data?.data?.access ?? data?.access;
      const token = typeof access === 'string' && access ? access : 'cookie';
      setAccessToken(token);
      return token;
    }
    return null;
  } catch (err) {
    // BUG-407: only treat HTTP 401/403 from refresh as a real session expiry.
    // Transient network (no response) must not log the user out.
    const status = axios.isAxiosError(err)
      ? err.response?.status
      : err && typeof err === 'object' && 'response' in err
        ? (err as { response?: { status?: number } }).response?.status
        : undefined;
    if (status === 401 || status === 403) {
      clearTokens();
      if (opts?.notifyOnFailure !== false || activeRefreshNotifyOnFailure) {
        window.dispatchEvent(new Event('bizboard:session-expired'));
      }
    }
    return null;
  }
}

/**
 * BB-000257 / BB-000266: silent refresh via httpOnly cookie → in-memory access.
 * Used on boot (memory empty) and on 401 retry.
 * BB-000751: both call sites now share one in-flight request via refreshPromise.
 * Debounced with MIN_REFRESH_INTERVAL_MS to prevent HTTP 429 on rapid navigation.
 */
export async function silentRefreshAccessToken(
  opts?: { notifyOnFailure?: boolean; force?: boolean },
): Promise<string | null> {
  if (!opts?.force && Date.now() - lastRefreshSuccessTime < MIN_REFRESH_INTERVAL_MS) {
    return 'cookie';
  }
  if (opts?.notifyOnFailure !== false) {
    activeRefreshNotifyOnFailure = true;
  }
  if (!refreshPromise) {
    refreshPromise = doRefresh(opts).finally(() => {
      refreshPromise = null;
      activeRefreshNotifyOnFailure = false;
    });
  }
  return refreshPromise;
}

async function refreshAccessToken(): Promise<string | null> {
  return silentRefreshAccessToken({ force: true });
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as InternalAxiosRequestConfig & {
      _retry?: boolean;
      _csrfRetry?: boolean;
    };
    if (
      error.response?.status === 403 &&
      original &&
      !original._csrfRetry &&
      isCsrfFailure(error)
    ) {
      original._csrfRetry = true;
      try {
        await ensureCsrfCookie(true);
        applyCsrfHeader(original);
        return apiClient(original);
      } catch {
        return Promise.reject(error);
      }
    }
    if (
      error.response?.status === 401 &&
      original &&
      !original._retry &&
      !isAuthCredentialUrl(original.url)
    ) {
      original._retry = true;
      // BB-000751: silentRefreshAccessToken() dedups internally now, so a
      // concurrent boot-time refresh (AuthContext) and this 401 retry share
      // one in-flight request instead of firing two.
      const access = await refreshAccessToken();
      if (access) {
        // Cookie refreshed server-side; retry without Bearer.
        return apiClient(original);
      }
    }
    // R5-004: the stored X-Company-Id disagrees with the server's active
    // company (e.g. company switched in another tab). Surface it once so the
    // app shell can re-sync / show a company picker instead of every call
    // failing with a raw 409.
    if (error.response?.status === 409) {
      const body = error.response.data as
        | { error?: { code?: string }; code?: string }
        | undefined;
      const code = body?.error?.code ?? body?.code;
      if (code === 'company_context_conflict') {
        window.dispatchEvent(
          new CustomEvent('bizboard:company-context-conflict', { detail: { url: original?.url } }),
        );
      }
      if (code === 'COMPANY_REQUIRED') {
        const details =
          (body as { error?: { details?: unknown } } | undefined)?.error?.details ?? body;
        window.dispatchEvent(new CustomEvent('bizboard:company-required', { detail: details }));
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

export function isNetworkError(error: unknown): boolean {
  if (!axios.isAxiosError(error)) return false;
  return !error.response || error.code === 'ERR_NETWORK' || error.message === 'Network Error';
}

function formatErrorDetails(details: unknown): string | null {
  if (!details || typeof details !== 'object' || Array.isArray(details)) return null;
  const parts: string[] = [];
  for (const [field, messages] of Object.entries(details as Record<string, unknown>)) {
    if (Array.isArray(messages)) {
      const joined = messages.map(String).filter(Boolean).join(', ');
      if (joined) parts.push(`${field}: ${joined}`);
    } else if (typeof messages === 'string' && messages.trim()) {
      parts.push(`${field}: ${messages.trim()}`);
    } else if (messages != null && typeof messages !== 'object') {
      parts.push(`${field}: ${String(messages)}`);
    }
  }
  return parts.length ? parts.join('; ') : null;
}

function isGenericValidationMessage(msg: string): boolean {
  return /^validation failed\.?$/i.test(msg.trim());
}

function friendlyAuthMessage(raw: string): string {
  const lower = raw.toLowerCase();
  if (
    lower.includes('no active account') ||
    lower.includes('given credentials') ||
    lower.includes('token is invalid') ||
    lower.includes('token_not_valid')
  ) {
    return 'Email or password is incorrect.';
  }
  return raw;
}

export function getErrorCode(error: unknown): string | null {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as Record<string, unknown> | undefined;
    const nested = data?.error;
    if (nested && typeof nested === 'object' && nested !== null) {
      const code = (nested as { code?: unknown }).code;
      if (typeof code === 'string' && code.trim()) return code.trim();
    }
    if (typeof data?.code === 'string' && data.code.trim()) return data.code.trim();
    if (error.response?.status === 403) return 'permission_denied';
  }
  return null;
}

export function getErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as Record<string, unknown> | undefined;
    const nested = data?.error;
    if (nested && typeof nested === 'object' && nested !== null) {
      const envelope = nested as { message?: unknown; details?: unknown };
      const msg = typeof envelope.message === 'string' ? envelope.message.trim() : '';
      const fromDetails = formatErrorDetails(envelope.details);
      if (msg && !isGenericValidationMessage(msg)) return friendlyAuthMessage(msg);
      if (fromDetails) return fromDetails;
      if (msg) return friendlyAuthMessage(msg);
    }
    const topDetails = formatErrorDetails(data?.details);
    if (topDetails) {
      const topMsg = typeof data?.message === 'string' ? data.message.trim() : '';
      if (!topMsg || isGenericValidationMessage(topMsg)) return topDetails;
    }
    for (const candidate of [data?.detail, data?.message, data?.error]) {
      if (typeof candidate === 'string' && candidate.trim()) return friendlyAuthMessage(candidate);
    }
    if (error.message) return friendlyAuthMessage(error.message);
    return 'Request failed';
  }
  if (error instanceof Error) return friendlyAuthMessage(error.message);
  if (typeof error === 'string' && error.trim()) return friendlyAuthMessage(error);
  return 'Unexpected error';
}

export function shouldUseMocks(): boolean {
  if (import.meta.env.PROD) return false;
  return import.meta.env.VITE_USE_MOCKS === 'true';
}

/** BB-000283: UUID Idempotency-Key for create POSTs. */
export function newIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `idem-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
}

/** PD-01: every user Complete/Save/Pay click gets a fresh UUID. Network auto-retry reuses the request header. */
export function userGestureIdempotencyKey(): string {
  return newIdempotencyKey();
}

export function idempotencyHeaders(key?: string): Record<string, string> {
  return { 'Idempotency-Key': key ?? newIdempotencyKey() };
}
