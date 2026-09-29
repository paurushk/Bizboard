import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { listSharedTickets } from '@/api/roadmap';
import { isSupportTicketsEnabled } from '@/config/features';
import { PageTitle } from '@/contextHelp';
import { t } from '@/i18n';
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
  const list = useQuery({ queryKey: ['shared-tickets'], queryFn: listSharedTickets });
  return (
    <Stack spacing={1}>
      <PageTitle>{t('nav.sharedTickets')}</PageTitle>
      {rowsOf(list.data).map((row) => (
        <Typography key={String(row.id)}>
          {String(row.sourceNumber)} · {String(row.sourceCompanyName)} · {String(row.subject)} · {String(row.status)}
        </Typography>
      ))}
      {rowsOf(list.data).length === 0 ? <Typography>No shared tickets.</Typography> : null}
    </Stack>
  );
}
