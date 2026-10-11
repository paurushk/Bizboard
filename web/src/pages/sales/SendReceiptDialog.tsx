import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import FormControlLabel from '@mui/material/FormControlLabel';
import Radio from '@mui/material/Radio';
import RadioGroup from '@mui/material/RadioGroup';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { sendReceipt } from '@/api/resources';
import { t } from '@/i18n';
import { ActionDialog } from '@/pages/sales/ActionDialog';
import { openDeviceShare } from '@/pages/sales/receiptShare';
import type { CustomerReceipt } from '@/types/domain';

type Channel = 'whatsapp' | 'email' | 'device';

function Form({ receipt, onClose, onDone }: { receipt: CustomerReceipt; onClose: () => void; onDone: (message: string) => void }) {
  const [channel, setChannel] = useState<Channel>('whatsapp');
  const [recipient, setRecipient] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [errorSource, setErrorSource] = useState<unknown>(null);
  const [link, setLink] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      sendReceipt(receipt.id, {
        channel: channel === 'email' ? 'email' : 'whatsapp',
        // An empty recipient with WhatsApp is the device share; omitting it uses the customer's number.
        ...(channel === 'device' ? { recipient: '' } : recipient.trim() ? { recipient: recipient.trim() } : {}),
      }),
    onSuccess: (result) => {
      if (result.mode === 'device') {
        openDeviceShare(result);
        onDone(t('receipts.sendOpened'));
        return;
      }
      if (result.mode === 'link' && result.shareLink) {
        // Not sent from the business number: the person sends this link themselves.
        setLink(result.shareLink);
        return;
      }
      onDone(t('receipts.sendSent'));
    },
    onError: (err) => {
      setError(getErrorMessage(err));
      setErrorSource(err);
    },
  });

  return (
    <ActionDialog
      open
      title={t('receipts.sendTitle')}
      onClose={onClose}
      onConfirm={link ? undefined : () => mutation.mutate()}
      confirmLabel={t('receipts.actionSend')}
      pending={mutation.isPending}
      error={error}
      errorSource={errorSource}
    >
      <Typography variant="body2" color="text.secondary">
        {receipt.number ?? receipt.id} · {receipt.customerName}
      </Typography>
      {link ? (
        <Alert
          severity="success"
          action={
            <Button color="inherit" size="small" component="a" href={link} target="_blank" rel="noopener noreferrer">
              {t('receipts.sendLink')}
            </Button>
          }
        >
          {t('receipts.sendLink')}
        </Alert>
      ) : (
        <>
          <RadioGroup value={channel} onChange={(e) => setChannel(e.target.value as Channel)}>
            <FormControlLabel value="whatsapp" control={<Radio />} label={t('receipts.sendWhatsapp')} />
            <FormControlLabel value="device" control={<Radio />} label={t('receipts.sendDeviceHint')} />
            <FormControlLabel value="email" control={<Radio />} label={t('receipts.sendEmail')} />
          </RadioGroup>
          {channel !== 'device' ? (
            <TextField
              size="small"
              label={t('receipts.sendRecipient')}
              value={recipient}
              onChange={(e) => setRecipient(e.target.value)}
            />
          ) : null}
          {channel === 'whatsapp' ? (
            <Typography variant="caption" color="text.secondary">
              {t('receipts.sendConsent')}
            </Typography>
          ) : null}
        </>
      )}
    </ActionDialog>
  );
}

/** Send the receipt voucher to the customer. The send is logged on the receipt. */
export function SendReceiptDialog(props: {
  receipt: CustomerReceipt | null;
  onClose: () => void;
  onDone: (message: string) => void;
}) {
  return props.receipt ? (
    <Form key={props.receipt.id} receipt={props.receipt} onClose={props.onClose} onDone={props.onDone} />
  ) : null;
}
