import { apiClient, shouldUseMocks, unwrapData } from './client';
import { getRefreshToken, setTokens } from '@/auth/session';
import { mockSalesUser, mockUser } from '@/mocks/data';
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
}

export async function login(payload: LoginPayload): Promise<{ user: User; tokens: AuthTokens }> {
  if (shouldUseMocks()) {
    await delay(300);
    const user =
      payload.email.toLowerCase().includes('sales') ? mockSalesUser : mockUser;
    return {
      user,
      tokens: { access: 'mock-access', refresh: 'mock-refresh' },
    };
  }

  const { data } = await apiClient.post('/auth/login/', payload);
  const body = unwrapData<{ user: User; access: string; refresh: string }>(data);
  if (!body.access || !body.refresh) {
    throw new Error('Login response missing tokens');
  }
  let user = body.user;
  if (!user) {
    user = await fetchCurrentUser();
  }
  return {
    user,
    tokens: { access: body.access, refresh: body.refresh },
  };
}

export async function register(
  payload: RegisterPayload,
): Promise<{ user: User; tokens: AuthTokens }> {
  if (shouldUseMocks()) {
    await delay(300);
    return {
      user: { ...mockUser, email: payload.email, fullName: payload.fullName ?? mockUser.fullName },
      tokens: { access: 'mock-access', refresh: 'mock-refresh' },
    };
  }

  const { data } = await apiClient.post('/auth/register/', payload);
  const body = unwrapData<{ access: string; refresh: string; userId: number; companyId: number }>(
    data,
  );
  const tokens = { access: body.access, refresh: body.refresh };
  setTokens(tokens);
  const user = await fetchCurrentUser();
  return { user, tokens };
}

export async function requestOtp(phone: string): Promise<{ detail: string; debugCode?: string }> {
  if (shouldUseMocks()) {
    return { detail: 'OTP sent.', debugCode: '123456' };
  }
  const { data } = await apiClient.post('/auth/otp/request/', { phone });
  return unwrapData(data);
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
  const body = unwrapData<{ user?: User; access: string; refresh: string }>(data);
  const tokens = { access: body.access, refresh: body.refresh };
  setTokens(tokens);
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
    const refresh = getRefreshToken();
    await apiClient.post('/auth/logout/', refresh ? { refresh } : {});
  } catch {
    // ignore network errors on logout
  }
}

function delay(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}
