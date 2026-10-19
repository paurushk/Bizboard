import type { ReactNode } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';
import { settingsErrorText } from '@/utils/settingsErrors';

type QueryLike<T> = {
  data: T | undefined;
  isLoading: boolean;
  isError: boolean;
  error: unknown;
  refetch: () => unknown;
};

/**
 * SET-13: one way to show a settings section that depends on a fetch. A failed load is an error
 * with Retry — never a blank form or placeholder values that could be saved back. If a refresh
 * fails while data is already on screen, the data stays and a warning explains it may be stale.
 */
export function AsyncSection<T>({
  query,
  isEmpty,
  empty,
  children,
}: {
  query: QueryLike<T>;
  isEmpty?: (data: T) => boolean;
  empty?: { title?: string; description?: string; action?: ReactNode };
  children: (data: T) => ReactNode;
}) {
  if (query.isLoading) return <LoadingState />;
  if (query.data === undefined) {
    if (query.isError) {
      return (
        <ErrorState message={settingsErrorText(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      );
    }
    return <LoadingState />;
  }
  if (isEmpty?.(query.data)) {
    return <EmptyState title={empty?.title} description={empty?.description} action={empty?.action} />;
  }
  return (
    <>
      {query.isError ? (
        <Alert
          severity="warning"
          action={
            <Button color="inherit" size="small" onClick={() => void query.refetch()}>
              {t('settingsShell.retry')}
            </Button>
          }
          sx={{ mb: 2 }}
        >
          {t('settingsShell.staleData')}
        </Alert>
      ) : null}
      {children(query.data)}
    </>
  );
}
