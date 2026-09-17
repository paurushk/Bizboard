import Box from '@mui/material/Box';
import Alert from '@mui/material/Alert';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import { useQuery } from '@tanstack/react-query';
import { Link as RouterLink, Navigate } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { getDashboard, getBusinessHealth, getCompany, getDailySummary, listBusinessAlerts, listLowStock } from '@/api/resources';
import { getShopFloorSummary, funnelCount, funnelReasons } from '@/lib/telemetry';
import { canCreateSales, canViewAiInsights, isOwner } from '@/utils/permissions';
import { KpiStat, MoneyText, PageHeader, SeverityChip } from '@/components/insights';
import { OnboardingChecklist } from '@/components/OnboardingChecklist';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { StatusChip } from '@/components/StatusChip';
import { AttentionQueuePreview } from '@/pages/AttentionPage';
import { CollectionAttentionCard } from '@/components/CollectionAttentionCard';
import { useAuth } from '@/auth/AuthContext';
import { t, useLocale } from '@/i18n';
import type { DashboardKpis } from '@/types/domain';
import { formatMoney, toNumber } from '@/utils/money';
import { documentStatusTone, paidAwareStatus, statusLabelKey } from '@/utils/status';
import { canViewPaymentSurfaces } from '@/utils/permissions';
import { shouldForceSetup } from '@/onboarding/shouldForceSetup';
import { useState } from 'react';

function agingBucket(aging: NonNullable<DashboardKpis['receivablesAging']>, keys: string[]): number {
  for (const key of keys) {
    const value = (aging as Record<string, unknown>)[key];
    if (value != null) return toNumber(value as string | number);
  }
  return 0;
}

export function DashboardPage() {
  useLocale();
  const { user } = useAuth();
  const [inviteCtaDismissed, setInviteCtaDismissed] = useState(
    () => localStorage.getItem('bb_invite_cta_dismissed') === '1',
  );
  const showInsights = canViewAiInsights(user);
  const dashboard = useQuery({ queryKey: ['dashboard'], queryFn: getDashboard });
  const company = useQuery({ queryKey: ['company'], queryFn: getCompany });
  const lowStock = useQuery({ queryKey: ['low-stock'], queryFn: listLowStock });
  const summary = useQuery({
    queryKey: ['insights-summary'],
    queryFn: () => getDailySummary(),
    retry: false,
    enabled: showInsights,
  });
  const bizAlerts = useQuery({
    queryKey: ['insights-alerts'],
    queryFn: () => listBusinessAlerts(),
    retry: false,
    enabled: showInsights,
  });
  const health = useQuery({
    queryKey: ['insights-health'],
    queryFn: getBusinessHealth,
    retry: false,
    enabled: showInsights,
  });
  const shopFloor = useQuery({
    queryKey: ['shop-floor-telemetry'],
    queryFn: getShopFloorSummary,
    retry: false,
    enabled: isOwner(user?.role ?? 'VIEWER'),
  });

  if (!company.isLoading && shouldForceSetup(user, company.data)) {
    return <Navigate to="/setup" replace />;
  }

  if (dashboard.isLoading) return <LoadingState />;
  if (dashboard.isError) {
    return (
      <ErrorState message={getErrorMessage(dashboard.error)} error={dashboard.error} onRetry={() => void dashboard.refetch()} />
    );
  }

  const data = dashboard.data!;
  const productCount = data.productCount ?? data.product_count ?? 0;
  const invoiceCount = data.invoiceCount ?? data.invoice_count ?? 0;
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

  const topBiz = (bizAlerts.data ?? []).slice(0, 3);
  const payablesAging = data.payablesAging ?? data.payables_aging;
  const payablesAgingBuckets = payablesAging
    ? [
        { label: t('dashboard.agingCurrent'), value: agingBucket(payablesAging, ['current']) },
        {
          label: t('dashboard.aging1to30'),
          value: agingBucket(payablesAging, ['days130', 'days1_30', 'days_1_30']),
        },
        {
          label: t('dashboard.aging31to60'),
          value: agingBucket(payablesAging, ['days3160', 'days31_60', 'days_31_60']),
        },
        {
          label: t('dashboard.aging61to90'),
          value: agingBucket(payablesAging, ['days6190', 'days61_90', 'days_61_90']),
        },
        {
          label: t('dashboard.aging90plus'),
          value: agingBucket(payablesAging, ['days90Plus', 'days_90_plus']),
        },
      ]
    : [];
  const healthChip = health.data ? (
    <Chip
      component={RouterLink}
      to="/insights/health"
      clickable
      color={Number(health.data.score) >= 70 ? 'success' : Number(health.data.score) >= 45 ? 'warning' : 'error'}
      label={
        Number(health.data.score) >= 70
          ? t('dashboard.healthHealthy')
          : Number(health.data.score) >= 45
            ? t('dashboard.healthAttention')
            : t('dashboard.healthAction')
      }
      title={`${t('dashboard.healthGradeTitle', {
        grade: health.data.grade,
        score: health.data.score,
      })}${health.data.limitedData ? ` · ${t('dashboard.limitedData')}` : ''}`}
    />
  ) : null;

  return (
    <Stack spacing={3}>
      <PageHeader
        title={t('nav.dashboard')}
        actions={
          <Stack direction="row" spacing={1}>
            {showInsights ? (
              <Button component={RouterLink} to="/insights" size="small" variant="outlined">
                {t('nav.insights')}
              </Button>
            ) : null}
            {canCreateSales(user) ? (
              <Button component={RouterLink} to="/sales/new" variant="contained">
                {t('nav.newInvoice')}
              </Button>
            ) : null}
          </Stack>
        }
      />

      <OnboardingChecklist
        company={company.data}
        productCount={productCount}
        invoiceCount={invoiceCount}
      />

      {shopFloor.data ? (
        <Paper sx={{ p: 2 }}>
          <Typography variant="subtitle1" fontWeight={600} gutterBottom>
            {t('dashboard.shopFloor')}
          </Typography>
          <ShopFloorFunnel summary={shopFloor.data} />
        </Paper>
      ) : null}

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
          <Typography variant="h6">{t('dashboard.needsAttention')}</Typography>
          <Button component={RouterLink} to="/attention" size="small">
            {t('attention.seeAll')}
          </Button>
        </Stack>
        <AttentionQueuePreview />
      </Paper>

      {canViewPaymentSurfaces(user) ? <CollectionAttentionCard /> : null}

      {!inviteCtaDismissed &&
      user?.role === 'OWNER' &&
      productCount > 0 &&
      invoiceCount > 0 ? (
        <Alert
          severity="success"
          onClose={() => {
            localStorage.setItem('bb_invite_cta_dismissed', '1');
            setInviteCtaDismissed(true);
          }}
          action={<Button component={RouterLink} to="/settings/users">{t('onboarding.inviteStaff')}</Button>}
        >
          {t('onboarding.inviteStaffDescription')}
        </Alert>
      ) : null}

      {showInsights && (summary.data || health.data || topBiz.length > 0) ? (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={2} flexWrap="wrap" useFlexGap>
            {summary.data ? (
              <Box sx={{ flex: 1, minWidth: 200 }}>
                <Typography variant="subtitle2" color="text.secondary">
                  {t('insights.todaySummary')}
                </Typography>
                <Typography variant="body2" sx={{ mt: 0.5 }}>
                  {t('dashboard.salesTodayLine', {
                    amount: formatMoney(data.salesToday?.total),
                    count: data.salesToday?.count ?? 0,
                    monthAmount: formatMoney(data.salesThisMonth?.total),
                    monthCount: data.salesThisMonth?.count ?? 0,
                  })}
                </Typography>
              </Box>
            ) : (
              <Box sx={{ flex: 1 }} />
            )}
            {healthChip}
            <Stack spacing={0.5}>
              {topBiz.map((a) => (
                <Stack key={a.id} direction="row" spacing={1} alignItems="center">
                  <SeverityChip severity={a.severity} />
                  <Typography variant="caption" noWrap sx={{ maxWidth: 220 }}>
                    {a.message}
                  </Typography>
                </Stack>
              ))}
              {company.data?.negativeStockPolicy &&
              company.data.negativeStockPolicy !== 'BLOCK' ? (
                <Typography variant="caption" color="warning.main" component={RouterLink} to="/settings/gst">
                  {t('dashboard.negativeStockPolicyNote', { policy: company.data.negativeStockPolicy })}
                </Typography>
              ) : null}
            </Stack>
          </Stack>
        </Paper>
      ) : null}

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
        <KpiStat label={t('dashboard.todaySales')} value={data.salesToday?.total} money />
        <KpiStat label={t('dashboard.monthSales')} value={data.salesThisMonth?.total} money />
        <KpiStat label={t('dashboard.purchasesThisMonth')} value={data.purchasesThisMonth?.total} money />
        <KpiStat label={t('dashboard.lowStock')} value={data.lowStockCount ?? 0} />
        <KpiStat label={t('dashboard.receivables')} value={data.receivables} money />
        <KpiStat label={t('dashboard.payables')} value={data.payables} money />
        {data.cashPosition != null || data.cash_position != null ? (
          <KpiStat
            label={t('dashboard.cashPosition')}
            value={
              typeof (data.cashPosition ?? data.cash_position) === 'object'
                ? ((data.cashPosition ?? data.cash_position) as { closing?: number }).closing ?? 0
                : (data.cashPosition ?? data.cash_position ?? 0)
            }
            money
          />
        ) : null}
      </Box>

      {agingBuckets.length > 0 ? (
        <Stack spacing={1.5}>
          <Typography variant="h6">{t('dashboard.receivablesAging')}</Typography>
          <Box
            sx={{
              display: 'grid',
              gap: 1.5,
              gridTemplateColumns: { xs: 'repeat(2, 1fr)', sm: 'repeat(5, 1fr)' },
            }}
          >
            {agingBuckets.map((bucket) => (
              <KpiStat key={bucket.label} label={bucket.label} value={bucket.value} money dense />
            ))}
          </Box>
        </Stack>
      ) : null}

      {payablesAgingBuckets.length > 0 ? (
        <Stack spacing={1.5}>
          <Typography variant="h6">{t('dashboard.payablesAging')}</Typography>
          <Box
            sx={{
              display: 'grid',
              gap: 1.5,
              gridTemplateColumns: { xs: 'repeat(2, 1fr)', sm: 'repeat(5, 1fr)' },
            }}
          >
            {payablesAgingBuckets.map((bucket) => (
              <KpiStat key={bucket.label} label={bucket.label} value={bucket.value} money dense />
            ))}
          </Box>
        </Stack>
      ) : null}

      {data.recentInvoices && data.recentInvoices.length > 0 ? (
        <Paper variant="outlined" sx={{ p: 2.5, overflow: 'auto' }}>
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
                    <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                      <StatusChip
                        tone={documentStatusTone(paidAwareStatus(inv.status, inv.balance, inv.paymentState))}
                        labelKey={statusLabelKey(paidAwareStatus(inv.status, inv.balance, inv.paymentState))}
                      />
                      {inv.returnState === 'PARTIAL' ? (
                        <StatusChip tone="warning" labelKey="status.PARTIALLY_RETURNED" />
                      ) : null}
                    </Stack>
                  </TableCell>
                  <TableCell align="right">
                    <MoneyText value={inv.grandTotal} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}

      <Stack spacing={1.5}>
        <PageHeader
          title={t('dashboard.alerts')}
        />
        {lowStock.isLoading ? (
          <LoadingState />
        ) : lowStock.isError ? (
          <ErrorState message={getErrorMessage(lowStock.error)} error={lowStock.error} onRetry={() => void lowStock.refetch()} />
        ) : (lowStock.data?.length ?? 0) === 0 ? (
          <EmptyState description={t('empty.stockHealthy')} />
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
      </Stack>
    </Stack>
  );
}

function ShopFloorFunnel({ summary }: { summary: import('@/lib/telemetry').ShopFloorSummary }) {
  const funnel = summary.funnel;
  const p95 = summary.completeP95Ms ?? summary.complete_p95_ms;
  const offline = summary.offlineFlushFail ?? summary.offline_flush_fail ?? 0;
  const reasons = funnelReasons(
    funnel,
    'invoice_complete_failed_by_reason',
    'invoiceCompleteFailedByReason',
  );
  const reasonBits = Object.entries(reasons).filter(([, n]) => n > 0);
  const rows: { key: string; started: number | string; completed: number | string; failed: number }[] = [
    {
      key: 'invoice',
      started: funnelCount(funnel, 'invoice_complete_started', 'invoiceCompleteStarted'),
      completed: funnelCount(funnel, 'invoice_complete', 'invoiceComplete'),
      failed: funnelCount(funnel, 'invoice_complete_failed', 'invoiceCompleteFailed'),
    },
    {
      key: 'pdf',
      started: funnelCount(funnel, 'pdf_started', 'pdfStarted'),
      completed: '—',
      failed: funnelCount(funnel, 'pdf_failed', 'pdfFailed'),
    },
    {
      key: 'payment',
      started: funnelCount(funnel, 'payment_started', 'paymentStarted'),
      completed: funnelCount(funnel, 'payment_completed', 'paymentCompleted'),
      failed: funnelCount(funnel, 'payment_failed', 'paymentFailed'),
    },
    {
      key: 'signup',
      started: '—',
      completed: funnelCount(funnel, 'signup_completed', 'signupCompleted'),
      failed: funnelCount(funnel, 'signup_failed', 'signupFailed'),
    },
  ];
  return (
    <Stack spacing={2}>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={3}>
        <Typography variant="body2">
          {t('dashboard.completeP95')}: {p95 != null ? `${p95} ms` : '—'}
        </Typography>
        <Typography variant="body2">
          {t('dashboard.offlineFails')}: {offline}
        </Typography>
      </Stack>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>{t('dashboard.journey')}</TableCell>
            <TableCell align="right">{t('dashboard.journeyStarted')}</TableCell>
            <TableCell align="right">{t('dashboard.journeyCompleted')}</TableCell>
            <TableCell align="right">{t('dashboard.journeyFailed')}</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.key}>
              <TableCell>
                {row.key === 'invoice'
                  ? t('dashboard.journeyInvoice')
                  : row.key === 'pdf'
                    ? t('dashboard.journeyPdf')
                    : row.key === 'payment'
                      ? t('dashboard.journeyPayment')
                      : t('dashboard.journeySignup')}
              </TableCell>
              <TableCell align="right">{row.started}</TableCell>
              <TableCell align="right">{row.completed}</TableCell>
              <TableCell align="right">{row.failed}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {reasonBits.length ? (
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          <Typography variant="body2" color="text.secondary">
            {t('dashboard.failedReasons')}:
          </Typography>
          {reasonBits.map(([reason, n]) => (
            <Chip key={reason} size="small" label={`${reason}: ${n}`} />
          ))}
        </Stack>
      ) : null}
    </Stack>
  );
}
