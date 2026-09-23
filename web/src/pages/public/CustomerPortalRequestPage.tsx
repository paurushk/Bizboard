import { useState } from 'react';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation } from '@tanstack/react-query';
import { requestCustomerPortalLink } from '@/api/resources';
import { getErrorMessage } from '@/api/client';
import { t } from '@/i18n';
import { formatPortalDebugHint } from './portalDebugHint';

export function CustomerPortalRequestPage() {
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [sent, setSent] = useState(false);
  const [debugHint, setDebugHint] = useState<string | null>(null);
  const [error, setError] = useState('');
  const request = useMutation({
    mutationFn: () => requestCustomerPortalLink({
      email: email.trim() || undefined,
      phone: phone.trim() || undefined,
    }),
    onSuccess: (data) => {
      setError('');
      setSent(true);
      setDebugHint(formatPortalDebugHint(data));
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  return (
    <Stack minHeight="100vh" p={2} alignItems="center" justifyContent="center" sx={{ bgcolor: 'grey.50' }}>
      <Card sx={{ maxWidth: 480, width: '100%' }}>
        <CardContent>
          <Stack spacing={2}>
            <Typography variant="h5" component="h1">{t('portal.requestTitle')}</Typography>
            {sent ? <Typography>{t('portal.sent')}</Typography> : null}
            {debugHint ? <Typography data-testid="portal-debug-hint">{debugHint}</Typography> : null}
            {error ? <Typography color="error">{error}</Typography> : null}
            <TextField label={t('portal.email')} value={email} onChange={(e) => setEmail(e.target.value)} type="email" />
            <TextField label={t('portal.phone')} value={phone} onChange={(e) => setPhone(e.target.value)} />
            <Button
              variant="contained"
              disabled={request.isPending || (!email.trim() && !phone.trim())}
              onClick={() => request.mutate()}
            >
              {t('portal.send')}
            </Button>
          </Stack>
        </CardContent>
      </Card>
    </Stack>
  );
}
