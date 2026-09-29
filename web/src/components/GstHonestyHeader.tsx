import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import { t } from '@/i18n';

/** Shared honesty banner on every GSTR page: worksheet sentence plus the portal link. */
export function GstHonestyHeader() {
  return (
    <Stack spacing={1}>
      <Alert severity="info">{t('gstHonesty.offlineAid')}</Alert>
      <Button
        variant="outlined"
        size="small"
        component="a"
        href="https://www.gst.gov.in/"
        target="_blank"
        rel="noopener noreferrer"
        sx={{ alignSelf: 'flex-start' }}
      >
        {t('gstHonesty.filePortalLink')}
      </Button>
    </Stack>
  );
}
