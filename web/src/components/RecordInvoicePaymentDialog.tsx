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
import { getErrorMessage } from '@/api/client';
import { recordInvoicePayment } from '@/api/resources';
import { ChequePaymentFields, type ChequePaymentValues } from '@/components/ChequePaymentFields';
import { t } from '@/i18n';
import type { PaymentMode, SalesInvoice } from '@/types/domain';
import { formatMoney, toNumber } from '@/utils/money';
import { todayIso } from '@/components/billing';

type Props = {
  invoice: SalesInvoice | null;
  open: boolean;
  onClose: () => void;
  onSuccess: (invoice: SalesInvoice) => void;
};

const EMPTY_CHEQUE: ChequePaymentValues = { chequeNumber: '', chequeBankName: '', chequeDate: '' };

export function RecordInvoicePaymentDialog({ invoice, open, onClose, onSuccess }: Props) {
  const [amount, setAmount] = useState('');
  const [discount, setDiscount] = useState('');
  const [mode, setMode] = useState<PaymentMode>('CASH');
  const [paymentDate, setPaymentDate] = useState(todayIso());
  const [reference, setReference] = useState('');
  const [cheque, setCheque] = useState(EMPTY_CHEQUE);
  const [error, setError] = useState<string | null>(null);

  const due = invoice ? toNumber(invoice.balance ?? invoice.grandTotal) : 0;

  const mutation = useMutation({
    mutationFn: () => {
      if (!invoice) throw new Error('Missing invoice');
      return recordInvoicePayment(invoice.id, {
        amount: Number(amount),
        discount: discount === '' ? 0 : Number(discount),
        mode,
        paymentDate,
        reference,
        chequeNumber: cheque.chequeNumber,
        chequeBankName: cheque.chequeBankName,
        chequeDate: cheque.chequeDate || undefined,
        chequeImage: cheque.chequeImage || undefined,
      });
    },
    onSuccess: (inv) => {
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
            inputProps={{ min: 0.01, step: '0.01' }}
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
            <MenuItem value="CASH">Cash</MenuItem>
            <MenuItem value="UPI">UPI</MenuItem>
            <MenuItem value="BANK">Bank</MenuItem>
            <MenuItem value="CARD">Card</MenuItem>
            <MenuItem value="CHEQUE">Cheque</MenuItem>
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
          disabled={!invoice || !(Number(amount) > 0) || chequeIncomplete || mutation.isPending}
          onClick={() => mutation.mutate()}
        >
          {t('history.recordPayment')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
