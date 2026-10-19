import { useState } from 'react';
import Stack from '@mui/material/Stack';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { getInvoiceProfitRollup } from '@/api/resources';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';
import { DataTable, DateRangeFields, PageShell } from '@/pages/phase/phaseShared';
import { showEmpty } from '@/utils/queryState';
import { useReportPeriod } from '@/utils/useReportPeriod';

type GroupBy = 'customer' | 'product' | 'period' | 'cost_center';

const GROUP_BY_LABEL: Record<GroupBy, string> = {
  customer: 'common.customer',
  product: 'common.product',
  period: 'common.period',
  cost_center: 'reports.costCenter',
};

/** Built per render so the labels follow a language switch (a module-level t() is read once at import). */
function columnsFor(group: GroupBy): Array<{ key: string; label: string; money?: boolean }> {
  const money = [
    { key: 'revenue', label: t('common.revenue'), money: true },
    { key: 'cogs', label: t('reports.cogs'), money: true },
    { key: 'margin', label: t('reports.grossMargin'), money: true },
  ];
  const invoices = { key: 'invoices', label: t('common.invoices') };
  if (group === 'customer') return [{ key: 'name', label: t('common.customer') }, invoices, ...money];
  if (group === 'product') return [{ key: 'name', label: t('common.product') }, ...money];
  if (group === 'period') return [{ key: 'period', label: t('common.period') }, invoices, ...money];
  return [{ key: 'name', label: t('reports.costCenter') }, invoices, ...money];
}

export function InvoiceProfitRollupPage() {
  const [groupBy, setGroupBy] = useState<GroupBy>('customer');
  const { dateFrom, dateTo, setDateFrom, setDateTo, invalid } = useReportPeriod('invoice-profit-rollup', 'currentFY');

  const query = useQuery({
    queryKey: ['invoice-profit-rollup', groupBy, dateFrom, dateTo],
    queryFn: () =>
      getInvoiceProfitRollup(groupBy, {
        ...(dateFrom ? { date_from: dateFrom } : {}),
        ...(dateTo ? { date_to: dateTo } : {}),
      }),
    enabled: !invalid,
    placeholderData: keepPreviousData,
  });

  const columns = columnsFor(groupBy);

  return (
    <PageShell title={t('reports.invoiceProfitRollup')} actions={
<Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
          <ToggleButtonGroup
            value={groupBy}
            exclusive
            size="small"
            onChange={(_, value: GroupBy | null) => value && setGroupBy(value)}
          >
            {(Object.keys(GROUP_BY_LABEL) as GroupBy[]).map((key) => (
              <ToggleButton key={key} value={key}>
                {t(GROUP_BY_LABEL[key])}
              </ToggleButton>
            ))}
          </ToggleButtonGroup>
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
