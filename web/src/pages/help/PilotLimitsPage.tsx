import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { t } from '@/i18n';

// Source of truth for the list: docs/help/LIMITATIONS.md (guard_limitations_page keeps them in step).
const KEYS = [
  'filing',
  'einvoice',
  'itcMatch',
  'cost',
  'offline',
  'books',
  'payments',
  'tally',
  'whatsapp',
  'modules',
] as const;

/** Freeze-scope limitations, shown in the product rather than only in the repo. Also public at /limits. */
export function PilotLimitsPage() {
  return (
    <Stack spacing={2} sx={{ p: { xs: 2, sm: 3 }, maxWidth: 720 }}>
      <Typography variant="h5" component="h1">
        {t('pilotLimits.title')}
      </Typography>
      {KEYS.map((key) => (
        <Typography key={key} component="h2" variant="subtitle1">
          {t(`pilotLimits.${key}`)}
        </Typography>
      ))}
    </Stack>
  );
}
