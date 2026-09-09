import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import Box from '@mui/material/Box';
import CircularProgress from '@mui/material/CircularProgress';
import { useNavigate } from 'react-router-dom';
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
import { clearPosPendingStorageForUser } from '@/pages/pos/posStatus';
import { deepLinkToPath, isNative, onDeepLink, registerForPushNotifications } from '@/lib/native';
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
  const navigate = useNavigate();
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
      await authApi.register(payload);
      // R-068: never auto-issue a session after register; operator must sign in.
      return 'pending' as const;
    },
    [],
  );

  const logout = useCallback(async () => {
    const companyId = user?.companyId;
    const userId = user?.id;
    // F1-025: drop the session immediately so the shell can't be interacted
    // with mid-logout; the network call + cleanup run after.
    setUser(null);
    setUsingMockSession(false);
    // A shared device's next login is a different user -- let it re-register.
    pushRegisteredRef.current = false;
    try {
      await authApi.logout();
    } catch {
      // already logging out locally — a failed server logout must not block it
    }
    if (companyId && userId) {
      // CR-109: drop mid-settlement cash/UPI cues so the next operator cannot resume them.
      clearPosPendingStorageForUser(companyId, userId);
      try {
        await clearAllDrafts(companyId, userId);
      } catch {
        // best-effort wipe
      }
    }
    // CR-007: Wipe shared counter IndexedDB outbox on explicit logout to prevent cross-tenant draft leaks
    if (typeof indexedDB !== 'undefined' && indexedDB.deleteDatabase) {
      try {
        indexedDB.deleteDatabase('bizboard-invoice-outbox');
      } catch {}
    }
    await clearBizboardPwaCaches();
    clearFeatureFlagsCache();
    clearSession();
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
        clearPosPendingStorageForUser(companyId, userId);
        void clearAllDrafts(companyId, userId).catch(() => {
          // best-effort wipe
        });
      }
      if (typeof indexedDB !== 'undefined' && indexedDB.deleteDatabase) {
        try {
          indexedDB.deleteDatabase('bizboard-invoice-outbox');
        } catch {}
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

  // M1-009: register this device's push token once per login, native shells
  // only. No-ops instantly on web (isNative() false) or if the plugin isn't
  // wired (no google-services.json bundled) — see lib/native.ts.
  const pushRegisteredRef = useRef(false);
  useEffect(() => {
    if (!user || !isNative() || pushRegisteredRef.current) return;
    pushRegisteredRef.current = true;
    void (async () => {
      const token = await registerForPushNotifications();
      if (token) {
        try {
          await authApi.registerPushToken(token);
        } catch {
          /* best-effort — a failed PATCH just means no push this session */
        }
      }
    })();
  }, [user]);

  // M1-008: a custom-scheme deep link opened while the app is already running
  // (in.bizboard.app://...) — strip the scheme/host and route to the path
  // within the existing app shell. Native shells only; no-ops on web.
  useEffect(() => {
    return onDeepLink((url) => {
      const path = deepLinkToPath(url);
      if (path) navigate(path);
      // malformed deep link -> null -> ignore rather than crash the shell
    });
  }, [navigate]);

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

        // GAP-008: On unauthenticated public routes with no prior session in storage,
        // do not fire silentRefreshAccessToken to eliminate benign 401 console noise.
        const isPublicPath =
          window.location.pathname.startsWith('/login') ||
          window.location.pathname.startsWith('/register') ||
          window.location.pathname.startsWith('/forgot-password') ||
          window.location.pathname.startsWith('/reset-password') ||
          window.location.pathname.startsWith('/pay/');
        if (!getStoredUser() && isPublicPath) {
          clearSession();
          setUser(null);
          setUsingMockSession(false);
          return;
        }

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
