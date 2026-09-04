import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { getBillingPortal, startBillingCheckout } from '@/api/billing';
import { isAllowedShareUrl } from '@/utils/safeUrl';
import { useAuth } from '@/auth/AuthContext';
import { t } from '@/i18n';
import { ForbiddenPage } from '@/pages/ForbiddenPage';
import { ErrorState, LoadingState } from '@/components/PageState';
import { formatMoney } from '@/utils/money';
import { canManageUsers } from '@/utils/permissions';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';

function formatPaise(paise: number): string {
  return `${formatMoney(paise / 100)} / mo`;
}

export function BillingPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ['billing-portal', user?.companyId], queryFn: getBillingPortal });
  const checkout = useMutation({
    mutationFn: (planId: number) => startBillingCheckout(planId),
    onSuccess: (res) => {
      void qc.invalidateQueries({ queryKey: ['billing-portal'] });
      // F3-033: if the gateway returned a hosted-checkout page, send the user
      // there instead of only refetching a query in the background.
      const url = (res as { checkoutUrl?: string | null }).checkoutUrl;
      if (url && isAllowedShareUrl(url)) {
        window.location.assign(url);
      }
    },
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

  return (
    <Stack spacing={2} sx={{ maxWidth: 720 }}>
      <Typography variant="h4">{t('nav.billing')}</Typography>
      <Paper sx={{ p: 3 }}>
        <Stack spacing={1.5}>
          <Typography variant="h6">Current plan</Typography>
          <Typography>
            {sub?.plan?.name ?? 'No subscription'} · status: {status}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Seats: {seatLimit ?? '—'}
            {sub?.trialEndsAt ? ` · trial ends ${sub.trialEndsAt}` : ''}
            {sub?.currentPeriodEnd ? ` · period ends ${sub.currentPeriodEnd}` : ''}
          </Typography>
          {status === 'suspended' || (status === 'trial' && sub?.writeBlocked) ? (
            <HelpErrorAlert message="Workspace writes are blocked until billing is active." />
          ) : null}
        </Stack>
      </Paper>
      <Paper sx={{ p: 3 }}>
        <Typography variant="h6" sx={{ mb: 2 }}>
          Available plans
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
                disabled={checkout.isPending}
                onClick={() => checkout.mutate(plan.id)}
              >
                {sub?.plan?.id === plan.id ? 'Current' : 'Start checkout'}
              </Button>
            </Stack>
          ))}
          {plans.length === 0 ? (
            <Typography color="text.secondary">No plans are configured yet.</Typography>
          ) : null}
        </Stack>
      </Paper>
    </Stack>
  );
}
