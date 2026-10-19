import { useMemo } from 'react';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Stack from '@mui/material/Stack';
import { Link as RouterLink } from 'react-router-dom';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { getInvoiceProfitReport } from '@/api/resources';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';
import { formatColumnHeader, isMoneyColumn } from '@/utils/reportFormat';
import { DataTable, DateRangeFields, PageShell } from '@/pages/phase/phaseShared';
import { showEmpty } from '@/utils/queryState';
import { useReportPeriod } from '@/utils/useReportPeriod';

const COST_BASIS_COLOR: Record<string, 'success' | 'warning' | 'error' | 'default'> = {
  FIFO: 'success',
  VALUATION_FALLBACK: 'warning',
  PURCHASE_PRICE_FALLBACK: 'warning',
  ZERO_COST: 'error',
  NO_COGS: 'default',
};

const HIDDEN_COLUMNS = new Set(['id', 'invoice_id', 'is_backfilled']);

export function InvoiceProfitReportPage() {
  const { dateFrom, dateTo, setDateFrom, setDateTo, invalid } = useReportPeriod('invoice-profit', 'currentFY');

  const query = useQuery({
    queryKey: ['invoice-profit-report', dateFrom, dateTo],
    queryFn: () =>
      getInvoiceProfitReport({
        ...(dateFrom ? { date_from: dateFrom } : {}),
        ...(dateTo ? { date_to: dateTo } : {}),
      }),
    enabled: !invalid,
    placeholderData: keepPreviousData,
  });

  const columns = useMemo(() => {
    const first = query.data?.rows?.[0];
    if (!first) return [];
    return Object.keys(first)
      .filter((key) => !HIDDEN_COLUMNS.has(key))
      .map((key) => {
        if (key === 'cost_basis') {
          return {
            key,
            label: t('reports.costBasis'),
            render: (row: Record<string, unknown>) => {
              const value = String(row.cost_basis ?? '');
              return (
                <Chip
                  size="small"
                  label={value.replace(/_/g, ' ')}
                  color={COST_BASIS_COLOR[value] ?? 'default'}
                  variant={row.is_backfilled ? 'outlined' : 'filled'}
                />
              );
            },
          };
        }
        return { key, label: formatColumnHeader(key), money: isMoneyColumn(key) };
      });
  }, [query.data?.rows]);

  return (
    <PageShell title={t('reports.invoiceProfit')} actions={
<Stack direction="row" spacing={1} alignItems="center">
          <Button component={RouterLink} to="/reports/invoice-profit/rollup" size="small" variant="outlined">
            {t('reports.invoiceProfitRollup')}
          </Button>
          <DateRangeFields from={dateFrom} to={dateTo} onFromChange={setDateFrom} onToChange={setDateTo} />
        </Stack>
}>
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
