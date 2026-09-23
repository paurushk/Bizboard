import { useMemo, useState } from 'react';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { getDayBook } from '@/api/resources';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { PageTitle } from '@/contextHelp';
import { t } from '@/i18n';
import { asRows, DataTable } from '@/pages/phase/phaseShared';
import { formatMoney, toNumber } from '@/utils/money';
import { todayIso } from '@/components/billing';

export function DayBookPage() {
  const [onDate, setOnDate] = useState(todayIso());
  const query = useQuery({
    queryKey: ['day-book', onDate],
    queryFn: () => getDayBook({ date: onDate }),
  });
  const rows = useMemo(() => (query.data?.rows as Record<string, unknown>[]) ?? [], [query.data]);

  if (query.isLoading) return <LoadingState />;
  if (query.isError) {
    return (
      <ErrorState
        message={getErrorMessage(query.error)}
        error={query.error}
        onRetry={() => void query.refetch()}
      />
    );
  }

  return (
    <Stack spacing={2}>
      <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ sm: 'center' }} spacing={1}>
        <PageTitle>{t('nav.dayBook')}</PageTitle>
        <TextField
          type="date"
          size="small"
          label={t('common.date')}
          InputLabelProps={{ shrink: true }}
          value={onDate}
          onChange={(e) => setOnDate(e.target.value)}
        />
      </Stack>
      <Typography variant="body2" color="text.secondary">
        {String(query.data?.disclaimer ?? t('reports.dayBookDisclaimer'))}
      </Typography>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
        {[
          [t('reports.inflow'), query.data?.inflow],
          [t('reports.outflow'), query.data?.outflow],
          [t('reports.net'), query.data?.net],
        ].map(([label, val]) => (
          <Paper key={String(label)} variant="outlined" sx={{ p: 2, flex: 1 }}>
            <Typography variant="caption" color="text.secondary">
              {String(label)}
            </Typography>
            <Typography variant="h6">{formatMoney(toNumber(val as string | number))}</Typography>
          </Paper>
        ))}
      </Stack>
      {rows.length === 0 ? <EmptyState description={t('reports.dayBookEmpty')} /> : null}
      {rows.length > 0 ? (
        <DataTable
          rows={asRows(rows)}
          empty={t('reports.dayBookEmpty')}
          columns={[
            { key: 'date', label: t('common.date') },
            { key: 'txnType', label: t('common.type') },
            { key: 'number', label: t('common.number') },
            { key: 'party', label: t('billing.customer') },
            { key: 'amount', label: t('common.total'), render: (row) => formatMoney(toNumber(row.amount as string | number)) },
            { key: 'status', label: t('common.status') },
          ]}
          actions={(row) =>
            row.sourcePath ? (
              <Typography component={RouterLink} to={String(row.sourcePath)} variant="body2" sx={{ color: 'primary.main' }}>
                {t('common.open')}
              </Typography>
            ) : null
          }
        />
      ) : null}
    </Stack>
  );
}
