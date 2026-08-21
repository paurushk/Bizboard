import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { CssBaseline, ThemeProvider } from '@mui/material';
import { AuthProvider } from '@/auth/AuthContext';
import { fetchFeatureFlags } from '@/config/featureFlags';
import { shouldUseMocks } from '@/api/client';
import { hasStoredSession } from '@/auth/session';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { theme } from '@/theme';
import { App } from './App';
import { registerPwa } from './pwa';
import './index.css';

if (import.meta.env.PROD && import.meta.env.VITE_USE_MOCKS === 'true') {
  throw new Error('VITE_USE_MOCKS must not be enabled for production builds');
}
if (import.meta.env.PROD && import.meta.env.VITE_PILOT_ADVANCED === 'true') {
  throw new Error('VITE_PILOT_ADVANCED must not be enabled for production builds');
}

// BB-000121 / BB-000165: optional Sentry — no-op when VITE_SENTRY_DSN is unset.
const sentryDsn = import.meta.env.VITE_SENTRY_DSN;
if (typeof sentryDsn === 'string' && sentryDsn.trim()) {
  void import('@sentry/react')
    .then((Sentry) => {
      Sentry.init({
        dsn: sentryDsn.trim(),
        environment: import.meta.env.MODE,
        tracesSampleRate: 0.1,
      });
    })
    .catch(() => {
      // Package missing or init failed — keep app bootable.
    });
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 30_000,
    },
  },
});

// UXW2-006: skip the boot-time fetch on a truly anonymous device — the endpoint
// requires auth, so firing it blind guarantees a 401 on every logged-out load.
// hasStoredSession() is a display-profile heuristic (not a real auth check), so a
// stale/expired session can still 401 here; that's fine, it's the same silent
// graceful-degradation as before. The authenticated case is now covered
// properly by AuthContext's boot effect, which re-fetches flags once /auth/me
// actually resolves instead of racing it.
if (shouldUseMocks() || hasStoredSession()) {
  void fetchFeatureFlags().catch(() => {
    // Stale/expired session — flags stay null until authenticated refresh.
  });
}

registerPwa();

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <ThemeProvider theme={theme}>
          <CssBaseline />
          <BrowserRouter>
            <AuthProvider>
              <App />
            </AuthProvider>
          </BrowserRouter>
        </ThemeProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  </StrictMode>,
);
