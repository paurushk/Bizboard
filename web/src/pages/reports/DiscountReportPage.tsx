import { useMemo, useState } from 'react';
import Card from '@mui/material/Card';
import Stack from '@mui/material/Stack';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { getPurchaseDiscountReport, getSalesDiscountReport } from '@/api/resources';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { PageTitle } from '@/contextHelp';
import { t } from '@/i18n';
import type { DiscountReportResponse } from '@/types/domain';
import { formatMoney } from '@/utils/money';
import { DataTable, DateRangeFields } from '@/pages/phase/phaseShared';

type DocType = 'sales' | 'purchases';
type BreakdownView = 'party' | 'product' | 'period';

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <Card variant="outlined" sx={{ p: 2, flex: 1, minWidth: 160 }}>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="h6">{value}</Typography>
    </Card>
  );
}

export function DiscountReportPage() {
  const [docType, setDocType] = useState<DocType>('sales');
  const [breakdown, setBreakdown] = useState<BreakdownView>('party');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  const query = useQuery({
    queryKey: ['discount-report', docType, dateFrom, dateTo],
    queryFn: () =>
      (docType === 'sales' ? getSalesDiscountReport : getPurchaseDiscountReport)({
        ...(dateFrom ? { date_from: dateFrom } : {}),
        ...(dateTo ? { date_to: dateTo } : {}),
      }) as Promise<DiscountReportResponse>,
  });

  const data = query.data;
  const partyLabel = docType === 'sales' ? t('common.customer') : t('common.supplier');

  const rows = useMemo(() => {
    if (!data) return [];
    if (breakdown === 'party') return data.byParty;
    if (breakdown === 'product') return data.byProduct;
    return data.byPeriod;
  }, [data, breakdown]);

  const columns = useMemo(() => {
    if (breakdown === 'party') {
      return [
        { key: 'name', label: partyLabel },
        { key: 'invoices', label: t('common.invoices') },
        { key: 'revenue', label: t('common.revenue'), money: true },
        { key: 'lineDiscount', label: t('reports.lineDiscount'), money: true },
      ];
    }
    if (breakdown === 'product') {
      return [
        { key: 'product', label: t('common.product') },
        { key: 'revenue', label: t('common.revenue'), money: true },
        { key: 'lineDiscount', label: t('reports.lineDiscount'), money: true },
      ];
    }
    return [
      { key: 'period', label: t('common.period') },
      { key: 'revenue', label: t('common.revenue'), money: true },
      { key: 'lineDiscount', label: t('reports.lineDiscount'), money: true },
    ];
  }, [breakdown, partyLabel]);

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1}>
        <PageTitle>{t('nav.discountReport')}</PageTitle>
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
          <ToggleButtonGroup
            value={docType}
            exclusive
            size="small"
            onChange={(_, value: DocType | null) => value && setDocType(value)}
          >
            <ToggleButton value="sales">{t('nav.salesReports')}</ToggleButton>
            <ToggleButton value="purchases">{t('nav.purchaseReports')}</ToggleButton>
          </ToggleButtonGroup>
          <DateRangeFields from={dateFrom} to={dateTo} onFromChange={setDateFrom} onToChange={setDateTo} />
        </Stack>
      </Stack>

      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}

      {data ? (
        <>
          <Stack direction="row" flexWrap="wrap" gap={2}>
            <StatCard label={t('common.invoices')} value={String(data.totals.invoiceCount)} />
            <StatCard label={t('reports.discountedInvoices')} value={String(data.totals.discountedInvoiceCount)} />
            <StatCard label={t('reports.lineDiscount')} value={formatMoney(data.totals.lineDiscountTotal)} />
            <StatCard label={t('reports.headerDiscount')} value={formatMoney(data.totals.headerDiscountTotal)} />
            <StatCard label={t('reports.totalDiscount')} value={formatMoney(data.totals.totalDiscount)} />
            <StatCard label={t('reports.avgDiscountPercent')} value={`${formatMoney(data.totals.avgDiscountPercent)}%`} />
          </Stack>

          <ToggleButtonGroup
            value={breakdown}
            exclusive
            size="small"
            onChange={(_, value: BreakdownView | null) => value && setBreakdown(value)}
          >
            <ToggleButton value="party">{partyLabel}</ToggleButton>
            <ToggleButton value="product">{t('common.product')}</ToggleButton>
            <ToggleButton value="period">{t('common.period')}</ToggleButton>
          </ToggleButtonGroup>

          {rows.length === 0 ? (
            <EmptyState description={t('empty.reports')} />
          ) : (
            <DataTable rows={rows as never} columns={columns} empty={t('empty.reports')} virtualized />
          )}
        </>
      ) : null}
    </Stack>
  );
}
