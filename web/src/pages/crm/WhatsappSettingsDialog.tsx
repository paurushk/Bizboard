import { useState } from 'react';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { issueWhatsappWebhookToken, saveWhatsappAppSecret, whatsappWebhookUrl } from '@/api/crm';
import { LoadingState } from '@/components/PageState';
import { t } from '@/i18n';

/** Owner-only: the values Meta asks for, and this company's own app secret. */
export function WhatsappSettingsDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const [secret, setSecret] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const settings = useQuery({
    queryKey: ['whatsapp-settings'],
    queryFn: () => issueWhatsappWebhookToken(false),
    enabled: open,
  });
  const save = useMutation({
    mutationFn: () => saveWhatsappAppSecret(secret.trim()),
    onSuccess: () => {
      setSecret('');
      setError('');
      setMessage(t('osPlan.whatsappSecretSaved'));
      void qc.invalidateQueries({ queryKey: ['whatsapp-settings'] });
    },
    onError: (err) => {
      setMessage('');
      setError(getErrorMessage(err));
    },
  });
  const data = settings.data;
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{t('osPlan.whatsappSettings')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {settings.isLoading ? <LoadingState /> : null}
          {settings.isError ? <Typography color="error">{getErrorMessage(settings.error)}</Typography> : null}
          {data ? (
            <>
              <TextField
                label={t('osPlan.whatsappUrl')}
                value={whatsappWebhookUrl(data.token)}
                InputProps={{ readOnly: true }}
              />
              <TextField
                label={t('osPlan.whatsappVerifyToken')}
                value={data.verifyToken}
                InputProps={{ readOnly: true }}
              />
              <Typography variant="body2" color="text.secondary">
                {data.secretConfigured ? t('osPlan.whatsappSecretSet') : t('osPlan.whatsappSecretNotSet')}
              </Typography>
              <TextField
                label={t('osPlan.whatsappSecret')}
                type="password"
                autoComplete="off"
                value={secret}
                onChange={(e) => setSecret(e.target.value)}
                helperText={t('osPlan.whatsappSecretHelp')}
              />
            </>
          ) : null}
          {message ? <Typography variant="body2">{message}</Typography> : null}
          {error ? <Typography color="error">{error}</Typography> : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" disabled={!secret.trim() || save.isPending} onClick={() => save.mutate()}>
          {t('common.save')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
