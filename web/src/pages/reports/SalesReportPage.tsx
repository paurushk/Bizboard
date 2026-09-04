import { useMemo, useState } from 'react';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { exportReport, getSalesRegister } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';
import { canExport } from '@/utils/permissions';
import { downloadReportUrl, formatColumnHeader, isMoneyColumn } from '@/utils/reportFormat';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { DataTable } from '@/pages/phase/phaseShared';

export function SalesReportPage() {
  const { user } = useAuth();
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const query = useQuery({
    queryKey: ['sales-register', dateFrom, dateTo],
    queryFn: () => getSalesRegister({ dateFrom: dateFrom || undefined, dateTo: dateTo || undefined }),
  });

  const exportMutation = useMutation({
    // BUG-616: forward the same date filter the on-screen table is using —
    // previously export ignored it and always exported the full register.
    mutationFn: () => exportReport('sales', { dateFrom: dateFrom || undefined, dateTo: dateTo || undefined }),
    onSuccess: (r) => downloadReportUrl(r.url, 'sales-register.csv'),
  });

  // F3-017: an unbounded date range can return the entire register —
  // window the DOM rows via phaseShared.DataTable's virtualized mode.
  const columns = useMemo(
    () =>
      (query.data?.rows?.[0] ? Object.keys(query.data.rows[0]) : []).map((key) => ({
        key,
        label: formatColumnHeader(key),
        money: isMoneyColumn(key),
      })),
    [query.data?.rows],
  );

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1}>
        <Typography variant="h4">{t('nav.salesReports')}</Typography>
        <Stack direction="row" spacing={1} alignItems="center">
          <TextField
            type="date"
            size="small"
            label={t('common.dateFrom')}
            InputLabelProps={{ shrink: true }}
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
          />
          <TextField
            type="date"
            size="small"
            label={t('common.dateTo')}
            InputLabelProps={{ shrink: true }}
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
          />
          {canExport(user) ? (
            <Button
              variant="outlined"
              disabled={exportMutation.isPending}
              onClick={() => exportMutation.mutate()}
            >
              {t('common.export')}
            </Button>
          ) : null}
        </Stack>
      </Stack>
      {exportMutation.isError ? (
        <HelpErrorAlert error={exportMutation.error} />
      ) : null}
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {query.data?.rows?.length === 0 ? <EmptyState description={t('empty.reports')} /> : null}
      {query.data && query.data.rows.length > 0 ? (
        <DataTable rows={query.data.rows} columns={columns} empty={t('empty.reports')} virtualized />
      ) : null}
    </Stack>
  );
}
