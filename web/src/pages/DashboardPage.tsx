import Box from '@mui/material/Box';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import Button from '@mui/material/Button';
import { useQuery } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { getDashboard, listLowStock } from '@/api/resources';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { StatusChip } from '@/components/StatusChip';
import { t } from '@/i18n';
import type { DashboardKpis } from '@/types/domain';
import { formatMoney, toNumber } from '@/utils/money';
import { documentStatusTone, statusLabelKey } from '@/utils/status';

function KpiCard({ label, value }: { label: string; value: string }) {
  return (
    <Paper sx={{ p: 2.5, height: '100%' }}>
      <Typography variant="body2" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="h5" sx={{ mt: 1 }}>
        {value}
      </Typography>
    </Paper>
  );
}

// BUG-601: the backend already computes and returns these aging buckets on
// every /dashboard/ call — the frontend previously never read them at all.
// The camelCase renderer's exact key shape for numeric-prefixed segments
// (days_1_30 etc.) wasn't confirmed when this type was written, so accept
// any of the documented variants rather than silently showing nothing.
function agingBucket(aging: NonNullable<DashboardKpis['receivablesAging']>, keys: string[]): number {
  for (const key of keys) {
    const value = (aging as Record<string, unknown>)[key];
    if (value != null) return toNumber(value as string | number);
  }
  return 0;
}

export function DashboardPage() {
  const dashboard = useQuery({ queryKey: ['dashboard'], queryFn: getDashboard });
  const lowStock = useQuery({ queryKey: ['low-stock'], queryFn: listLowStock });

  if (dashboard.isLoading) return <LoadingState />;
  if (dashboard.isError) {
    return (
      <ErrorState message={getErrorMessage(dashboard.error)} onRetry={() => void dashboard.refetch()} />
    );
  }

  const data = dashboard.data!;
  const aging = data.receivablesAging;
  const agingBuckets = aging
    ? [
        { label: t('dashboard.agingCurrent'), value: agingBucket(aging, ['current']) },
        {
          label: t('dashboard.aging1to30'),
          value: agingBucket(aging, ['days130', 'days1_30', 'days_1_30']),
        },
        {
          label: t('dashboard.aging31to60'),
          value: agingBucket(aging, ['days3160', 'days31_60', 'days_31_60']),
        },
        {
          label: t('dashboard.aging61to90'),
          value: agingBucket(aging, ['days6190', 'days61_90', 'days_61_90']),
        },
        {
          label: t('dashboard.aging90plus'),
          value: agingBucket(aging, ['days90Plus', 'days_90_plus']),
        },
      ]
    : [];

  return (
    <Stack spacing={3}>
      <Typography variant="h4">{t('nav.dashboard')}</Typography>
      <Box
        sx={{
          display: 'grid',
          gap: 2,
          gridTemplateColumns: {
            xs: '1fr',
            sm: 'repeat(2, 1fr)',
            md: 'repeat(3, 1fr)',
          },
        }}
      >
        <KpiCard label={t('dashboard.todaySales')} value={formatMoney(data.salesToday?.total)} />
        <KpiCard label={t('dashboard.monthSales')} value={formatMoney(data.salesThisMonth?.total)} />
        <KpiCard
          label={t('dashboard.purchasesThisMonth')}
          value={formatMoney(data.purchasesThisMonth?.total)}
        />
        <KpiCard label={t('dashboard.lowStock')} value={String(data.lowStockCount ?? 0)} />
        <KpiCard label={t('dashboard.receivables')} value={formatMoney(data.receivables)} />
        <KpiCard label={t('dashboard.payables')} value={formatMoney(data.payables)} />
      </Box>

      {agingBuckets.length > 0 ? (
        <Paper sx={{ p: 2.5 }}>
          <Typography variant="h6" sx={{ mb: 2 }}>
            {t('dashboard.receivablesAging')}
          </Typography>
          <Box
            sx={{
              display: 'grid',
              gap: 2,
              gridTemplateColumns: { xs: 'repeat(2, 1fr)', sm: 'repeat(5, 1fr)' },
            }}
          >
            {agingBuckets.map((bucket) => (
              <Box key={bucket.label}>
                <Typography variant="body2" color="text.secondary">
                  {bucket.label}
                </Typography>
                <Typography variant="subtitle1" fontWeight={600}>
                  {formatMoney(bucket.value)}
                </Typography>
              </Box>
            ))}
          </Box>
        </Paper>
      ) : null}

      {data.recentInvoices && data.recentInvoices.length > 0 ? (
        <Paper sx={{ p: 2.5, overflow: 'auto' }}>
          <Typography variant="h6" sx={{ mb: 2 }}>
            {t('dashboard.recentInvoices')}
          </Typography>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('common.number')}</TableCell>
                <TableCell>{t('common.date')}</TableCell>
                <TableCell>{t('billing.customer')}</TableCell>
                <TableCell>{t('common.status')}</TableCell>
                <TableCell align="right">{t('common.total')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {data.recentInvoices.map((inv) => (
                <TableRow key={inv.id} hover>
                  <TableCell>
                    <Typography
                      component={RouterLink}
                      to={`/sales/history/${inv.id}`}
                      sx={{ color: 'primary.main', textDecoration: 'none' }}
                    >
                      {inv.number ?? `Draft #${inv.id}`}
                    </Typography>
                  </TableCell>
                  <TableCell>{inv.date}</TableCell>
                  <TableCell>{inv.customer ?? '—'}</TableCell>
                  <TableCell>
                    <StatusChip tone={documentStatusTone(inv.status)} labelKey={statusLabelKey(inv.status)} />
                  </TableCell>
                  <TableCell align="right">{formatMoney(inv.grandTotal)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}

      <Paper sx={{ p: 2.5 }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
          <Typography variant="h6">{t('dashboard.alerts')}</Typography>
          <Button component={RouterLink} to="/sales/new" variant="contained">
            {t('nav.newInvoice')}
          </Button>
        </Stack>
        {lowStock.isLoading ? (
          <LoadingState />
        ) : lowStock.isError ? (
          // BUG-611: previously an errored low-stock query was
          // indistinguishable from "nothing is low on stock" — a real
          // reassurance-when-there-shouldn't-be-one failure mode.
          <ErrorState message={getErrorMessage(lowStock.error)} onRetry={() => void lowStock.refetch()} />
        ) : (lowStock.data?.length ?? 0) === 0 ? (
          <EmptyState description={t('empty.stock')} />
        ) : (
          <Stack spacing={1}>
            {lowStock.data!.slice(0, 5).map((item) => (
              <Typography key={item.product}>
                {item.productName} — available {toNumber(item.available)} (reorder{' '}
                {toNumber(item.reorderLevel)})
              </Typography>
            ))}
            <Button component={RouterLink} to="/inventory/low-stock" size="small">
              {t('nav.lowStock')}
            </Button>
          </Stack>
        )}
      </Paper>
    </Stack>
  );
}
