import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { Link as RouterLink } from 'react-router-dom';
import { PageTitle } from '@/contextHelp';
import { t } from '@/i18n';

/** In-page state when a module screen loads but cannot finish its main action. The nav item stays. */
export function ModuleNotReady({
  message,
  onRetry,
}: {
  message?: string;
  onRetry?: () => void;
}) {
  return (
    <Stack spacing={2}>
      <PageTitle>{t('moduleNotReady.title')}</PageTitle>
      <Typography color="text.secondary" role="status">{message ?? t('moduleNotReady.body')}</Typography>
      <Typography>{t('cog.featureOffSentence')}</Typography>
      <Button component={RouterLink} to="/settings" variant="outlined" sx={{ alignSelf: 'flex-start' }}>
        {t('cog.openSettings')}
      </Button>
      {onRetry ? (
        <Button variant="outlined" onClick={onRetry} sx={{ alignSelf: 'flex-start' }}>
          {t('common.retry')}
        </Button>
      ) : null}
    </Stack>
  );
}
