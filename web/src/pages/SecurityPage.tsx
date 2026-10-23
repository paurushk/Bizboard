import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { SignedInDevicesPanel } from '@/components/SignedInDevicesPanel';
import { TwoStepVerificationPanel } from '@/components/TwoStepVerificationPanel';
import { t } from '@/i18n';

/**
 * WP-ID3: every signed-in user's own security page — two-step verification and the devices signed
 * in to their account (the new-device email points here). Not owner-only: these are about the
 * person, not the company.
 */
export function SecurityPage() {
  return (
    <Stack spacing={2}>
      <Typography variant="h5" component="h1">
        {t('security.title')}
      </Typography>
      <Typography variant="body2" color="text.secondary">
        {t('security.help')}
      </Typography>
      <TwoStepVerificationPanel />
      <SignedInDevicesPanel />
    </Stack>
  );
}
