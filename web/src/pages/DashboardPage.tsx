import Box from '@mui/material/Box';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import Button from '@mui/material/Button';
import { useQuery } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { getDashboard, listLowStock } from '@/api/resources';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';
import { formatMoney, toNumber } from '@/utils/money';

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

export function DashboardPage() {
  const dashboard = useQuery({ queryKey: ['dashboard'], queryFn: getDashboard });
  const lowStock = useQuery({ queryKey: ['low-stock'], queryFn: listLowStock });

  if (dashboard.isLoading) return <LoadingState />;
  if (dashboard.isError) {
    return <ErrorState message={dashboard.error.message} onRetry={() => void dashboard.refetch()} />;
  }

  const data = dashboard.data!;

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
          label={t('dashboard.unpaid')}
          value={formatMoney(data.purchasesThisMonth?.total)}
        />
        <KpiCard label={t('dashboard.lowStock')} value={String(data.lowStockCount ?? 0)} />
        <KpiCard label={t('dashboard.receivables')} value={formatMoney(data.receivables)} />
        <KpiCard label={t('dashboard.payables')} value={formatMoney(data.payables)} />
      </Box>

      <Paper sx={{ p: 2.5 }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
          <Typography variant="h6">{t('dashboard.alerts')}</Typography>
          <Button component={RouterLink} to="/sales/new" variant="contained">
            {t('nav.newInvoice')}
          </Button>
        </Stack>
        {lowStock.isLoading ? (
          <LoadingState />
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
