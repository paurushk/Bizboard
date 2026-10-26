import { Alert, AlertTitle, Button, Stack } from '@mui/material';
import { Link as RouterLink } from 'react-router-dom';
import { t } from '@/i18n';

/** BB-100: shown instead of a switched-off page opened from a bookmark or a link. */
export function FeatureOffNotice() {
  return (
    <Stack spacing={2} sx={{ maxWidth: 640 }}>
      <Alert severity="info">
        <AlertTitle>{t('featureOff.title')}</AlertTitle>
        {t('featureOff.body')}
      </Alert>
      <div>
        <Button variant="contained" component={RouterLink} to="/">
          {t('featureOff.home')}
        </Button>
      </div>
    </Stack>
  );
}
