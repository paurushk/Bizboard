import { useMemo } from 'react';
import Chip from '@mui/material/Chip';
import Link from '@mui/material/Link';
import Paper from '@mui/material/Paper';
import Typography from '@mui/material/Typography';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import { keepPreviousData, useMutation, useQuery } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { exportReport, getSalesRegister, getSalesSummary } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { dateRangeForPreset } from '@/components/HistoryFilterBar';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';
import { formatMoney, toNumber } from '@/utils/money';
import { canExport } from '@/utils/permissions';
import { registerRowPath } from '@/pages/reports/ledgerLinks';
import { showEmpty } from '@/utils/queryState';
import { useReportPeriod } from '@/utils/useReportPeriod';
import { downloadReportUrl, formatColumnHeader, isMoneyColumn } from '@/utils/reportFormat';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { DataTable, PageShell } from '@/pages/phase/phaseShared';

export function SalesReportPage() {
  const { user } = useAuth();
  // RPT-06: opens on this financial year (never "everything") and remembers the last choice.
  const { dateFrom, dateTo, setDateFrom, setDateTo, setRange, invalid } = useReportPeriod('sales', 'currentFY');
  const query = useQuery({
    queryKey: ['sales-register', dateFrom, dateTo],
    queryFn: () => getSalesRegister({ dateFrom: dateFrom || undefined, dateTo: dateTo || undefined }),
    enabled: !invalid,
    placeholderData: keepPreviousData,
  });
  const summary = useQuery({
    queryKey: ['sales-summary', dateFrom, dateTo],
    queryFn: () => getSalesSummary({ date_from: dateFrom || undefined, date_to: dateTo || undefined }),
    enabled: !invalid,
    placeholderData: keepPreviousData,
  });
  // A failed refetch must not keep showing the previous range's figures.
  const sd = summary.isError ? undefined : summary.data;
  const totals = sd?.totals as
    | { revenue?: string; invoiceCount?: number; grossInvoiced?: string; creditNotes?: string; debitNotes?: string; taxable?: string; gstAndOther?: string }
    | undefined;

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
        // RPT-11: the document number opens the document.
        ...(key === 'number'
          ? {
              render: (row: Record<string, unknown>) => {
                const to = registerRowPath('sales', row);
                return to ? <Link component={RouterLink} to={to}>{String(row.number ?? '')}</Link> : String(row.number ?? '—');
              },
            }
          : {}),
      })),
    [query.data],
  );

  const byDateRows = useMemo(() => {
    const raw = ((sd?.byDate ?? sd?.by_date) as Array<Record<string, unknown>> | undefined) ?? [];
    return raw.map((row, i) => ({
      id: String(row.invoiceDate ?? row.invoice_date ?? i),
      invoiceDate: String(row.invoiceDate ?? row.invoice_date ?? ''),
      revenue: row.revenue,
      count: row.count,
    }));
  }, [sd]);

  return (
    <PageShell title={t('nav.salesReports')} actions={
<Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
          {(['currentFY', 'previousFY', 'q1', 'q2', 'q3', 'q4'] as const).map((preset) => (
            <Chip
              key={preset}
              size="small"
              label={t(`history.preset.${preset}`)}
              onClick={() => {
                setRange(dateRangeForPreset(preset));
              }}
            />
          ))}
          <TextField
            type="date"
            size="small"
            label={t('common.dateFrom')}
            InputLabelProps={{ shrink: true }}
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            error={invalid}
          />
          <TextField
            type="date"
            size="small"
            label={t('common.dateTo')}
            InputLabelProps={{ shrink: true }}
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            error={invalid}
            helperText={invalid ? t('salesSummary.rangeBackwards') : undefined}
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
}>
      {exportMutation.isError ? (
        <HelpErrorAlert error={exportMutation.error} />
      ) : null}
      {summary.isError ? (
        <ErrorState message={getErrorMessage(summary.error)} error={summary.error} onRetry={() => void summary.refetch()} />
      ) : null}
      {sd && totals ? (
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
          <Paper sx={{ p: 2, flex: 1 }}>
            <Typography variant="caption" color="text.secondary">{t('salesSummary.revenueTitle')}</Typography>
            <Typography variant="h6">{formatMoney(toNumber(totals.revenue))}</Typography>
            <Chip size="small" sx={{ mt: 1 }} label={t('salesSummary.invoices', { count: totals.invoiceCount ?? 0 })} />
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              {t('salesSummary.grossInvoiced')} {formatMoney(toNumber(totals.grossInvoiced))}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {t('salesSummary.creditNotes')} −{formatMoney(toNumber(totals.creditNotes))}
            </Typography>
            {toNumber(totals.debitNotes) > 0 ? (
              <Typography variant="body2" color="text.secondary">
                {t('salesSummary.debitNotes')} +{formatMoney(toNumber(totals.debitNotes))}
              </Typography>
            ) : null}
            <Typography variant="body2" color="text.secondary">
              {t('salesSummary.beforeGst')} {formatMoney(toNumber(totals.taxable))} · {t('salesSummary.gst')} {formatMoney(toNumber(totals.gstAndOther))}
            </Typography>
            <Link component={RouterLink} to="/reports/gstr1" variant="body2" sx={{ display: 'inline-block', mt: 1 }}>
              {t('salesSummary.compareGstr1')}
            </Link>
          </Paper>
          <Paper sx={{ p: 2, flex: 1 }}>
            <Typography variant="subtitle2">{t('reports.topCustomers')}</Typography>
            {((sd.topCustomers as Array<{ customerName?: string; customer__name?: string; customer?: string; amount?: string }>) ?? []).slice(0, 5).map((row, i) => (
              <Typography key={i} variant="body2">
                {row.customerName ?? row.customer__name ?? row.customer ?? '—'} · {formatMoney(toNumber(row.amount))}
              </Typography>
            ))}
          </Paper>
          <Paper sx={{ p: 2, flex: 1 }}>
            <Typography variant="subtitle2">{t('reports.topProducts')}</Typography>
            {((sd.topProducts as Array<{ productName?: string; product__name?: string; product?: string; amount?: string }>) ?? []).slice(0, 5).map((row, i) => (
              <Typography key={i} variant="body2">
                {row.productName ?? row.product__name ?? row.product ?? '—'} · {formatMoney(toNumber(row.amount))}
              </Typography>
            ))}
          </Paper>
          {sd.paymentBreakdown ? (
            <Paper sx={{ p: 2, flex: 1 }}>
              <Typography variant="subtitle2">{t('billing.paymentMode')}</Typography>
              {(['paid', 'partial', 'unpaid'] as const).map((key) => {
                const row = (sd.paymentBreakdown as Record<string, { count?: number; amount?: string }>)[key];
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
        <Paper tabIndex={0} role="region" aria-label={t('common.scrollableTable')} sx={{ overflow: 'auto' }}>
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
      {showEmpty(query, query.data?.rows?.length ?? -1) ? <EmptyState description={t('empty.reports')} /> : null}
      {!query.isError && query.data && query.data.rows.length > 0 ? (
        <DataTable rows={query.data.rows} columns={columns} empty={t('empty.reports')} virtualized />
      ) : null}
    </PageShell>
  );
}
