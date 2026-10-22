import { useState } from 'react';
import Accordion from '@mui/material/Accordion';
import AccordionDetails from '@mui/material/AccordionDetails';
import AccordionSummary from '@mui/material/AccordionSummary';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getBillingPortal, startBillingCheckout } from '@/api/billing';
import { PlanChangeNotice } from '@/components/billing/PlanChangeNotice';
import { billingOps, listVendorTenants, suspendSubscription } from '@/api/roadmap';
import { isAllowedPaymentUrl } from '@/utils/safeUrl';
import { useAuth } from '@/auth/AuthContext';
import { BizboardInvoicesPanel } from '@/components/billing/BizboardInvoicesPanel';
import { SuspendWorkspaceDialog, type SuspendInput } from '@/components/billing/SuspendWorkspaceDialog';
import { AsyncSection } from '@/components/settings/AsyncSection';
import { SettingsPage } from '@/components/settings/SettingsPage';
import { t } from '@/i18n';
import { ForbiddenPage } from '@/pages/ForbiddenPage';
import { formatMoney } from '@/utils/money';
import { canManageUsers } from '@/utils/permissions';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { settingsErrorText } from '@/utils/settingsErrors';

function formatPaise(paise: number): string {
  return `${formatMoney(paise / 100)} ${t('cog.perMonth')}`;
}

/**
 * Plan, usage and checkout. The one destructive action, suspending the workspace, sits apart in a
 * collapsed danger zone and asks for more than a click. Operator tooling (parked billing events)
 * is in the Django admin, not here.
 */
export function BillingPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ['billing-portal', user?.companyId], queryFn: getBillingPortal });
  const ops = useQuery({ queryKey: ['billing-ops', user?.companyId], queryFn: billingOps, enabled: canManageUsers(user) });
  const tenants = useQuery({
    queryKey: ['vendor-tenants', user?.companyId],
    queryFn: listVendorTenants,
    enabled: canManageUsers(user),
  });
  const checkout = useMutation({
    mutationFn: (planId: number) => startBillingCheckout(planId),
    onSuccess: (res) => {
      void qc.invalidateQueries({ queryKey: ['billing-portal'] });
      // F3-033: if the gateway returned a hosted-checkout page, send the user
      // there instead of only refetching a query in the background.
      const url = (res as { checkoutUrl?: string | null }).checkoutUrl;
      const proration = res.prorationUrl;
      // WP-BL3: an upgrade has two steps (pay the difference, approve the new mandate), so show
      // both links instead of leaving the page.
      if (proration && isAllowedPaymentUrl(proration)) {
        setUpgradeLinks({ prorationUrl: proration, checkoutUrl: url && isAllowedPaymentUrl(url) ? url : null });
        return;
      }
      if (url && isAllowedPaymentUrl(url)) {
        window.location.assign(url);
      }
    },
  });
  const [upgradeLinks, setUpgradeLinks] = useState<{ prorationUrl?: string | null; checkoutUrl?: string | null } | null>(null);
  const [suspendOpen, setSuspendOpen] = useState(false);
  const [suspendError, setSuspendError] = useState('');
  const suspend = useMutation({
    mutationFn: (input: SuspendInput) => suspendSubscription(input),
    onSuccess: () => {
      setSuspendOpen(false);
      setSuspendError('');
      void qc.invalidateQueries({ queryKey: ['billing-portal'] });
      void qc.invalidateQueries({ queryKey: ['billing-ops'] });
      void qc.invalidateQueries({ queryKey: ['billing-subscription'] });
    },
    onError: (err) => setSuspendError(settingsErrorText(err)),
  });

  if (!canManageUsers(user)) return <ForbiddenPage />;

  return (
    <SettingsPage
      title={t('nav.billing')}
      purpose={t('billingDanger.purpose')}
    >
      <AsyncSection query={query}>
        {(portal) => {
          const sub = portal.subscription ?? null;
          const plans = portal.plans ?? [];
          const seatLimit = portal.seatLimit ?? sub?.plan?.seatLimit ?? null;
          const status = sub?.status ?? 'none';
          const planLine =
            status === 'trial'
              ? t('integrations.freeTrialEnds', { date: sub?.trialEndsAt ? String(sub.trialEndsAt).slice(0, 10) : '' })
              : (sub?.plan?.name ?? t('integrations.noSubscription'));
          const tenantRows = Array.isArray(tenants.data) ? tenants.data : [];
          return (
            <Stack spacing={2} sx={{ maxWidth: 720 }}>
              {!sub ? <Alert severity="warning">{t('integrations.billingClosed')}</Alert> : null}
              <Paper sx={{ p: 3 }}>
                <Stack spacing={1.5}>
                  <Typography variant="h6">{t('sweep2.currentPlan')}</Typography>
                  <Typography>{t('cog.billingStatus', { plan: planLine, status })}</Typography>
                  <Typography variant="body2" color="text.secondary">
                    {t('cog.billingSeats', { count: seatLimit ?? '—' })}
                    {sub?.trialEndsAt ? ` · ${t('cog.trialEndsAt', { date: String(sub.trialEndsAt) })}` : ''}
                    {sub?.currentPeriodEnd ? ` · ${t('cog.periodEnds', { date: String(sub.currentPeriodEnd) })}` : ''}
                  </Typography>
                  <PlanChangeNotice sub={sub} links={upgradeLinks} />
                  {ops.data?.upgradePrompt && (ops.data.upgradePrompt as { show?: boolean }).show ? (
                    <HelpErrorAlert
                      message={t('cog.planLimitReached', {
                        reason: String((ops.data.upgradePrompt as { reason?: string }).reason ?? ''),
                      })}
                    />
                  ) : null}
                  {ops.data?.trialNotice && (ops.data.trialNotice as { show?: boolean }).show ? (
                    <Typography>
                      {t('cog.trialDaysLeft', {
                        days: String((ops.data.trialNotice as { daysLeft?: number }).daysLeft ?? ''),
                      })}
                    </Typography>
                  ) : null}
                  {status === 'suspended' || (status === 'trial' && sub?.writeBlocked) ? (
                    <HelpErrorAlert message={t('cog.writesBlockedBilling')} />
                  ) : null}
                </Stack>
              </Paper>

              <Paper sx={{ p: 3 }}>
                <Typography variant="h6" sx={{ mb: 2 }}>
                  {t('sweep2.availablePlans')}
                </Typography>
                {checkout.isError ? <HelpErrorAlert error={checkout.error} sx={{ mb: 2 }} /> : null}
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
                          {t('settingsSweep.planLine', { price: formatPaise(plan.pricePaise), seats: String(plan.seatLimit) })}
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

              <BizboardInvoicesPanel companyKey={user?.companyId} />

              {tenantRows.length > 0 ? (
                <Paper sx={{ p: 3 }}>
                  <Typography variant="h6" sx={{ mb: 1 }}>
                    {t('billingDanger.tenants')}
                  </Typography>
                  <Stack spacing={0.5}>
                    {tenantRows.map((row) => (
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
              ) : null}

              {sub && status !== 'suspended' ? (
                <Accordion variant="outlined" disableGutters sx={{ borderColor: 'error.main' }}>
                  <AccordionSummary expandIcon={<ExpandMoreIcon />} aria-controls="danger-zone" id="danger-zone-header">
                    <Typography color="error" fontWeight={600}>
                      {t('billingDanger.zoneTitle')}
                    </Typography>
                  </AccordionSummary>
                  <AccordionDetails id="danger-zone">
                    <Stack spacing={1.5}>
                      <Typography variant="body2" color="text.secondary">
                        {t('billingDanger.zoneHelp')}
                      </Typography>
                      <Button
                        variant="outlined"
                        color="error"
                        sx={{ alignSelf: 'flex-start' }}
                        onClick={() => {
                          setSuspendError('');
                          setSuspendOpen(true);
                        }}
                      >
                        {t('billingDanger.open')}
                      </Button>
                    </Stack>
                  </AccordionDetails>
                </Accordion>
              ) : null}

              <SuspendWorkspaceDialog
                open={suspendOpen}
                companyName={user?.company?.name ?? ''}
                periodEnd={sub?.currentPeriodEnd ? String(sub.currentPeriodEnd) : null}
                busy={suspend.isPending}
                error={suspendError}
                onClose={() => setSuspendOpen(false)}
                onConfirm={(input) => suspend.mutate(input)}
              />
            </Stack>
          );
        }}
      </AsyncSection>
    </SettingsPage>
  );
}
