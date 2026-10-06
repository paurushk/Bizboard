import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { getCrmOnboarding } from '@/api/osPlan';
import { PageTitle } from '@/contextHelp';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { getErrorMessage } from '@/api/client';
import { t } from '@/i18n';

const STEP_HREF: Record<string, string> = {
  company: '/settings/company',
  booker: '/settings/users',
  lead: '/crm/leads',
  stage: '/crm/pipeline',
};

function onboardingHref(stepId: string) {
  return STEP_HREF[stepId] ?? '/crm/leads';
}

export function CrmOnboardingPage() {
  const checklist = useQuery({ queryKey: ['crm-onboarding'], queryFn: getCrmOnboarding });
  return (
    <Stack spacing={2}>
      <PageTitle>{t('nav.crmOnboarding')}</PageTitle>
      <Typography variant="body2" color="text.secondary">{t('osPlan.onboardingHelp')}</Typography>
      {checklist.isLoading ? <LoadingState /> : null}
      {checklist.isError ? (
        <ErrorState message={getErrorMessage(checklist.error)} error={checklist.error} onRetry={() => void checklist.refetch()} />
      ) : null}
      {checklist.data && (checklist.data.steps ?? []).length === 0 ? (
        <EmptyState description={t('osPlan.onboardingEmpty')} />
      ) : null}
      {(checklist.data?.steps ?? []).map((step) => (
        <Paper key={step.id} variant="outlined" sx={{ p: 1.5 }}>
          <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
            <Typography>
              {step.done ? '✓' : '○'} {step.title}
            </Typography>
            <Button size="small" component={RouterLink} to={onboardingHref(step.id)}>{t('common.next')}</Button>
          </Stack>
        </Paper>
      ))}
    </Stack>
  );
}
