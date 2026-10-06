import { apiClient, shouldUseMocks, unwrapData } from './client';
import { getStoredUser, setAccessToken } from '@/auth/session';
import {
  mockAccountantAccountingUser,
  mockAccountantUser,
  mockOwnerAccountingUser,
  mockOwnerEmptyGstinUser,
  mockOwnerStockBlockUser,
  mockOwnerWritesBlockedUser,
  mockAuditorUser,
  mockInventoryUser,
  mockManagerUser,
  mockPolicyDeskUser,
  mockSalesUser,
  mockUser,
  mockViewerUser,
} from '@/mocks/data';
import type { AuthTokens, User } from '@/types/domain';

/** Same email-substring convention login() uses to pick a mock persona —
 * shared so fetchCurrentUser() resolves the actually-logged-in mock user
 * instead of always defaulting to OWNER. A "books-on" email opts into the
 * accountingEnabled:true company variant (see mocks/data.ts) instead of the
 * shared books-off default every other persona uses. */
export function mockUserForEmail(email: string): User {
  const lower = email.toLowerCase();
  if (lower.includes('books-on')) {
    return lower.includes('accountant') ? mockAccountantAccountingUser : mockOwnerAccountingUser;
  }
  if (lower.includes('empty-gstin')) return mockOwnerEmptyGstinUser;
  if (lower.includes('stock-block')) return mockOwnerStockBlockUser;
  if (lower.includes('writes-blocked')) return mockOwnerWritesBlockedUser;
  if (lower.includes('policy')) return mockPolicyDeskUser;
  if (lower.includes('auditor')) return mockAuditorUser;
  if (lower.includes('manager')) return mockManagerUser;
  if (lower.includes('viewer')) return mockViewerUser;
  if (lower.includes('sales')) return mockSalesUser;
  if (lower.includes('warehouse') || lower.includes('inventory')) return mockInventoryUser;
  if (lower.includes('accountant')) return mockAccountantUser;
  return mockUser;
}

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
  otpCode: string;
}

function tokensFromBody(body: { access?: string | null; refresh?: string }): AuthTokens {
  if (body.access) {
    return { access: body.access, refresh: body.refresh };
  }
  // BB-000602: production cookie mode returns access:null; httpOnly bb_access is the session.
  return { access: 'cookie', refresh: body.refresh };
}

/** Thrown by login()/verifyOtp() when the account has two-step verification enabled. */
export class MfaRequiredError extends Error {
  readonly mfaToken: string;
  constructor(mfaToken: string) {
    super('Two-step verification required');
    this.name = 'MfaRequiredError';
    this.mfaToken = mfaToken;
  }
}

function throwIfMfaRequired(body: { mfaRequired?: boolean; mfaToken?: string }): void {
  if (body.mfaRequired && body.mfaToken) throw new MfaRequiredError(body.mfaToken);
}

/** Thrown when a money role must enrol before any session is issued. */
export class MfaEnrollmentRequiredError extends Error {
  readonly enrolToken: string;
  constructor(enrolToken: string) {
    super('Two-step enrolment required');
    this.name = 'MfaEnrollmentRequiredError';
    this.enrolToken = enrolToken;
  }
}

function throwIfEnrollment(body: {
  mfaEnrollmentRequired?: boolean;
  enrolToken?: string;
  mfa_enrollment_required?: boolean;
  enrol_token?: string;
}): void {
  const token = body.enrolToken || body.enrol_token;
  if ((body.mfaEnrollmentRequired || body.mfa_enrollment_required) && token) {
    throw new MfaEnrollmentRequiredError(token);
  }
}

export async function login(payload: LoginPayload): Promise<{ user: User; tokens: AuthTokens }> {
  if (shouldUseMocks()) {
    await delay(300);
    return {
      user: mockUserForEmail(payload.email),
      tokens: { access: 'mock-access', refresh: 'mock-refresh' },
    };
  }

  const { data } = await apiClient.post('/auth/login/', payload);
  const body = unwrapData<{
    user: User;
    access: string;
    refresh?: string;
    mfaRequired?: boolean;
    mfaToken?: string;
    mfaEnrollmentRequired?: boolean;
    enrolToken?: string;
  }>(data);
  throwIfEnrollment(body);
  throwIfMfaRequired(body);
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
      kind: 'pending',
      detail: 'Account created. Sign in with your email and password to continue.',
    };
  }

  const { data } = await apiClient.post('/auth/register/', payload);
  const body = unwrapData<{
    access?: string;
    refresh?: string;
    userId?: number;
    companyId?: number;
    detail?: string;
    user?: User;
  }>(data);
  // R-068 / BB-000251: register never establishes a session (no JWT). Same
  // pending shape for new and duplicate emails (non-enumerating).
  return {
    kind: 'pending',
    detail: body.detail || 'If this email can be registered, an account has been prepared.',
  };
}

/** Sign-up step 1: mandatory email verification, ahead of register(). */
export async function requestRegisterOtp(email: string): Promise<{ detail: string; debugCode?: string }> {
  if (shouldUseMocks()) {
    return import.meta.env.DEV
      ? { detail: 'Verification code sent.', debugCode: '123456' }
      : { detail: 'Verification code sent.' };
  }
  const { data } = await apiClient.post('/auth/register/otp/request/', { email });
  const body = unwrapData<{ detail: string; debugCode?: string; debug_code?: string }>(data);
  return {
    detail: body.detail,
    debugCode: body.debugCode ?? body.debug_code,
  };
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
  const body = unwrapData<{
    user?: User;
    access: string;
    refresh?: string;
    mfaRequired?: boolean;
    mfaToken?: string;
    mfaEnrollmentRequired?: boolean;
    enrolToken?: string;
  }>(data);
  throwIfEnrollment(body);
  throwIfMfaRequired(body);
  const tokens = tokensFromBody(body);
  setAccessToken(tokens.access);
  let user = body.user;
  if (!user) {
    user = await fetchCurrentUser();
  }
  return { user, tokens };
}

/** Second step of login: exchange the challenge token + authenticator (or recovery) code for a session. */
export async function verifyMfaLogin(
  mfaToken: string,
  input: { code?: string; recoveryCode?: string },
): Promise<{ user: User; tokens: AuthTokens }> {
  if (shouldUseMocks()) {
    return { user: mockUser, tokens: { access: 'mock-access', refresh: 'mock-refresh' } };
  }
  const { data } = await apiClient.post('/auth/mfa/verify/', {
    mfaToken,
    code: input.code,
    recoveryCode: input.recoveryCode,
  });
  const body = unwrapData<{ user?: User; access: string | null; refresh?: string }>(data);
  const tokens = tokensFromBody(body);
  setAccessToken(tokens.access);
  const user = body.user ?? (await fetchCurrentUser());
  return { user, tokens };
}

export interface MfaStatus {
  enabled: boolean;
  pendingSetup: boolean;
  recoveryCodesRemaining: number;
}

export interface MfaSetup {
  secret: string;
  otpauthUri: string;
  qrPng: string;
}

export async function getMfaStatus(): Promise<MfaStatus> {
  if (shouldUseMocks()) return { enabled: false, pendingSetup: false, recoveryCodesRemaining: 0 };
  const { data } = await apiClient.get('/auth/mfa/status/');
  return unwrapData<MfaStatus>(data);
}

export async function startMfaSetup(enrolToken?: string): Promise<MfaSetup> {
  const { data } = await apiClient.post(
    '/auth/mfa/setup/',
    enrolToken ? { enrol_token: enrolToken } : {},
  );
  return unwrapData<MfaSetup>(data);
}

/** Returns the one-time recovery codes; they are never shown again. */
export async function confirmMfa(code: string, enrolToken?: string): Promise<string[]> {
  const { data } = await apiClient.post('/auth/mfa/confirm/', {
    code,
    ...(enrolToken ? { enrol_token: enrolToken } : {}),
  });
  return unwrapData<{ recoveryCodes: string[] }>(data).recoveryCodes;
}

export async function disableMfa(password: string, factor: { code?: string; recoveryCode?: string }): Promise<void> {
  await apiClient.post('/auth/mfa/disable/', { password, code: factor.code, recoveryCode: factor.recoveryCode });
}

export async function regenerateMfaRecoveryCodes(password: string, code: string): Promise<string[]> {
  const { data } = await apiClient.post('/auth/mfa/recovery-codes/', { password, code });
  return unwrapData<{ recoveryCodes: string[] }>(data).recoveryCodes;
}

export async function fetchCurrentUser(): Promise<User> {
  if (shouldUseMocks()) {
    await delay(100);
    // BB fix (2026-09-13): this used to always return mockUser (OWNER),
    // silently resetting a SALES/ACCT mock session back to OWNER on every
    // app boot/navigation (AuthContext re-fetches "me" so capabilities
    // aren't trusted from storage) — the stored profile keeps `email`
    // specifically so this lookup is possible.
    const stored = getStoredUser();
    return stored ? mockUserForEmail(stored.email) : mockUser;
  }
  const { data } = await apiClient.get('/auth/me/');
  return unwrapData<User>(data);
}

/** M1-009: register this device's push token (native shell only — a no-op result on web). */
export async function registerPushToken(pushToken: string): Promise<void> {
  if (shouldUseMocks() || !pushToken) return;
  await apiClient.patch('/auth/me/', { pushToken });
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

export async function requestPasswordReset(identifier: string): Promise<void> {
  if (shouldUseMocks()) {
    await delay(200);
    return;
  }
  await apiClient.post('/auth/password/reset/', { identifier });
}

export async function confirmPasswordReset(token: string, newPassword: string): Promise<void> {
  if (shouldUseMocks()) {
    await delay(200);
    return;
  }
  await apiClient.post('/auth/password/reset/confirm/', {
    token,
    new_password: newPassword,
  });
}

function delay(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}
