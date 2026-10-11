import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Chip from '@mui/material/Chip';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { getErrorMessage } from '@/api/client';
import { sendReceipt } from '@/api/resources';
import { t } from '@/i18n';
import { ActionDialog } from '@/pages/sales/ActionDialog';
import type { CustomerReceipt } from '@/types/domain';

type Outcome = { id: number; ok: boolean; message: string };

/**
 * Send the voucher of every selected receipt to its customer, one after another. A customer with
 * no contact for the chosen channel fails on its own row and the rest still go.
 */
export function BulkSendDialog({ receipts, onClose }: { receipts: CustomerReceipt[]; onClose: () => void }) {
  const [channel, setChannel] = useState<'whatsapp' | 'email'>('whatsapp');
  const [running, setRunning] = useState(false);
  const [outcomes, setOutcomes] = useState<Outcome[] | null>(null);

  const run = async () => {
    setRunning(true);
    const rows: Outcome[] = [];
    for (const receipt of receipts) {
      try {
        await sendReceipt(receipt.id, { channel });
        rows.push({ id: receipt.id, ok: true, message: '' });
      } catch (err) {
        rows.push({ id: receipt.id, ok: false, message: getErrorMessage(err) });
      }
      setOutcomes([...rows]);
    }
    setRunning(false);
  };

  const sent = (outcomes ?? []).filter((row) => row.ok).length;
  const byId = new Map((outcomes ?? []).map((row) => [row.id, row]));

  return (
    <ActionDialog
      open
      title={t('receipts.bulkSend')}
      onClose={onClose}
      onConfirm={outcomes && !running ? undefined : () => void run()}
      confirmLabel={t('receipts.actionSend')}
      pending={running}
      maxWidth="sm"
    >
      <TextField
        select
        size="small"
        label={t('receipts.sendRecipient')}
        value={channel}
        onChange={(e) => setChannel(e.target.value as 'whatsapp' | 'email')}
        disabled={running || outcomes != null}
      >
        <MenuItem value="whatsapp">{t('receipts.sendWhatsapp')}</MenuItem>
        <MenuItem value="email">{t('receipts.sendEmail')}</MenuItem>
      </TextField>
      {outcomes && !running ? (
        <Alert severity={sent === receipts.length ? 'success' : 'warning'}>
          {t('receipts.bulkSendDone', { sent, total: receipts.length })}
        </Alert>
      ) : null}
      <Stack spacing={0.75}>
        {receipts.map((receipt) => {
          const outcome = byId.get(receipt.id);
          return (
            <Stack key={receipt.id} direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
              <Typography variant="body2">
                {receipt.number ?? receipt.id} · {receipt.customerName}
                {outcome && !outcome.ok ? (
                  <Typography component="span" variant="caption" color="error" sx={{ display: 'block' }}>
                    {outcome.message}
                  </Typography>
                ) : null}
              </Typography>
              {outcome ? (
                <Chip
                  size="small"
                  variant="outlined"
                  color={outcome.ok ? 'success' : 'error'}
                  label={outcome.ok ? t('receipts.sendSent') : t('receipts.bulkFailed')}
                />
              ) : null}
            </Stack>
          );
        })}
      </Stack>
    </ActionDialog>
  );
}
