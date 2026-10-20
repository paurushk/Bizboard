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
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link as RouterLink, Navigate } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { getDashboard, getBusinessHealth, getCompany, listLowStock } from '@/api/resources';
import { canCreateSales, canViewAiInsights, canViewFinancialReports } from '@/utils/permissions';
import { ProfitDetailsDialog } from '@/components/ProfitDetailsDialog';
import { KpiStat, MoneyText, PageHeader } from '@/components/insights';
import { isOnboardingComplete, OnboardingChecklist } from '@/components/OnboardingChecklist';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { StatusChip } from '@/components/StatusChip';
import { ForbiddenPage } from '@/pages/ForbiddenPage';
import { AttentionQueuePreview } from '@/pages/AttentionPage';
import { CollectionAttentionCard } from '@/components/CollectionAttentionCard';
import { useAuth } from '@/auth/AuthContext';
import { t, useLocale } from '@/i18n';
import type { DashboardKpis } from '@/types/domain';
import { formatMoney, toNumber } from '@/utils/money';
import { documentStatusTone, invoiceDisplayStatus, statusLabelKey } from '@/utils/status';
import { canViewPaymentSurfaces } from '@/utils/permissions';
import { isMoneyHubEnabled } from '@/config/featureFlags';
import { shouldForceSetup } from '@/onboarding/shouldForceSetup';
import { companyStepIncompleteNeedsGst } from '@/onboarding/taxHints';

function agingBucket(aging: NonNullable<DashboardKpis['receivablesAging']>, keys: string[]): number {
  for (const key of keys) {
    const value = (aging as Record<string, unknown>)[key];
    if (value != null) return toNumber(value as string | number);
  }
  return 0;
}

const visuallyHidden = {
  position: 'absolute',
  width: 1,
  height: 1,
  overflow: 'hidden',
  clip: 'rect(0 0 0 0)',
  whiteSpace: 'nowrap',
} as const;

function negativeStockPolicyLabel(policy: string): string {
  const key = `dashboard.policy_${policy}`;
  const label = t(key);
  return label === key ? policy : label;
}

function inviteCtaKey(user: { id?: number | string; companyId?: number | string } | null): string {
  return `bb_invite_cta_dismissed:${user?.id ?? ''}:${user?.companyId ?? ''}`;
}

function readInviteCtaDismissed(key: string): boolean {
  try {
    return localStorage.getItem(key) === '1';
  } catch {
    return false;
  }
}

export function DashboardPage() {
  useLocale();
  const { user } = useAuth();
  const qc = useQueryClient();
  const canSeeFinancials = canViewFinancialReports(user);
  const ctaKey = inviteCtaKey(user);
  const [inviteCtaDismissed, setInviteCtaDismissed] = useState(() => readInviteCtaDismissed(ctaKey));
  const [profitInvoiceId, setProfitInvoiceId] = useState<number | null>(null);
  const showInsights = canViewAiInsights(user);
  const dashboard = useQuery({ queryKey: ['dashboard'], queryFn: getDashboard, enabled: canSeeFinancials });
  const company = useQuery({ queryKey: ['company'], queryFn: getCompany });
  // The dashboard payload carries the first few low-stock rows. The separate list is only fetched
  // for an older response that lacks them.
  const lowStock = useQuery({
    queryKey: ['low-stock'],
    queryFn: listLowStock,
    enabled: canSeeFinancials && dashboard.isSuccess && dashboard.data?.lowStockItems === undefined,
  });
  const health = useQuery({
    queryKey: ['insights-health'],
    queryFn: getBusinessHealth,
    retry: false,
    enabled: canSeeFinancials,
  });

  if (!company.isLoading && shouldForceSetup(user, company.data)) {
    return <Navigate to="/setup" replace />;
  }

  // Other roles are redirected by HomePage; this guards a direct render or a permission change mid-session.
  if (!canSeeFinancials) return <ForbiddenPage />;

  // One failed query must not blank the whole home screen: the KPI area degrades on its own below.
  const data: DashboardKpis = dashboard.data ?? ({} as DashboardKpis);
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
  const lowStockItems = data.lowStockItems;
  const lowStockRows = lowStockItems ?? lowStock.data ?? [];
  // With the dashboard itself down and no list from elsewhere we do not know the stock position, so say nothing
  // rather than "stock is healthy".
  const lowStockKnown = !dashboard.isError || lowStockItems !== undefined || Boolean(lowStock.data) || lowStock.isError;
  const lowStockLoading = lowStockItems === undefined && (lowStock.isLoading || (dashboard.isLoading && !lowStock.data));
  const refreshAll = () => {
    void dashboard.refetch();
    void qc.invalidateQueries({ queryKey: ['low-stock'] });
    void health.refetch();
    void qc.invalidateQueries({ queryKey: ['attention-rows'] });
  };
  // The server decides the band; the score fallback is only for an older response without one.
  const healthBand =
    health.data?.band ?? (Number(health.data?.score) >= 70 ? 'healthy' : Number(health.data?.score) >= 45 ? 'watch' : 'action');
  const healthChip = health.data ? (
    <Chip
      component={RouterLink}
      to="/insights/health"
      clickable
      color={healthBand === 'healthy' ? 'success' : healthBand === 'watch' ? 'warning' : 'error'}
      label={
        healthBand === 'healthy'
          ? t('dashboard.healthHealthy')
          : healthBand === 'watch'
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
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap justifyContent="flex-end">
            {/* Both routes are behind canViewFinancialReports: other roles would land on Forbidden. */}
            {canViewFinancialReports(user) ? (
              <>
                <Button component={RouterLink} to="/morning" size="small" variant="text">
                  {t('cog.morningTitle')}
                </Button>
                <Button component={RouterLink} to="/reports/close-month" size="small" variant="text">
                  {t('cog.closeMonth')}
                </Button>
              </>
            ) : null}
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

      {dashboard.isSuccess ? (
        <OnboardingChecklist
          company={company.data}
          productCount={productCount}
          invoiceCount={invoiceCount}
        />
      ) : null}

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
          <Typography variant="h6" component="h2">{t('dashboard.needsAttention')}</Typography>
          <Button component={RouterLink} to="/attention" size="small">
            {t('attention.seeAll')}
          </Button>
        </Stack>
        <AttentionQueuePreview />
      </Paper>

      {canViewPaymentSurfaces(user) ? <CollectionAttentionCard /> : null}

      {/* One "getting started" card at a time: the invite prompt waits until the checklist is done. */}
      {!inviteCtaDismissed &&
      user?.role === 'OWNER' &&
      dashboard.isSuccess &&
      isOnboardingComplete(company.data, productCount, invoiceCount) &&
      !companyStepIncompleteNeedsGst(company.data) ? (
        <Alert
          severity="success"
          onClose={() => {
            try {
              localStorage.setItem(ctaKey, '1');
            } catch {
              // Storage blocked: the card is hidden for this visit only.
            }
            setInviteCtaDismissed(true);
          }}
          action={<Button component={RouterLink} to="/settings/users">{t('onboarding.inviteStaff')}</Button>}
        >
          {t('onboarding.inviteStaffDescription')}
        </Alert>
      ) : null}

      <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap" useFlexGap>
        {healthChip}
        {company.data?.negativeStockPolicy && company.data.negativeStockPolicy !== 'BLOCK' ? (
          <Typography variant="caption" color="warning.main" component={RouterLink} to="/settings/gst">
            {t('dashboard.negativeStockPolicyNote', { policy: negativeStockPolicyLabel(company.data.negativeStockPolicy) })}
          </Typography>
        ) : null}
        <Box sx={{ flex: 1 }} />
        {dashboard.dataUpdatedAt ? (
          <Typography variant="caption" color="text.secondary">
            {t('attention.lastUpdated', { time: new Date(dashboard.dataUpdatedAt).toLocaleTimeString() })}
          </Typography>
        ) : null}
        <Button size="small" onClick={refreshAll} disabled={dashboard.isFetching}>
          {t('attention.refresh')}
        </Button>
      </Stack>

      {dashboard.isError ? (
        <ErrorState message={getErrorMessage(dashboard.error)} error={dashboard.error} onRetry={() => void dashboard.refetch()} />
      ) : dashboard.isLoading ? (
        <LoadingState />
      ) : (
        <>
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
        <KpiStat
          label={t('dashboard.lowStock')}
          value={lowStock.isSuccess ? (lowStock.data?.length ?? 0) : (data.lowStockCount ?? 0)}
        />
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
      <Typography variant="caption" color="text.secondary" component="p">
        {t('dashboard.todayNote')}
      </Typography>
      {canViewFinancialReports(user) && isMoneyHubEnabled() ? (
        <Typography variant="body2">
          <RouterLink to="/money">{t('dashboard.seeAllMoney')}</RouterLink>
        </Typography>
      ) : null}

      {agingBuckets.length > 0 ? (
        <Stack spacing={1.5}>
          <Typography variant="h6" component="h2">{t('dashboard.receivablesAging')}</Typography>
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
          {Number(data.receivablesUnclearedCheques) > 0 ? (
            <Typography variant="caption" color="text.secondary">
              {t('customer360.unclearedCheques', { amount: formatMoney(data.receivablesUnclearedCheques ?? 0) })}
            </Typography>
          ) : null}
        </Stack>
      ) : null}

      {payablesAgingBuckets.length > 0 ? (
        <Stack spacing={1.5}>
          <Typography variant="h6" component="h2">{t('dashboard.payablesAging')}</Typography>
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
        <Paper variant="outlined" sx={{ p: 2.5, overflow: 'auto', position: 'relative' }}>
          <Typography variant="h6" component="h2" sx={{ mb: 2 }}>
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
                {canViewFinancialReports(user) ? (
                  <TableCell align="right">
                    <Box component="span" sx={visuallyHidden}>{t('common.actions')}</Box>
                  </TableCell>
                ) : null}
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
                      {inv.number ?? t('dashboard.draftNumber', { id: inv.id })}
                    </Typography>
                  </TableCell>
                  <TableCell>{inv.date}</TableCell>
                  <TableCell>{inv.customer ?? '—'}</TableCell>
                  <TableCell>
                    <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                      <StatusChip
                        tone={documentStatusTone(invoiceDisplayStatus(inv))}
                        labelKey={statusLabelKey(invoiceDisplayStatus(inv))}
                      />
                      {inv.returnState === 'PARTIAL' ? (
                        <StatusChip tone="warning" labelKey="status.PARTIALLY_RETURNED" />
                      ) : null}
                    </Stack>
                  </TableCell>
                  <TableCell align="right">
                    <MoneyText value={inv.grandTotal} />
                  </TableCell>
                  {canViewFinancialReports(user) ? (
                    <TableCell align="right">
                      <Button size="small" onClick={() => setProfitInvoiceId(inv.id)}>
                        {t('invoiceDetail.profitDetails')}
                      </Button>
                    </TableCell>
                  ) : null}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}
        </>
      )}

      {lowStockKnown ? (
      <Stack spacing={1.5}>
        <Typography variant="h6" component="h2">{t('nav.lowStock')}</Typography>
        {lowStockLoading ? (
          <LoadingState />
        ) : lowStock.isError && !lowStockItems ? (
          <ErrorState message={getErrorMessage(lowStock.error)} error={lowStock.error} onRetry={() => void lowStock.refetch()} />
        ) : lowStockRows.length === 0 ? (
          <EmptyState description={t('empty.stockHealthy')} />
        ) : (
          <Stack spacing={1}>
            {lowStockRows.slice(0, 5).map((item) => (
              <Typography key={item.product}>
                {t('dashboard.lowStockLine', {
                  name: item.productName,
                  available: toNumber(item.available),
                  reorder: toNumber(item.reorderLevel),
                })}
              </Typography>
            ))}
            <Button component={RouterLink} to="/inventory/low-stock" size="small">
              {t('nav.lowStock')}
            </Button>
          </Stack>
        )}
      </Stack>
      ) : null}
      <ProfitDetailsDialog
        open={profitInvoiceId != null}
        invoiceId={profitInvoiceId}
        onClose={() => setProfitInvoiceId(null)}
      />
    </Stack>
  );
}
