import { useMemo, useState } from 'react';
import Chip from '@mui/material/Chip';
import Paper from '@mui/material/Paper';
import Typography from '@mui/material/Typography';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import { useMutation, useQuery } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { exportReport, getSalesRegister, getSalesSummary } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { PageTitle } from '@/contextHelp';
import { t } from '@/i18n';
import { formatMoney, toNumber } from '@/utils/money';
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
  const summary = useQuery({
    queryKey: ['sales-summary', dateFrom, dateTo],
    queryFn: () => getSalesSummary({ date_from: dateFrom || undefined, date_to: dateTo || undefined }),
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

  const byDateRows = useMemo(() => {
    const raw = ((summary.data?.byDate ?? summary.data?.by_date) as Array<Record<string, unknown>> | undefined) ?? [];
    return raw.map((row, i) => ({
      id: String(row.invoiceDate ?? row.invoice_date ?? i),
      invoiceDate: String(row.invoiceDate ?? row.invoice_date ?? ''),
      revenue: row.revenue,
      count: row.count,
    }));
  }, [summary.data]);

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1}>
        <PageTitle>{t('nav.salesReports')}</PageTitle>
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
      {summary.data ? (
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
          <Paper sx={{ p: 2, flex: 1 }}>
            <Typography variant="caption" color="text.secondary">{t('reports.revenue')}</Typography>
            <Typography variant="h6">{formatMoney(toNumber((summary.data.totals as { revenue?: string })?.revenue))}</Typography>
            <Chip size="small" sx={{ mt: 1 }} label={(summary.data.totals as { invoiceCount?: number })?.invoiceCount ?? 0} />
          </Paper>
          <Paper sx={{ p: 2, flex: 1 }}>
            <Typography variant="subtitle2">{t('reports.topCustomers')}</Typography>
            {((summary.data.topCustomers as Array<{ customerName?: string; customer__name?: string; customer?: string; amount?: string }>) ?? []).slice(0, 5).map((row, i) => (
              <Typography key={i} variant="body2">
                {row.customerName ?? row.customer__name ?? row.customer ?? '—'} · {formatMoney(toNumber(row.amount))}
              </Typography>
            ))}
          </Paper>
          <Paper sx={{ p: 2, flex: 1 }}>
            <Typography variant="subtitle2">{t('reports.topProducts')}</Typography>
            {((summary.data.topProducts as Array<{ productName?: string; product__name?: string; product?: string; amount?: string }>) ?? []).slice(0, 5).map((row, i) => (
              <Typography key={i} variant="body2">
                {row.productName ?? row.product__name ?? row.product ?? '—'} · {formatMoney(toNumber(row.amount))}
              </Typography>
            ))}
          </Paper>
          {summary.data.paymentBreakdown ? (
            <Paper sx={{ p: 2, flex: 1 }}>
              <Typography variant="subtitle2">{t('billing.paymentMode')}</Typography>
              {(['paid', 'partial', 'unpaid'] as const).map((key) => {
                const row = (summary.data.paymentBreakdown as Record<string, { count?: number; amount?: string }>)[key];
                return (
                  <Typography key={key} variant="body2">
                    {t(`status.${key.toUpperCase()}`)} · {row?.count ?? 0} · {formatMoney(toNumber(row?.amount))}
                  </Typography>
                );
              })}
            </Paper>
          ) : null}
        </Stack>
      ) : null}
      {byDateRows.length > 0 ? (
        <Paper sx={{ overflow: 'auto' }}>
          <Typography variant="subtitle2" sx={{ p: 2, pb: 1 }}>{t('reports.revenueByDate')}</Typography>
          <DataTable
            rows={byDateRows}
            columns={[
              { key: 'invoiceDate', label: t('common.date') },
              { key: 'revenue', label: t('reports.revenue'), money: true },
              { key: 'count', label: t('reports.invoiceCount') },
            ]}
            empty={t('empty.reports')}
          />
        </Paper>
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
