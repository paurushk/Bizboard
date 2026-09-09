import Alert from '@mui/material/Alert';
import { t } from '@/i18n';

/** Pilot honesty banner — one short limitation, never a feature claim. */
export function HonestyBanner({
  messageKey,
  vars,
}: {
  messageKey: string;
  vars?: Record<string, string | number>;
}) {
  return (
    <Alert severity="info" sx={{ mb: 2 }}>
      {t(messageKey, vars)}
    </Alert>
  );
}
