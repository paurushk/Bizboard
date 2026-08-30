import type { AuthTokens, User } from '@/types/domain';

const ACCESS_KEY = 'bizboard.access';
const REFRESH_KEY = 'bizboard.refresh';
const USER_KEY = 'bizboard.user';

/**
 * BB-000375: access JWT is httpOnly cookie (bb_access), not readable by XSS.
 * Memory/localStorage no longer hold access tokens.
 */
let sessionEstablished = false;

/**
 * BB-000030: persisted profile is display-only — never role/capabilities.
 * AuthContext always overwrites live user state from `/auth/me`.
 */
export type StoredUserProfile = {
  id: number;
  email: string;
  fullName: string;
  companyName?: string;
  companyId?: number;
};

export function getAccessToken(): string | null {
  // Cookie auth — Authorization header not required when withCredentials=true.
  return sessionEstablished ? 'cookie' : null;
}

/** Refresh JWT is httpOnly cookie-only; never read from localStorage. */
export function getRefreshToken(): string | null {
  return null;
}

export function setAccessToken(_access: string): void {
  sessionEstablished = true;
  try {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  } catch {
    // ignore
  }
}

export function clearTokens(): void {
  sessionEstablished = false;
  try {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  } catch {
    // ignore
  }
}

export function setTokens(tokens: AuthTokens): void {
  setAccessToken(tokens.access);
}

export function getStoredUser(): StoredUserProfile | null {
  try {
    const raw = localStorage.getItem(USER_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as StoredUserProfile;
  } catch {
    return null;
  }
}

export function setStoredUser(user: User | StoredUserProfile | null): void {
  try {
    if (!user) {
      localStorage.removeItem(USER_KEY);
      return;
    }
    const profile: StoredUserProfile = {
      id: user.id,
      email: user.email,
      fullName: 'fullName' in user ? user.fullName : (user as User).fullName,
      companyName:
        'companyName' in user
          ? (user as StoredUserProfile).companyName
          : (user as User).company?.name,
      companyId:
        'companyId' in user
          ? user.companyId
          : (user as User).companyId ?? (user as User).company?.id,
    };
    localStorage.setItem(USER_KEY, JSON.stringify(profile));
  } catch {
    // ignore
  }
}

export function clearSession(): void {
  clearTokens();
  setStoredUser(null);
}

export function hasStoredSession(): boolean {
  return Boolean(getStoredUser());
}
