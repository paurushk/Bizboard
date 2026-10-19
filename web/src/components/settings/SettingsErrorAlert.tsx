import Typography from '@mui/material/Typography';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { t } from '@/i18n';
import { settingsErrorAdvice } from '@/utils/settingsErrors';

/**
 * SET-14: the server's message, then why it happened and what to do, for any failed save on a
 * Settings screen. Drop-in for `HelpErrorAlert` where `error` is the thrown error.
 */
export function SettingsErrorAlert({ error, onClose }: { error: unknown; onClose?: () => void }) {
  if (error == null) return null;
  const advice = settingsErrorAdvice(error);
  return (
    <HelpErrorAlert error={error} onClose={onClose}>
      {advice ? (
        <Typography variant="body2" component="div" sx={{ mt: 0.5 }}>
          <strong>{t('settingsErrors.why')}:</strong> {advice.cause}
          <br />
          <strong>{t('settingsErrors.fix')}:</strong> {advice.fix}
        </Typography>
      ) : null}
    </HelpErrorAlert>
  );
}
