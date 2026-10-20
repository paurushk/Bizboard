import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import { Link as RouterLink } from 'react-router-dom';
import { useAuth } from '@/auth/AuthContext';
import { PageHeader } from '@/components/insights/PageHeader';
import { t } from '@/i18n';

/** Company consent stays off for the UX audit. Screens render; no provider call is made. */
export function useAiConsentOn(): boolean {
  const { user } = useAuth();
  return user?.company?.aiFeaturesEnabled === true;
}

export function AiConsentOffScreen({ title }: { title: string }) {
  const { user } = useAuth();
  return (
    <Stack spacing={2}>
      <PageHeader title={title} />
      <Alert
        severity="info"
        action={
          user?.role === 'OWNER' ? (
            <Button color="inherit" size="small" component={RouterLink} to="/settings/ai">
              {t('insights.openAiSettings')}
            </Button>
          ) : undefined
        }
      >
        {t('insights.consentOff')}
      </Alert>
    </Stack>
  );
}
