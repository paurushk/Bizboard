import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { getCrmOnboarding } from '@/api/osPlan';
import { PageTitle } from '@/contextHelp';
import { t } from '@/i18n';

export function CrmOnboardingPage() {
  const checklist = useQuery({ queryKey: ['crm-onboarding'], queryFn: getCrmOnboarding });
  return (
    <Stack spacing={2}>
      <PageTitle>{t('nav.crmOnboarding')}</PageTitle>
      <Typography variant="body2" color="text.secondary">{t('osPlan.onboardingHelp')}</Typography>
      {(checklist.data?.steps ?? []).map((step) => (
        <Paper key={step.id} variant="outlined" sx={{ p: 1.5 }}>
          <Typography>
            {step.done ? '✓' : '○'} {step.title}
          </Typography>
        </Paper>
      ))}
    </Stack>
  );
}
