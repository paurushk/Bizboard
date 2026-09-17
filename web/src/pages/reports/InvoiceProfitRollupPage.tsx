import { useMemo, useState } from 'react';
import Stack from '@mui/material/Stack';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import { useQuery } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { getInvoiceProfitRollup } from '@/api/resources';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { PageTitle } from '@/contextHelp';
import { t } from '@/i18n';
import { DataTable, DateRangeFields } from '@/pages/phase/phaseShared';

type GroupBy = 'customer' | 'product' | 'period' | 'cost_center';

const GROUP_BY_LABEL: Record<GroupBy, string> = {
  customer: 'common.customer',
  product: 'common.product',
  period: 'common.period',
  cost_center: 'reports.costCenter',
};

const COLUMNS_BY_GROUP: Record<GroupBy, Array<{ key: string; label: string; money?: boolean }>> = {
  customer: [
    { key: 'name', label: t('common.customer') },
    { key: 'invoices', label: t('common.invoices') },
    { key: 'revenue', label: t('common.revenue'), money: true },
    { key: 'cogs', label: t('reports.cogs'), money: true },
    { key: 'margin', label: t('reports.grossMargin'), money: true },
  ],
  product: [
    { key: 'name', label: t('common.product') },
    { key: 'revenue', label: t('common.revenue'), money: true },
    { key: 'cogs', label: t('reports.cogs'), money: true },
    { key: 'margin', label: t('reports.grossMargin'), money: true },
  ],
  period: [
    { key: 'period', label: t('common.period') },
    { key: 'invoices', label: t('common.invoices') },
    { key: 'revenue', label: t('common.revenue'), money: true },
    { key: 'cogs', label: t('reports.cogs'), money: true },
    { key: 'margin', label: t('reports.grossMargin'), money: true },
  ],
  cost_center: [
    { key: 'name', label: t('reports.costCenter') },
    { key: 'invoices', label: t('common.invoices') },
    { key: 'revenue', label: t('common.revenue'), money: true },
    { key: 'cogs', label: t('reports.cogs'), money: true },
    { key: 'margin', label: t('reports.grossMargin'), money: true },
  ],
};

export function InvoiceProfitRollupPage() {
  const [groupBy, setGroupBy] = useState<GroupBy>('customer');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  const query = useQuery({
    queryKey: ['invoice-profit-rollup', groupBy, dateFrom, dateTo],
    queryFn: () =>
      getInvoiceProfitRollup(groupBy, {
        ...(dateFrom ? { date_from: dateFrom } : {}),
        ...(dateTo ? { date_to: dateTo } : {}),
      }),
  });

  const columns = useMemo(() => COLUMNS_BY_GROUP[groupBy], [groupBy]);

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1}>
        <PageTitle>{t('reports.invoiceProfitRollup')}</PageTitle>
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
      </Stack>
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
