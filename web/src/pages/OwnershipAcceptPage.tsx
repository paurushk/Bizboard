import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useMutation } from '@tanstack/react-query';
import { Link as RouterLink, useSearchParams } from 'react-router-dom';
import { acceptOwnershipTransfer } from '@/api/ownership';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { t } from '@/i18n';

/** WP-ID1: the member opens the emailed link (signed in) and accepts ownership. */
export function OwnershipAcceptPage() {
  const [params] = useSearchParams();
  const token = params.get('token') ?? '';
  const accept = useMutation({ mutationFn: () => acceptOwnershipTransfer(token) });

  return (
    <Stack spacing={2} sx={{ p: { xs: 2, sm: 3 }, maxWidth: 560 }}>
      <Typography variant="h5" component="h1">
        {t('ownership.acceptTitle')}
      </Typography>
      <Typography>{t('ownership.acceptHelp')}</Typography>
      {!token ? <Alert severity="error">{t('ownership.noToken')}</Alert> : null}
      {accept.isError ? <HelpErrorAlert error={accept.error} /> : null}
      {accept.isSuccess ? (
        <Alert severity="success">
          {t('ownership.accepted')}{' '}
          <Button component={RouterLink} to="/settings/users" size="small">
            {t('ownership.goToUsers')}
          </Button>
        </Alert>
      ) : (
        <Button
          variant="contained"
          sx={{ alignSelf: 'flex-start' }}
          disabled={!token || accept.isPending}
          onClick={() => accept.mutate()}
        >
          {t('ownership.accept')}
        </Button>
      )}
    </Stack>
  );
}
