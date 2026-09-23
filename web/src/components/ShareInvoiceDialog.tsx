import { useEffect, useState } from 'react';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import Typography from '@mui/material/Typography';
import { useMutation } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { shareInvoice } from '@/api/resources';
import { isRuntimeFlagEnabled } from '@/config/featureFlags';
import { t } from '@/i18n';
import { isAllowedShareUrl, openShareUrl } from '@/utils/safeUrl';

export type ShareChannel = 'EMAIL' | 'WHATSAPP';

export type ShareInvoiceResult = {
  status: string;
  shareLink?: string;
  mode?: 'cloud' | 'link';
  error?: string;
  whatsappSendStatus?: string;
};

export function shareSuccessMessage(res: ShareInvoiceResult, channel: ShareChannel): string {
  if (channel === 'WHATSAPP') {
    const mode = res.mode ?? (res.status === 'SENT' ? 'cloud' : 'link');
    if (mode === 'cloud' && res.status === 'SENT') return t('common.whatsappCloudSent');
    if (res.error) return res.error || t('common.whatsappFallbackWarn');
    return t('common.whatsappLinkHint');
  }
  return res.shareLink ? t('common.shareReady') : `${t('common.share')} ${res.status}`;
}

type Props = {
  open: boolean;
  invoiceId: number | null;
  defaultPhone?: string;
  defaultEmail?: string;
  onClose: () => void;
  onSuccess?: (message: string, res: ShareInvoiceResult) => void;
  onError?: (message: string) => void;
};

export function ShareInvoiceDialog({
  open,
  invoiceId,
  defaultPhone = '',
  defaultEmail = '',
  onClose,
  onSuccess,
  onError,
}: Props) {
  const [channel, setChannel] = useState<ShareChannel>('EMAIL');
  const [phone, setPhone] = useState(defaultPhone);
  const [email, setEmail] = useState(defaultEmail);
  const [shareLink, setShareLink] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setPhone(defaultPhone);
    setEmail(defaultEmail);
    setShareLink(null);
    setChannel(defaultEmail && !defaultPhone ? 'EMAIL' : defaultPhone ? 'WHATSAPP' : 'EMAIL');
  }, [open, defaultPhone, defaultEmail]);

  const mutation = useMutation({
    mutationFn: (payload: { channel: ShareChannel; recipient: string }) => {
      if (!invoiceId) throw new Error('Missing invoice');
      return shareInvoice(invoiceId, payload);
    },
    onSuccess: (res, variables) => {
      setShareLink(res.shareLink ?? null);
      const message = shareSuccessMessage(res, variables.channel);
      onSuccess?.(message, res);
      // BB-000743: cloud attempted but fell back to wa.me — never silent.
      // The dialog still reports "success" (a link was produced), but the
      // failure must stay visible, not be swallowed by a green banner.
      if (variables.channel === 'WHATSAPP' && res.error) {
        onError?.(res.error || t('common.whatsappFallbackWarn'));
      }
      const mode =
        variables.channel === 'WHATSAPP'
          ? (res.mode ?? (res.status === 'SENT' ? 'cloud' : 'link'))
          : 'link';
      if (res.shareLink && mode !== 'cloud') {
        try {
          openShareUrl(res.shareLink);
        } catch {
          onSuccess?.(t('common.shareBlocked'), res);
        }
      }
    },
    onError: (err) => onError?.(getErrorMessage(err)),
  });

  const recipient = channel === 'WHATSAPP' ? phone : email;
  const phoneOk = /^\d{10,15}$/.test(phone.replace(/\D/g, ''));
  const emailOk = /^\S+@\S+\.\S+$/.test(email);
  const recipientOk = channel === 'WHATSAPP' ? phoneOk : emailOk;

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{t('common.shareInvoice')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <ToggleButtonGroup
            exclusive
            size="small"
            value={channel}
            onChange={(_, value: ShareChannel | null) => value && setChannel(value)}
          >
            <ToggleButton value="EMAIL">{t('common.email')}</ToggleButton>
            <ToggleButton value="WHATSAPP">{t('common.whatsapp')}</ToggleButton>
          </ToggleButtonGroup>
          {channel === 'WHATSAPP' ? (
            <TextField
              label={t('common.whatsapp')}
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="9198XXXXXXXX"
              helperText={
                isRuntimeFlagEnabled('ENABLE_WHATSAPP_CLOUD')
                  ? undefined
                  : t('common.whatsappLinkHint')
              }
              error={Boolean(phone) && !phoneOk}
            />
          ) : (
            <TextField
              label={t('common.email')}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              error={Boolean(email) && !emailOk}
            />
          )}
          {shareLink && isAllowedShareUrl(shareLink) ? (
            <Typography variant="body2">
              <a href={shareLink} target="_blank" rel="noopener noreferrer">
                {shareLink}
              </a>
            </Typography>
          ) : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.close')}</Button>
        <Button
          variant="contained"
          disabled={!invoiceId || !recipientOk || mutation.isPending}
          onClick={() => mutation.mutate({ channel, recipient })}
        >
          {t('common.send')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
