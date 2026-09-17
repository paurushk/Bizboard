import Alert from '@mui/material/Alert';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { PageTitle } from '@/contextHelp';
import { t } from '@/i18n';

/** Honesty gate: partner AA ingest APIs exist; this app has no consent UI. */
export function AccountAggregatorPage() {
  return (
    <Stack spacing={2}>
      <PageTitle>{t('nav.accountAggregator')}</PageTitle>
      <Alert severity="warning">
        <Typography fontWeight={600}>{t('aaHonesty.title')}</Typography>
        <Typography variant="body2">{t('aaHonesty.body')}</Typography>
      </Alert>
    </Stack>
  );
}
