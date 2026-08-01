import { Component, type ErrorInfo, type ReactNode } from 'react';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';

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
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Unhandled render error', error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <Stack spacing={2} sx={{ p: 4, alignItems: 'flex-start' }}>
          <Typography variant="h5">Something went wrong</Typography>
          <Typography color="text.secondary">
            An unexpected error occurred. Reloading the page usually fixes this.
          </Typography>
          <Button variant="contained" onClick={() => window.location.reload()}>
            Reload
          </Button>
        </Stack>
      );
    }
    return this.props.children;
  }
}
