import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import type { BillingSubscription } from '@/api/billing';
import { t } from '@/i18n';
import { formatMoney } from '@/utils/money';

function day(value?: string | null): string {
  return value ? new Date(value).toLocaleDateString() : '';
}

/**
 * WP-BL3 / WP-BL4: what is happening to the plan and how renewals are collected — an upgrade in
 * effect and its one-time prorated charge, a change waiting for the period end, and the UPI
 * Autopay / card mandate with the next debit date.
 */
export function PlanChangeNotice({
  sub,
  links,
}: {
  sub: BillingSubscription | null;
  links?: { prorationUrl?: string | null; checkoutUrl?: string | null } | null;
}) {
  if (!sub) return null;
  const upgrading = Boolean(sub.upgradePlanName);
  const owed = upgrading && !sub.prorationPaidAt && (sub.prorationAmountPaise ?? 0) > 0;
  return (
    <Stack spacing={1}>
      {upgrading ? (
        <Alert severity={owed ? 'warning' : 'success'}>
          {owed
            ? t('planChange.upgradeOwed', {
                plan: sub.upgradePlanName ?? '',
                amount: formatMoney((sub.prorationAmountPaise ?? 0) / 100),
                until: day(sub.upgradeGraceUntil),
              })
            : t('planChange.upgradePaid', { plan: sub.upgradePlanName ?? '' })}
        </Alert>
      ) : null}
      {links?.prorationUrl || links?.checkoutUrl ? (
        <Stack direction="row" spacing={1} flexWrap="wrap">
          {links.prorationUrl ? (
            <Button variant="contained" href={links.prorationUrl} target="_blank" rel="noopener">
              {t('planChange.payDifference')}
            </Button>
          ) : null}
          {links.checkoutUrl ? (
            <Button variant="outlined" href={links.checkoutUrl} target="_blank" rel="noopener">
              {t('planChange.approveMandate')}
            </Button>
          ) : null}
        </Stack>
      ) : null}
      {sub.pendingPlanName && !upgrading ? (
        <Typography variant="body2">
          {t('planChange.pending', { plan: sub.pendingPlanName, date: day(sub.currentPeriodEnd) })}
        </Typography>
      ) : null}
      {sub.mandateStatus || sub.paymentMethod ? (
        <Typography variant="body2" color="text.secondary">
          {t('planChange.mandate', {
            method: t(`planChange.method.${sub.paymentMethod || 'unknown'}`),
            status: t(`planChange.mandateStatus.${sub.mandateStatus || 'ACTIVE'}`),
            date: day(sub.currentPeriodEnd),
          })}
        </Typography>
      ) : null}
    </Stack>
  );
}
