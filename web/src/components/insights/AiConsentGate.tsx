import Alert from '@mui/material/Alert';
import Stack from '@mui/material/Stack';
import { useAuth } from '@/auth/AuthContext';
import { PageHeader } from '@/components/insights/PageHeader';
import { t } from '@/i18n';

/** Company consent stays off for the UX audit. Screens render; no provider call is made. */
export function useAiConsentOn(): boolean {
  const { user } = useAuth();
  return user?.company?.aiFeaturesEnabled === true;
}

export function AiConsentOffScreen({ title }: { title: string }) {
  return (
    <Stack spacing={2}>
      <PageHeader title={title} />
      <Alert severity="info">{t('insights.consentOff')}</Alert>
    </Stack>
  );
}
