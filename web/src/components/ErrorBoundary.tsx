import { Component, type ErrorInfo, type ReactNode } from 'react';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { t } from '@/i18n';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

// BUG-409: no top-level error boundary existed anywhere in the render tree
// — any uncaught render-time exception (a malformed API payload hitting an
// unguarded property access, a null dereference in a billing page, etc.)
// blanked the entire screen with no recovery UI for any user role.
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    // F3-044: getDerivedStateFromError must be pure per React's own docs —
    // the chunk-reload side effect previously lived here; it's now in
    // componentDidCatch below, which is where side effects belong.
    return { hasError: true };
  }

  componentDidMount() {
    // F3-044 companion: a `bizboard:chunk-reload` guard left over from a
    // prior auto-recovery (see componentDidCatch) should not block
    // recovering from a *different* chunk error later in the same session —
    // clear it once we know the app mounted successfully, which is also
    // true right after that reload navigation completes.
    if (typeof sessionStorage !== 'undefined') {
      try {
        sessionStorage.removeItem('bizboard:chunk-reload');
      } catch {
        /* sessionStorage unavailable */
      }
    }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Unhandled render error', error, info.componentStack);
    // BB-000752: report to Sentry when available (dynamic import keeps bundle optional).
    void import('@sentry/react')
      .then((Sentry) => {
        Sentry.captureException(error, {
          extra: { componentStack: info.componentStack },
        });
      })
      .catch(() => {
        /* Sentry not installed / not configured */
      });

    // FE-11: after a deploy, a client still holding the old index.html requests
    // hashed chunk filenames that no longer exist — `lazy()` rejects with a
    // ChunkLoadError / "Failed to fetch dynamically imported module". A hard
    // reload fetches the new index.html and fixes it; do that once
    // automatically instead of stranding the user on the error screen.
    const msg = error instanceof Error ? `${error.name}: ${error.message}` : String(error);
    const isChunkError =
      /ChunkLoadError|Loading chunk [\d]+ failed|Failed to fetch dynamically imported module|error loading dynamically imported module/i.test(
        msg,
      );
    if (isChunkError && typeof sessionStorage !== 'undefined') {
      try {
        if (!sessionStorage.getItem('bizboard:chunk-reload')) {
          sessionStorage.setItem('bizboard:chunk-reload', String(Date.now()));
          window.location.reload();
        }
      } catch {
        /* sessionStorage unavailable — fall through to the error screen */
      }
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <Stack spacing={2} sx={{ p: 4, alignItems: 'flex-start' }}>
          <Typography variant="h5">{t('errorBoundary.title')}</Typography>
          <Typography color="text.secondary">{t('errorBoundary.body')}</Typography>
          <Button variant="contained" onClick={() => window.location.reload()}>
            {t('errorBoundary.reload')}
          </Button>
        </Stack>
      );
    }
    return this.props.children;
  }
}
