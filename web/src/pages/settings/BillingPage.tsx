import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { getBillingPortal, listBillingDeadLetters, replayBillingDeadLetter, startBillingCheckout } from '@/api/billing';
import { billingOps, listVendorTenants, suspendSubscription } from '@/api/roadmap';
import { isAllowedPaymentUrl } from '@/utils/safeUrl';
import { useAuth } from '@/auth/AuthContext';
import { PageTitle } from '@/contextHelp';
import { t } from '@/i18n';
import { ForbiddenPage } from '@/pages/ForbiddenPage';
import { ErrorState, LoadingState } from '@/components/PageState';
import { formatMoney } from '@/utils/money';
import { canManageUsers } from '@/utils/permissions';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';

function formatPaise(paise: number): string {
  return `${formatMoney(paise / 100)} ${t('cog.perMonth')}`;
}

export function BillingPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ['billing-portal', user?.companyId], queryFn: getBillingPortal });
  const dlqQuery = useQuery({
    queryKey: ['billing-dlq', user?.companyId],
    queryFn: listBillingDeadLetters,
    enabled: canManageUsers(user),
  });
  const checkout = useMutation({
    mutationFn: (planId: number) => startBillingCheckout(planId),
    onSuccess: (res) => {
      void qc.invalidateQueries({ queryKey: ['billing-portal'] });
      // F3-033: if the gateway returned a hosted-checkout page, send the user
      // there instead of only refetching a query in the background.
      const url = (res as { checkoutUrl?: string | null }).checkoutUrl;
      if (url && isAllowedPaymentUrl(url)) {
        window.location.assign(url);
      }
    },
  });
  const [churnReason, setChurnReason] = useState('');
  const [suspendError, setSuspendError] = useState('');
  const ops = useQuery({ queryKey: ['billing-ops', user?.companyId], queryFn: billingOps, enabled: canManageUsers(user) });
  const tenants = useQuery({ queryKey: ['vendor-tenants', user?.companyId], queryFn: listVendorTenants, enabled: canManageUsers(user) });
  const suspend = useMutation({
    mutationFn: () => suspendSubscription(churnReason),
    onSuccess: () => {
      setChurnReason('');
      setSuspendError('');
      void qc.invalidateQueries({ queryKey: ['billing-portal'] });
      void qc.invalidateQueries({ queryKey: ['billing-ops'] });
      void qc.invalidateQueries({ queryKey: ['billing-subscription'] });
    },
    onError: (err) => setSuspendError(getErrorMessage(err)),
  });
  const replayDeadLetter = useMutation({
    mutationFn: (id: number) => replayBillingDeadLetter(id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['billing-dlq'] }),
  });

  if (!canManageUsers(user)) return <ForbiddenPage />;
  if (query.isLoading) return <LoadingState />;
  if (query.isError) {
    return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  }

  const sub = query.data?.subscription ?? null;
  const plans = query.data?.plans ?? [];
  const seatLimit = query.data?.seatLimit ?? sub?.plan?.seatLimit ?? null;
  const status = sub?.status ?? 'none';
  const planLine = status === 'trial'
    ? t('integrations.freeTrialEnds', { date: sub?.trialEndsAt ? String(sub.trialEndsAt).slice(0, 10) : '' })
    : (sub?.plan?.name ?? t('integrations.noSubscription'));

  return (
    <Stack spacing={2} sx={{ maxWidth: 720 }}>
      <PageTitle>{t('nav.billing')}</PageTitle>
      {!sub ? <Alert severity="warning">{t('integrations.billingClosed')}</Alert> : null}
      <Paper sx={{ p: 3 }}>
        <Stack spacing={1.5}>
          <Typography variant="h6">{t('sweep2.currentPlan')}</Typography>
          <Typography>
            {t('cog.billingStatus', { plan: planLine, status })}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {t('cog.billingSeats', { count: seatLimit ?? '—' })}
            {sub?.trialEndsAt ? ` · ${t('cog.trialEndsAt', { date: String(sub.trialEndsAt) })}` : ''}
            {sub?.currentPeriodEnd ? ` · ${t('cog.periodEnds', { date: String(sub.currentPeriodEnd) })}` : ''}
          </Typography>
          {ops.data?.upgradePrompt && (ops.data.upgradePrompt as { show?: boolean }).show ? (
            <HelpErrorAlert message={t('cog.planLimitReached', { reason: String((ops.data.upgradePrompt as { reason?: string }).reason ?? '') })} />
          ) : null}
          {ops.data?.trialNotice && (ops.data.trialNotice as { show?: boolean }).show ? (
            <Typography>{t('cog.trialDaysLeft', { days: String((ops.data.trialNotice as { daysLeft?: number }).daysLeft ?? '') })}</Typography>
          ) : null}
          {status === 'suspended' || (status === 'trial' && sub?.writeBlocked) ? (
            <HelpErrorAlert message={t('cog.writesBlockedBilling')} />
          ) : null}
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
            <TextField size="small" label={t('sweep.churnReason')} value={churnReason} onChange={(e) => setChurnReason(e.target.value)} />
            <Button
              variant="outlined"
              disabled={!churnReason.trim() || suspend.isPending}
              onClick={() => {
                if (window.confirm(t('cog.suspendWorkspace'))) {
                  suspend.mutate();
                }
              }}
            >
              {t('sweep2.suspend')}
            </Button>
          </Stack>
          {suspendError ? <HelpErrorAlert message={suspendError} /> : null}
          {(Array.isArray(tenants.data) ? tenants.data : []).map((row) => (
            <Typography key={String(row.sourceCompanyId)} variant="body2">
              {t('cog.vendorTenantLine', {
                name: String(row.sourceCompanyName),
                setup: row.setupCompletedAt ? t('cog.setupDone') : t('cog.setupOpen'),
                invoice: row.firstInvoiceAt ? t('cog.invoiceYes') : t('cog.invoiceNo'),
              })}
              {row.churnReason ? ` · ${String(row.churnReason)}` : ''}
            </Typography>
          ))}
        </Stack>
      </Paper>
      <Paper sx={{ p: 3 }}>
        <Typography variant="h6" sx={{ mb: 2 }}>
          {t('sweep2.availablePlans')}
        </Typography>
        {checkout.isError ? (
          <HelpErrorAlert error={checkout.error} sx={{ mb: 2 }} />
        ) : null}
        <Stack spacing={1.5}>
          {plans.map((plan) => (
            <Stack
              key={plan.id}
              direction={{ xs: 'column', sm: 'row' }}
              spacing={1}
              alignItems={{ sm: 'center' }}
              justifyContent="space-between"
            >
              <div>
                <Typography fontWeight={600}>{plan.name}</Typography>
                <Typography variant="body2" color="text.secondary">
                  {formatPaise(plan.pricePaise)} · {plan.seatLimit} seats
                </Typography>
              </div>
              <Button
                variant={sub?.plan?.id === plan.id ? 'outlined' : 'contained'}
                disabled={checkout.isPending || sub?.plan?.id === plan.id}
                onClick={() => checkout.mutate(plan.id)}
              >
                {sub?.plan?.id === plan.id ? t('cog.currentPlan') : t('cog.startCheckout')}
              </Button>
            </Stack>
          ))}
          {plans.length === 0 ? (
            <Typography color="text.secondary">{t('sweep2.noPlansYet')}</Typography>
          ) : null}
        </Stack>
      </Paper>
      {dlqQuery.data && dlqQuery.data.length > 0 ? (
        <Paper sx={{ p: 3 }}>
          <Typography variant="h6" sx={{ mb: 2 }}>
            {t('sweep2.parkedBillingEvents')}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            {t('cog.parkedBillingHelp')}
          </Typography>
          {replayDeadLetter.isError ? <HelpErrorAlert error={replayDeadLetter.error} sx={{ mb: 2 }} /> : null}
          <Stack spacing={1.5}>
            {dlqQuery.data.map((event) => (
              <Stack
                key={event.id}
                direction={{ xs: 'column', sm: 'row' }}
                spacing={1}
                alignItems={{ sm: 'center' }}
                justifyContent="space-between"
              >
                <div>
                  <Stack direction="row" spacing={1} alignItems="center">
                    <Typography fontWeight={600}>{event.provider}</Typography>
                    <Chip size="small" label={event.status} color={event.status === 'pending' ? 'warning' : 'default'} />
                  </Stack>
                  <Typography variant="body2" color="text.secondary">
                    {event.error || event.eventId}
                  </Typography>
                </div>
                <Button
                  variant="outlined"
                  disabled={event.status !== 'pending' || replayDeadLetter.isPending}
                  onClick={() => replayDeadLetter.mutate(event.id)}
                >
                  {t('sweep2.replay')}
                </Button>
              </Stack>
            ))}
          </Stack>
        </Paper>
      ) : null}
    </Stack>
  );
}
