import { apiClient, shouldUseMocks, unwrapData } from './client';
import { setAccessToken } from '@/auth/session';
import { mockSalesUser, mockUser, mockViewerUser } from '@/mocks/data';
import type { AuthTokens, User } from '@/types/domain';

export interface LoginPayload {
  email: string;
  password: string;
}

export interface RegisterPayload {
  companyName: string;
  email: string;
  password: string;
  fullName?: string;
  phone?: string;
  state?: string;
  gstin?: string;
}

function tokensFromBody(body: { access?: string | null; refresh?: string }): AuthTokens {
  if (body.access) {
    return { access: body.access, refresh: body.refresh };
  }
  // BB-000602: production cookie mode returns access:null; httpOnly bb_access is the session.
  return { access: 'cookie', refresh: body.refresh };
}

export async function login(payload: LoginPayload): Promise<{ user: User; tokens: AuthTokens }> {
  if (shouldUseMocks()) {
    await delay(300);
    const email = payload.email.toLowerCase();
    const user = email.includes('viewer')
      ? mockViewerUser
      : email.includes('sales')
        ? mockSalesUser
        : mockUser;
    return {
      user,
      tokens: { access: 'mock-access', refresh: 'mock-refresh' },
    };
  }

  const { data } = await apiClient.post('/auth/login/', payload);
  const body = unwrapData<{ user: User; access: string; refresh?: string }>(data);
  const tokens = tokensFromBody(body);
  let user = body.user;
  if (!user) {
    setAccessToken(tokens.access);
    user = await fetchCurrentUser();
  }
  return { user, tokens };
}

export type RegisterResult =
  | { kind: 'session'; user: User; tokens: AuthTokens }
  | { kind: 'pending'; detail: string };

export async function register(payload: RegisterPayload): Promise<RegisterResult> {
  if (shouldUseMocks()) {
    await delay(300);
    return {
      kind: 'session',
      user: { ...mockUser, email: payload.email, fullName: payload.fullName ?? mockUser.fullName },
      tokens: { access: 'mock-access', refresh: 'mock-refresh' },
    };
  }

  const { data } = await apiClient.post('/auth/register/', payload);
  const body = unwrapData<{
    access?: string;
    refresh?: string;
    userId?: number;
    companyId?: number;
    detail?: string;
  }>(data);
  // BB-000251: duplicate email returns 200 without tokens (non-enumerating).
  if (!body.access) {
    return {
      kind: 'pending',
      detail: body.detail || 'If this email can be registered, an account has been prepared.',
    };
  }
  const tokens = tokensFromBody(body);
  setAccessToken(tokens.access);
  const user = await fetchCurrentUser();
  return { kind: 'session', user, tokens };
}

export async function requestOtp(phone: string): Promise<{ detail: string; debugCode?: string }> {
  if (shouldUseMocks()) {
    // Only echo a debug code in DEV mocks — production mock path must not invent one.
    return import.meta.env.DEV
      ? { detail: 'OTP sent.', debugCode: '123456' }
      : { detail: 'OTP sent.' };
  }
  const { data } = await apiClient.post('/auth/otp/request/', { phone });
  const body = unwrapData<{ detail: string; debugCode?: string; debug_code?: string }>(data);
  return {
    detail: body.detail,
    debugCode: body.debugCode ?? body.debug_code,
  };
}

export async function verifyOtp(
  phone: string,
  code: string,
): Promise<{ user: User; tokens: AuthTokens }> {
  if (shouldUseMocks()) {
    return {
      user: mockUser,
      tokens: { access: 'mock-access', refresh: 'mock-refresh' },
    };
  }
  const { data } = await apiClient.post('/auth/otp/verify/', { phone, code });
  const body = unwrapData<{ user?: User; access: string; refresh?: string }>(data);
  const tokens = tokensFromBody(body);
  setAccessToken(tokens.access);
  let user = body.user;
  if (!user) {
    user = await fetchCurrentUser();
  }
  return { user, tokens };
}

export async function fetchCurrentUser(): Promise<User> {
  if (shouldUseMocks()) {
    await delay(100);
    return mockUser;
  }
  const { data } = await apiClient.get('/auth/me/');
  return unwrapData<User>(data);
}

export async function logout(): Promise<void> {
  if (shouldUseMocks()) return;
  try {
    // Refresh cookie cleared server-side; withCredentials sends the cookie.
    await apiClient.post('/auth/logout/', {});
  } catch {
    // ignore network errors on logout
  }
}

function delay(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}
