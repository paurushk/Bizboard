import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { listSharedTickets } from '@/api/roadmap';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { isSupportTicketsEnabled } from '@/config/features';
import { PageTitle } from '@/contextHelp';
import { t, useLocale } from '@/i18n';
import { enumLabel } from '@/utils/enumLabels';
import { PageShell } from '@/pages/phase/phaseShared';

function rowsOf(data: unknown): Record<string, unknown>[] {
  if (Array.isArray(data)) return data as Record<string, unknown>[];
  const results = (data as { results?: Record<string, unknown>[] } | null)?.results;
  return results ?? [];
}

export function SharedTicketsPage() {
  if (!isSupportTicketsEnabled()) {
    return <PageShell title={t('nav.sharedTickets')}><Typography>{t('erp.moduleDisabled')}</Typography></PageShell>;
  }
  return <SharedInner />;
}

function SharedInner() {
  useLocale();
  const list = useQuery({ queryKey: ['shared-tickets'], queryFn: listSharedTickets });
  const rows = rowsOf(list.data);
  return (
    <Stack spacing={1}>
      <PageTitle>{t('nav.sharedTickets')}</PageTitle>
      {list.isLoading ? <LoadingState /> : null}
      {list.isError ? (
        <ErrorState message={getErrorMessage(list.error)} error={list.error} onRetry={() => void list.refetch()} />
      ) : null}
      {!list.isLoading && !list.isError && rows.length === 0 ? (
        <EmptyState description={t('osPlan.noSharedTickets')} />
      ) : null}
      {rows.map((row) => (
        <Stack key={String(row.id)} direction="row" spacing={1} alignItems="center">
          <Typography>
            {String(row.sourceNumber)} · {String(row.sourceCompanyName)} · {String(row.subject)} · {enumLabel('ticketStatus', String(row.status ?? ''))}
          </Typography>
          <Button size="small" component={RouterLink} to="/support/tickets">{t('common.open')}</Button>
        </Stack>
      ))}
      <Button component={RouterLink} to="/support/tickets" variant="outlined">{t('common.next')}</Button>
    </Stack>
  );
}
