import { useState } from 'react';
import Checkbox from '@mui/material/Checkbox';
import FormControlLabel from '@mui/material/FormControlLabel';
import MenuItem from '@mui/material/MenuItem';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery } from '@tanstack/react-query';
import { getErrorMessage, userGestureIdempotencyKey } from '@/api/client';
import { listBankAccounts, refundAdvance } from '@/api/resources';
import { todayIso } from '@/components/billing';
import { t } from '@/i18n';
import { ActionDialog } from '@/pages/sales/ActionDialog';
import { defaultBankFor } from '@/pages/sales/receiptBank';
import { MAX_VOID_REASON_LENGTH, MIN_VOID_REASON_LENGTH } from '@/pages/sales/receiptStatus';
import type { CustomerReceipt } from '@/types/domain';
import { formatMoney, toNumber } from '@/utils/money';

type Mode = 'CASH' | 'UPI' | 'BANK';

function Form({
  receipt,
  onClose,
  onDone,
}: {
  receipt: CustomerReceipt;
  onClose: () => void;
  onDone: () => void;
}) {
  const max = toNumber(receipt.allocatable ?? receipt.unallocated);
  const [amount, setAmount] = useState(String(max));
  const [mode, setMode] = useState<Mode>('CASH');
  const [reason, setReason] = useState('');
  const [bank, setBank] = useState('');
  const [fromTill, setFromTill] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorSource, setErrorSource] = useState<unknown>(null);
  const banks = useQuery({ queryKey: ['bank-accounts'], queryFn: listBankAccounts });
  const choices = (banks.data ?? []).filter((a) => a.isActive !== false && a.accountType !== 'CASH_BOX');
  const effectiveBank = bank || (mode !== 'CASH' ? String(defaultBankFor(banks.data ?? [])?.id ?? '') : '');

  const trimmed = reason.trim().replace(/\s+/g, ' ');
  const value = Number(amount);
  const invalid =
    !(value > 0) ||
    value > max + 0.001 ||
    trimmed.length < MIN_VOID_REASON_LENGTH ||
    (mode !== 'CASH' && !effectiveBank);

  const mutation = useMutation({
    mutationFn: () =>
      refundAdvance(
        receipt.id,
        {
          amount: value,
          mode,
          reason: trimmed,
          refundDate: todayIso(),
          bankAccount: mode !== 'CASH' && effectiveBank ? Number(effectiveBank) : undefined,
          paidFromTill: mode === 'CASH' ? fromTill : undefined,
        },
        { idempotencyKey: userGestureIdempotencyKey() },
      ),
    onSuccess: onDone,
    onError: (err) => {
      setError(getErrorMessage(err));
      setErrorSource(err);
    },
  });

  return (
    <ActionDialog
      open
      title={t('receipts.refundTitle')}
      onClose={onClose}
      onConfirm={() => mutation.mutate()}
      confirmLabel={t('receipts.actionRefund')}
      confirmDisabled={invalid}
      pending={mutation.isPending}
      error={error}
      errorSource={errorSource}
    >
      <Typography variant="body2" color="text.secondary">
        {receipt.number ?? receipt.id} · {receipt.customerName}
      </Typography>
      <Typography variant="body2">{t('receipts.refundIntro')}</Typography>
      {max <= 0 ? <Typography color="warning.main">{t('receipts.refundNotAvailable')}</Typography> : null}
      <TextField
        type="number"
        label={t('receipts.refundAmount')}
        value={amount}
        onChange={(e) => setAmount(e.target.value)}
        error={value > max + 0.001}
        helperText={t('receipts.refundMax', { max: formatMoney(max) })}
        slotProps={{ htmlInput: { min: 0, max, step: '0.01' } }}
      />
      <TextField select label={t('receipts.refundMode')} value={mode} onChange={(e) => setMode(e.target.value as Mode)}>
        {(['CASH', 'UPI', 'BANK'] as const).map((m) => (
          <MenuItem key={m} value={m}>
            {m}
          </MenuItem>
        ))}
      </TextField>
      {mode === 'CASH' ? (
        <FormControlLabel
          control={<Checkbox checked={fromTill} onChange={(e) => setFromTill(e.target.checked)} />}
          label={t('receipts.refundFromTill')}
        />
      ) : (
        <TextField
          select
          required
          label={t('receipts.refundBank')}
          value={effectiveBank}
          onChange={(e) => setBank(e.target.value)}
          error={!effectiveBank}
          helperText={!effectiveBank ? t('receipts.bankRequired') : undefined}
        >
          {choices.map((a) => (
            <MenuItem key={a.id} value={String(a.id)}>
              {a.name}
            </MenuItem>
          ))}
        </TextField>
      )}
      <TextField
        required
        label={t('receipts.refundReason')}
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        error={reason.length > 0 && trimmed.length < MIN_VOID_REASON_LENGTH}
        helperText={
          reason.length > 0 && trimmed.length < MIN_VOID_REASON_LENGTH
            ? t('receipts.voidReasonTooShort', { min: MIN_VOID_REASON_LENGTH })
            : t('receipts.refundReasonHelp')
        }
        slotProps={{ htmlInput: { maxLength: MAX_VOID_REASON_LENGTH } }}
      />
    </ActionDialog>
  );
}

/** Hand back part or all of the money on a receipt that has not been applied to any bill. */
export function RefundAdvanceDialog({
  receipt,
  onClose,
  onDone,
}: {
  receipt: CustomerReceipt | null;
  onClose: () => void;
  onDone: () => void;
}) {
  // Keyed on the receipt so the form (and the reason typed in it) starts fresh for each one.
  return receipt ? <Form key={receipt.id} receipt={receipt} onClose={onClose} onDone={onDone} /> : null;
}
