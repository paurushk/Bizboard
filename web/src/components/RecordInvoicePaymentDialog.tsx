import { useState } from 'react';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation } from '@tanstack/react-query';
import { getErrorMessage, newIdempotencyKey } from '@/api/client';
import { recordInvoicePayment } from '@/api/resources';
import { ChequePaymentFields, type ChequePaymentValues } from '@/components/ChequePaymentFields';
import { t } from '@/i18n';
import type { PaymentMode, SalesInvoice } from '@/types/domain';
import { formatMoney, toNumber } from '@/utils/money';
import { todayIso } from '@/components/billing/lineHelpers';

type Props = {
  invoice: SalesInvoice | null;
  open: boolean;
  onClose: () => void;
  onSuccess: (invoice: SalesInvoice) => void;
};

/** Short stable hash (FNV-1a) of what is being paid, so the key follows the request body. */
function bodyFingerprint(invoiceId: number | string, body: unknown): string {
  const text = `${invoiceId}:${JSON.stringify(body)}`;
  let hash = 0x811c9dc5;
  for (let i = 0; i < text.length; i += 1) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash.toString(16);
}

const EMPTY_CHEQUE: ChequePaymentValues = { chequeNumber: '', chequeBankName: '', chequeDate: '' };

export function RecordInvoicePaymentDialog({ invoice, open, onClose, onSuccess }: Props) {
  const [amount, setAmount] = useState('');
  const [discount, setDiscount] = useState('');
  const [mode, setMode] = useState<PaymentMode>('CASH');
  const [paymentDate, setPaymentDate] = useState(todayIso());
  const [reference, setReference] = useState('');
  const [cheque, setCheque] = useState(EMPTY_CHEQUE);
  const [error, setError] = useState<string | null>(null);
  // One key per payment being entered: a double click or a retry after a lost response
  // replays the first receipt instead of posting a second one.
  const [idempotencyKey, setIdempotencyKey] = useState(() => newIdempotencyKey());

  const due = invoice ? toNumber(invoice.balance ?? invoice.grandTotal) : 0;

  const mutation = useMutation({
    mutationFn: () => {
      if (!invoice) throw new Error('Missing invoice');
      const body = {
        amount: Number(amount),
        discount: discount === '' ? 0 : Number(discount),
        mode,
        paymentDate,
        reference,
        chequeNumber: cheque.chequeNumber,
        chequeBankName: cheque.chequeBankName,
        chequeDate: cheque.chequeDate || undefined,
        chequeImage: cheque.chequeImage || undefined,
      };
      // The server refuses a reused key with a different body. A retry of the same payment keeps
      // its key (so a lost response replays instead of posting twice); a corrected amount, or the
      // dialog reopened for another invoice, gets a new one.
      return recordInvoicePayment(invoice.id, body, {
        idempotencyKey: `${idempotencyKey}-${bodyFingerprint(invoice.id, body)}`,
      });
    },
    onSuccess: (inv) => {
      setIdempotencyKey(newIdempotencyKey());
      onSuccess(inv);
      setAmount('');
      setDiscount('');
      setReference('');
      setCheque(EMPTY_CHEQUE);
      setError(null);
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const chequeIncomplete =
    mode === 'CHEQUE' && (!cheque.chequeNumber.trim() || !cheque.chequeBankName.trim());
  const exceedsBalance = Number(amount) > due + 0.009;

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullWidth
      maxWidth="sm"
      TransitionProps={{
        onEnter: () => {
          setAmount(due > 0 ? String(due) : '');
          setPaymentDate(todayIso());
          setError(null);
        },
      }}
    >
      <DialogTitle>{t('history.recordPayment')}</DialogTitle>
      <DialogContent>
        <Stack spacing={1.5} sx={{ mt: 1 }}>
          {invoice ? (
            <Typography variant="body2" color="text.secondary">
              {invoice.number ?? `#${invoice.id}`} · {t('reports.dueBalance')}: {formatMoney(due)}
            </Typography>
          ) : null}
          {error ? (
            <Typography color="error" variant="body2">
              {error}
            </Typography>
          ) : null}
          <TextField
            size="small"
            type="number"
            label={t('billing.amountReceived')}
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            error={exceedsBalance}
            helperText={exceedsBalance ? t('billing.paymentExceedsBalance') : undefined}
            inputProps={{ min: 0.01, step: '0.01', max: due }}
          />
          <TextField
            size="small"
            type="number"
            label={t('history.settlementDiscount')}
            helperText={t('history.settlementDiscountHelp')}
            value={discount}
            onChange={(e) => setDiscount(e.target.value)}
            inputProps={{ min: 0, step: '0.01' }}
          />
          <TextField
            select
            size="small"
            label={t('billing.paymentMode')}
            value={mode}
            onChange={(e) => setMode(e.target.value as PaymentMode)}
          >
            <MenuItem value="CASH">{t('sweep2.cash')}</MenuItem>
            <MenuItem value="UPI">UPI</MenuItem>
            <MenuItem value="BANK">{t('sweep2.bank')}</MenuItem>
            <MenuItem value="CARD">{t('sweep2.card')}</MenuItem>
            <MenuItem value="CHEQUE">{t('sweep2.cheque')}</MenuItem>
          </TextField>
          <TextField
            size="small"
            type="date"
            label={t('common.date')}
            InputLabelProps={{ shrink: true }}
            value={paymentDate}
            onChange={(e) => setPaymentDate(e.target.value)}
          />
          {mode === 'UPI' || mode === 'BANK' ? (
            <TextField
              size="small"
              label={t('billing.reference')}
              value={reference}
              onChange={(e) => setReference(e.target.value)}
            />
          ) : null}
          {mode === 'CHEQUE' ? <ChequePaymentFields value={cheque} onChange={setCheque} /> : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button
          variant="contained"
          disabled={!invoice || !(Number(amount) > 0) || exceedsBalance || chequeIncomplete || mutation.isPending}
          onClick={() => mutation.mutate()}
        >
          {t('history.recordPayment')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
