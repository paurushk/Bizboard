import { useEffect, useRef, useState } from 'react';
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
import { downloadInvoicePdf, shareInvoice } from '@/api/resources';
import { t } from '@/i18n';
import { isAllowedShareUrl, isPhoneDevice, openShareUrl, shareOnThisDevice } from '@/utils/safeUrl';

export type ShareChannel = 'EMAIL' | 'WHATSAPP';

export type ShareInvoiceResult = {
  status: string;
  shareLink?: string;
  mode?: 'cloud' | 'link' | 'device';
  error?: string;
  whatsappSendStatus?: string;
  text?: string;
  documentUrl?: string;
};

function shareSuccessMessage(res: ShareInvoiceResult, channel: ShareChannel): string {
  if (channel === 'WHATSAPP') {
    if (res.mode === 'device') return t('common.whatsappLinkHint');
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
  initialChannel?: ShareChannel;
  /** Company Cloud WhatsApp. Hidden unless the caller turns this on. */
  allowBusinessWhatsApp?: boolean;
  onClose: () => void;
  onSuccess?: (message: string, res: ShareInvoiceResult) => void;
  onError?: (message: string) => void;
};

// The server mints the public link and puts it in the text, so this is one request.
function deviceShareText(res: ShareInvoiceResult): string {
  return (res.text || '').trim() || t('common.whatsappShare');
}

export function ShareInvoiceDialog({
  open,
  invoiceId,
  defaultPhone = '',
  defaultEmail = '',
  initialChannel,
  allowBusinessWhatsApp = false,
  onClose,
  onSuccess,
  onError,
}: Props) {
  const [channel, setChannel] = useState<ShareChannel>('EMAIL');
  const [phone, setPhone] = useState(defaultPhone);
  const [email, setEmail] = useState(defaultEmail);
  const [shareLink, setShareLink] = useState<string | null>(null);
  const [devicePending, setDevicePending] = useState(false);
  const pdfFileRef = useRef<File | null>(null);

  const resetKey = open ? `${defaultPhone}|${defaultEmail}|${initialChannel ?? ''}` : null;
  const [seenResetKey, setSeenResetKey] = useState<string | null>(null);
  if (seenResetKey !== resetKey) {
    setSeenResetKey(resetKey);
    if (resetKey !== null) {
      setPhone(defaultPhone);
      setEmail(defaultEmail);
      setShareLink(null);
      setChannel(
        initialChannel
          ?? (defaultEmail && !defaultPhone ? 'EMAIL' : defaultPhone ? 'WHATSAPP' : 'EMAIL'),
      );
    }
  }

  useEffect(() => {
    if (!open || !invoiceId || channel !== 'WHATSAPP' || !isPhoneDevice()) {
      pdfFileRef.current = null;
      return;
    }
    let cancelled = false;
    void downloadInvoicePdf(invoiceId)
      .then((blob) => {
        if (cancelled) return;
        pdfFileRef.current = new File([blob], `invoice-${invoiceId}.pdf`, { type: 'application/pdf' });
      })
      .catch(() => {
        if (!cancelled) pdfFileRef.current = null;
      });
    return () => {
      cancelled = true;
    };
  }, [open, invoiceId, channel]);

  const mutation = useMutation({
    mutationFn: (payload: { channel: ShareChannel; recipient: string; sendFromBusinessNumber?: boolean }) => {
      if (!invoiceId) throw new Error('Missing invoice');
      return shareInvoice(invoiceId, payload);
    },
    onSuccess: (res, variables) => {
      setShareLink(res.shareLink ?? null);
      const message = shareSuccessMessage(res, variables.channel);
      onSuccess?.(message, res);
      if (variables.channel === 'WHATSAPP' && res.error) {
        onError?.(res.error || t('common.whatsappFallbackWarn'));
      }
      const mode =
        variables.channel === 'WHATSAPP'
          ? (res.mode ?? (res.status === 'SENT' ? 'cloud' : 'link'))
          : 'link';
      if (res.shareLink && mode !== 'cloud' && mode !== 'device') {
        try {
          openShareUrl(res.shareLink);
        } catch {
          onSuccess?.(t('common.shareBlocked'), res);
        }
      }
    },
    onError: (err) => onError?.(getErrorMessage(err)),
  });

  const phoneOk = /^\d{10,15}$/.test(phone.replace(/\D/g, ''));
  const emailOk = /^\S+@\S+\.\S+$/.test(email);

  const shareOnDevice = async () => {
    if (!invoiceId) return;
    setDevicePending(true);
    try {
      const res = await shareInvoice(invoiceId, { channel: 'WHATSAPP', recipient: '' });
      const text = deviceShareText(res);
      await shareOnThisDevice({ text, file: pdfFileRef.current });
      onSuccess?.(shareSuccessMessage({ ...res, mode: 'device' }, 'WHATSAPP'), { ...res, mode: 'device', text });
    } catch (err) {
      const name = err && typeof err === 'object' ? (err as { name?: string }).name : '';
      if (name !== 'AbortError') onError?.(getErrorMessage(err));
    } finally {
      setDevicePending(false);
    }
  };

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
            <Stack spacing={1.5}>
              <Typography variant="body2" color="text.secondary">
                {t('common.whatsappLinkHint')}
              </Typography>
              {allowBusinessWhatsApp ? (
                <TextField
                  label={t('common.whatsapp')}
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="9198XXXXXXXX"
                  error={Boolean(phone) && !phoneOk}
                />
              ) : null}
            </Stack>
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
        {channel === 'WHATSAPP' && allowBusinessWhatsApp ? (
          <Button
            variant="outlined"
            disabled={!invoiceId || !phoneOk || mutation.isPending || devicePending}
            onClick={() =>
              mutation.mutate({
                channel: 'WHATSAPP',
                recipient: phone.replace(/\D/g, ''),
                sendFromBusinessNumber: true,
              })
            }
          >
            {t('common.whatsappSendFromBusiness')}
          </Button>
        ) : null}
        <Button
          variant="contained"
          disabled={!invoiceId || (channel === 'EMAIL' && !emailOk) || mutation.isPending || devicePending}
          onClick={() => {
            if (channel === 'WHATSAPP') {
              void shareOnDevice();
              return;
            }
            mutation.mutate({ channel, recipient: email });
          }}
        >
          {channel === 'WHATSAPP' ? t('common.whatsappShare') : t('common.send')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
