import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import * as authApi from '@/api/auth';
import {
  clearSession,
  getAccessToken,
  getStoredUser,
  hasSession,
  setStoredUser,
  setTokens,
} from '@/auth/session';
import type { User } from '@/types/domain';

interface AuthContextValue {
  user: User | null;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  loginWithOtp: (phone: string, code: string) => Promise<void>;
  register: (payload: authApi.RegisterPayload) => Promise<void>;
  logout: () => Promise<void>;
  usingMockSession: boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(() => getStoredUser());
  const [usingMockSession, setUsingMockSession] = useState(false);

  const applySession = useCallback((nextUser: User, tokens: { access: string; refresh: string }) => {
    setTokens(tokens);
    setStoredUser(nextUser);
    setUser(nextUser);
    setUsingMockSession(
      tokens.access.startsWith('mock') || tokens.access.startsWith('dev'),
    );
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const result = await authApi.login({ email, password });
      applySession(result.user, result.tokens);
    },
    [applySession],
  );

  const loginWithOtp = useCallback(
    async (phone: string, code: string) => {
      const result = await authApi.verifyOtp(phone, code);
      applySession(result.user, result.tokens);
    },
    [applySession],
  );

  const register = useCallback(
    async (payload: authApi.RegisterPayload) => {
      const result = await authApi.register(payload);
      applySession(result.user, result.tokens);
    },
    [applySession],
  );

  const logout = useCallback(async () => {
    await authApi.logout();
    clearSession();
    setUser(null);
    setUsingMockSession(false);
  }, []);

  // BUG-407: force the app into a logged-out state as soon as a refresh
  // definitively fails, instead of leaving stale `user` state rendered
  // while every subsequent request silently 401s.
  // ProtectedRoute redirects to /login when user is cleared on session-expired.
  useEffect(() => {
    const onSessionExpired = () => {
      clearSession();
      setUser(null);
      setUsingMockSession(false);
    };
    window.addEventListener('bizboard:session-expired', onSessionExpired);
    return () => window.removeEventListener('bizboard:session-expired', onSessionExpired);
  }, []);

  // BUG-408: logging out in one tab left other open tabs believing they
  // were still authenticated until their next API call happened to 401.
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key !== 'bizboard.access' && e.key !== 'bizboard.user') return;
      if (!getAccessToken() || !getStoredUser()) {
        setUser(null);
        setUsingMockSession(false);
      } else {
        setUser(getStoredUser());
      }
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  const value = useMemo(
    () => ({
      user,
      isAuthenticated: Boolean(user && hasSession()),
      login,
      loginWithOtp,
      register,
      logout,
      usingMockSession,
    }),
    [user, login, loginWithOtp, register, logout, usingMockSession],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
