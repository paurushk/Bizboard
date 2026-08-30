import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import Box from '@mui/material/Box';
import CircularProgress from '@mui/material/CircularProgress';
import * as authApi from '@/api/auth';
import { ACTIVE_COMPANY_STORAGE_KEY, shouldUseMocks, silentRefreshAccessToken } from '@/api/client';
import { clearFeatureFlagsCache, fetchFeatureFlags } from '@/config/featureFlags';
import {
  clearSession,
  getAccessToken,
  getStoredUser,
  setAccessToken,
  setStoredUser,
} from '@/auth/session';
import { clearAllDrafts } from '@/offline/invoiceDraftCache';
import { clearBizboardPwaCaches } from '@/pwaCaches';
import type { User } from '@/types/domain';

interface AuthContextValue {
  user: User | null;
  isAuthenticated: boolean;
  /** False until boot /auth/me settles (or no session to restore). */
  authReady: boolean;
  login: (email: string, password: string) => Promise<void>;
  loginWithOtp: (phone: string, code: string) => Promise<void>;
  register: (payload: authApi.RegisterPayload) => Promise<'session' | 'pending'>;
  setSession: (nextUser: User, access: string) => Promise<void>;
  logout: () => Promise<void>;
  usingMockSession: boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  // BB-000228 / BB-000266: access is memory-only — always boot via cookie refresh.
  const [user, setUser] = useState<User | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [usingMockSession, setUsingMockSession] = useState(false);

  const applySession = useCallback((nextUser: User, access: string) => {
    setAccessToken(access);
    // BB-000030: localStorage keeps display fields only; live ACL from this User.
    setStoredUser(nextUser);
    setUser(nextUser);
    setUsingMockSession(
      shouldUseMocks() || access.startsWith('mock') || access.startsWith('dev'),
    );
    setAuthReady(true);
  }, []);

  const setSession = useCallback(
    async (nextUser: User, access: string) => {
      applySession(nextUser, access);
      await fetchFeatureFlags(true);
    },
    [applySession],
  );

  const login = useCallback(
    async (email: string, password: string) => {
      const result = await authApi.login({ email, password });
      applySession(result.user, result.tokens.access);
      await fetchFeatureFlags(true);
    },
    [applySession],
  );

  const loginWithOtp = useCallback(
    async (phone: string, code: string) => {
      const result = await authApi.verifyOtp(phone, code);
      applySession(result.user, result.tokens.access);
      await fetchFeatureFlags(true);
    },
    [applySession],
  );

  const register = useCallback(
    async (payload: authApi.RegisterPayload) => {
      const result = await authApi.register(payload);
      if (result.kind === 'pending') {
        return 'pending';
      }
      applySession(result.user, result.tokens.access);
      await fetchFeatureFlags(true);
      return 'session';
    },
    [applySession],
  );

  const logout = useCallback(async () => {
    const companyId = user?.companyId;
    const userId = user?.id;
    await authApi.logout();
    if (companyId && userId) {
      try {
        await clearAllDrafts(companyId, userId);
      } catch {
        // best-effort wipe
      }
    }
    await clearBizboardPwaCaches();
    clearFeatureFlagsCache();
    clearSession();
    setUser(null);
    setUsingMockSession(false);
    setAuthReady(true);
  }, [user]);

  // BUG-407: force logged-out state when refresh fails.
  useEffect(() => {
    const onSessionExpired = () => {
      const stored = getStoredUser();
      const companyId = stored?.companyId;
      const userId = stored?.id;
      clearFeatureFlagsCache();
      if (companyId && userId) {
        void clearAllDrafts(companyId, userId).catch(() => {
          // best-effort wipe
        });
      }
      void clearBizboardPwaCaches();
      clearSession();
      setUser(null);
      setUsingMockSession(false);
      setAuthReady(true);
    };
    window.addEventListener('bizboard:session-expired', onSessionExpired);

    // R5-004: the stored active-company id no longer matches the server's
    // active company (usually a company switch in another tab). Drop the stale
    // header value and reload so the app re-resolves the company from /auth/me
    // instead of every request 409-ing.
    const onCompanyConflict = () => {
      try {
        localStorage.removeItem(ACTIVE_COMPANY_STORAGE_KEY);
      } catch {
        // ignore storage errors
      }
      window.location.reload();
    };
    window.addEventListener('bizboard:company-context-conflict', onCompanyConflict);

    return () => {
      window.removeEventListener('bizboard:session-expired', onSessionExpired);
      window.removeEventListener('bizboard:company-context-conflict', onCompanyConflict);
    };
  }, []);

  // UXW2-002: proactive sliding refresh so long invoice forms do not dump to /login
  // on the first Save after access JWT expiry. Also refresh on tab focus.
  useEffect(() => {
    if (!user || shouldUseMocks()) return;
    const refreshQuietly = () => {
      void silentRefreshAccessToken({ force: true, notifyOnFailure: false });
    };
    const intervalId = window.setInterval(refreshQuietly, 10 * 60 * 1000);
    const onVisibility = () => {
      if (document.visibilityState === 'visible') refreshQuietly();
    };
    window.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('focus', refreshQuietly);
    return () => {
      window.clearInterval(intervalId);
      window.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener('focus', refreshQuietly);
    };
  }, [user]);

  // BB-000266 / BB-000030: memory empty on load — silent-refresh, then /auth/me.
  // Never hydrate role/capabilities from localStorage (display profile only).
  useEffect(() => {
    let cancelled = false;
    setAuthReady(false);
    (async () => {
      try {
        if (shouldUseMocks()) {
          const stored = getStoredUser();
          if (stored) {
            setAccessToken('mock-access');
            // Mocks: re-fetch mock me so capabilities are not taken from storage.
            const me = await authApi.fetchCurrentUser();
            if (cancelled) return;
            setStoredUser(me);
            setUser(me);
            setUsingMockSession(true);
          }
          return;
        }
        // Drop any legacy full-user blob before me settles (no capability flash).
        setStoredUser(getStoredUser());
        // Do not notify on boot failure — anonymous visitors have no cookie.
        const access = await silentRefreshAccessToken({ notifyOnFailure: false });
        if (cancelled) return;
        if (!access) {
          clearSession();
          setUser(null);
          setUsingMockSession(false);
          return;
        }
        const me = await authApi.fetchCurrentUser();
        if (cancelled) return;
        setStoredUser(me);
        setUser(me);
        setUsingMockSession(shouldUseMocks());
        // UXW2-006: main.tsx's boot-time fetch races this silent refresh and can
        // land before the access token is set, silently leaving flags null for an
        // otherwise-authenticated session. Re-fetch now that auth is confirmed.
        void fetchFeatureFlags(true).catch(() => {
          // best-effort — a route that needs a flag will just see it as off
        });
      } catch {
        if (cancelled) return;
        clearSession();
        setUser(null);
        setUsingMockSession(false);
      } finally {
        if (!cancelled) setAuthReady(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // BUG-408 / BB-000299: sync across tabs via stored user; re-fetch /auth/me.
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key !== 'bizboard.user') return;
      void (async () => {
        if (!getStoredUser()) {
          clearSession();
          setUser(null);
          setUsingMockSession(false);
          return;
        }
        try {
          if (!getAccessToken()) {
            const access = await silentRefreshAccessToken();
            if (!access) {
              clearSession();
              setUser(null);
              setUsingMockSession(false);
              return;
            }
          }
          const me = await authApi.fetchCurrentUser();
          setStoredUser(me);
          setUser(me);
          setUsingMockSession(shouldUseMocks());
        } catch {
          clearSession();
          setUser(null);
          setUsingMockSession(false);
        }
      })();
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  const value = useMemo(
    () => ({
      user,
      isAuthenticated: Boolean(user),
      authReady,
      login,
      loginWithOtp,
      register,
      setSession,
      logout,
      usingMockSession,
    }),
    [user, authReady, login, loginWithOtp, register, setSession, logout, usingMockSession],
  );

  if (!authReady) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="100vh">
        <CircularProgress />
      </Box>
    );
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
