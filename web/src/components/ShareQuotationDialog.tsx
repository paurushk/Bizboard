import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { revokeQuotationLink, shareQuotation } from '@/api/resources';
import { t } from '@/i18n';
import { shareOnThisDevice } from '@/utils/safeUrl';

type Props = {
  open: boolean;
  quotation: { id: number; number?: string | null } | null;
  companyName?: string;
  onClose: () => void;
  /** Called after a link is made so the caller can refresh its list (the quote may now be Sent). */
  onShared?: () => void;
};

/** A link to the quotation's PDF that works without signing in, until its validity date. */
export function ShareQuotationDialog({ open, quotation, companyName = '', onClose, onShared }: Props) {
  const [link, setLink] = useState<{ url: string; expiresAt?: string | null } | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const make = useMutation({
    mutationFn: (channel: 'link' | 'whatsapp') => shareQuotation(quotation!.id, channel),
    onSuccess: (res) => {
      setLink({ url: res.url, expiresAt: res.expiresAt });
      onShared?.();
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const revoke = useMutation({
    mutationFn: () => revokeQuotationLink(quotation!.id),
    onSuccess: () => setLink(null),
    onError: (err) => setError(getErrorMessage(err)),
  });

  const reset = () => {
    setLink(null);
    setCopied(false);
    setError(null);
  };
  const close = () => {
    reset();
    onClose();
  };

  const withLink = async (channel: 'link' | 'whatsapp') => {
    setError(null);
    setCopied(false);
    try {
      return link ?? (await make.mutateAsync(channel).then((res) => ({ url: res.url, expiresAt: res.expiresAt })));
    } catch {
      return null;
    }
  };

  const copy = async () => {
    const ready = await withLink('link');
    if (!ready) return;
    try {
      await navigator.clipboard.writeText(ready.url);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  const whatsapp = async () => {
    const ready = await withLink('whatsapp');
    if (!ready) return;
    try {
      await shareOnThisDevice({
        text: t('phase1.quotationShareMessage', {
          number: quotation?.number ?? '',
          company: companyName,
          url: ready.url,
        }),
      });
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const validUntil = link?.expiresAt ? link.expiresAt.slice(0, 10) : '';

  return (
    <Dialog open={open} onClose={close} fullWidth maxWidth="sm" aria-labelledby="share-quotation-title">
      <DialogTitle id="share-quotation-title">
        {t('phase1.quotationShareTitle')} {quotation?.number ?? ''}
      </DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {error ? <Alert severity="error">{error}</Alert> : null}
          {link ? (
            <>
              <TextField
                size="small"
                fullWidth
                label={t('common.copyLink')}
                value={link.url}
                InputProps={{ readOnly: true }}
                onFocus={(e) => e.target.select()}
              />
              {validUntil ? (
                <Typography variant="body2" color="text.secondary">
                  {t('phase1.quotationShareHelp', { date: validUntil })}
                </Typography>
              ) : null}
              {copied ? <Alert severity="success">{t('phase1.quotationLinkCopied')}</Alert> : null}
            </>
          ) : null}
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <Button variant="contained" disabled={make.isPending} onClick={() => void copy()}>
              {t('common.copyLink')}
            </Button>
            <Button variant="outlined" disabled={make.isPending} onClick={() => void whatsapp()}>
              {t('phase1.quotationShareWhatsapp')}
            </Button>
            {link ? (
              <Button color="warning" disabled={revoke.isPending} onClick={() => revoke.mutate()}>
                {t('phase1.quotationRevokeLink')}
              </Button>
            ) : null}
          </Stack>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={close}>{t('common.close')}</Button>
      </DialogActions>
    </Dialog>
  );
}
