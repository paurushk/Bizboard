import Button from '@mui/material/Button';
import LinearProgress from '@mui/material/LinearProgress';
import Link from '@mui/material/Link';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { dismissOnboarding, getOnboarding, type OnboardingStep } from '@/api/onboarding';
import { t } from '@/i18n';

const LINKS: Record<OnboardingStep, string> = {
  gstin_verified: '/settings/company',
  first_item: '/inventory/products',
  first_party: '/sales/customers',
  first_invoice: '/sales/new',
  first_purchase: '/purchases/new',
  first_payment: '/sales/receipts',
  invited_user: '/settings/users',
  imported: '/settings/import',
};

/**
 * WP-GR2: the getting-started checklist on the home screen. Each step ticks itself when the
 * real action happens (the server stamps it), so nothing here can be ticked by hand. It hides
 * when every step is done or the owner dismisses it.
 */
export function OnboardingChecklistCard({ canDismiss }: { canDismiss: boolean }) {
  const qc = useQueryClient();
  const state = useQuery({ queryKey: ['onboarding'], queryFn: getOnboarding, staleTime: 60_000, retry: false });
  const dismiss = useMutation({
    mutationFn: dismissOnboarding,
    onSuccess: (value) => qc.setQueryData(['onboarding'], value),
  });
  const data = state.data;
  if (!data || !data.visible) return null;
  return (
    <Paper sx={{ p: 2, mb: 2 }}>
      <Stack spacing={1}>
        <Typography variant="h6">{t('onboardingChecklist.title')}</Typography>
        <Typography variant="body2" color="text.secondary">
          {t('onboardingChecklist.progress', { done: String(data.done), total: String(data.total) })}
        </Typography>
        <LinearProgress
          variant="determinate"
          value={data.total ? (data.done * 100) / data.total : 0}
          aria-label={t('onboardingChecklist.title')}
        />
        {data.steps.map((row) => (
          <Typography key={row.step} variant="body2">
            {row.doneAt ? '✓ ' : '○ '}
            {row.doneAt ? (
              t(`onboardingChecklist.step.${row.step}`)
            ) : (
              <Link component={RouterLink} to={LINKS[row.step]}>
                {t(`onboardingChecklist.step.${row.step}`)}
              </Link>
            )}
          </Typography>
        ))}
        {canDismiss ? (
          <Button size="small" sx={{ alignSelf: 'flex-start' }} disabled={dismiss.isPending} onClick={() => dismiss.mutate()}>
            {t('onboardingChecklist.dismiss')}
          </Button>
        ) : null}
      </Stack>
    </Paper>
  );
}
