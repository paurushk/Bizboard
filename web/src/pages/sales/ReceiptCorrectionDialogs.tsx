import { useState } from 'react';
import Autocomplete from '@mui/material/Autocomplete';
import Box from '@mui/material/Box';
import MenuItem from '@mui/material/MenuItem';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import {
  correctClosedTill,
  editReceipt,
  listBankAccounts,
  listCustomersPage,
  reassignReceiptCustomer,
} from '@/api/resources';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { t } from '@/i18n';
import { ActionDialog } from '@/pages/sales/ActionDialog';
import { MAX_VOID_REASON_LENGTH, MIN_VOID_REASON_LENGTH } from '@/pages/sales/receiptStatus';
import type { Customer, CustomerReceipt } from '@/types/domain';
import { formatMoney } from '@/utils/money';

function useReasonState() {
  const [reason, setReason] = useState('');
  const trimmed = reason.trim().replace(/\s+/g, ' ');
  return { reason, setReason, trimmed, tooShort: trimmed.length < MIN_VOID_REASON_LENGTH };
}

function ReasonField({
  label,
  state,
}: {
  label: string;
  state: ReturnType<typeof useReasonState>;
}) {
  return (
    <TextField
      autoFocus
      required
      label={label}
      value={state.reason}
      onChange={(e) => state.setReason(e.target.value)}
      error={state.reason.length > 0 && state.tooShort}
      helperText={
        state.reason.length > 0 && state.tooShort
          ? t('receipts.voidReasonTooShort', { min: MIN_VOID_REASON_LENGTH })
          : t('receipts.voidReasonHelp')
      }
      slotProps={{ htmlInput: { maxLength: MAX_VOID_REASON_LENGTH } }}
    />
  );
}

function useFailure() {
  const [error, setError] = useState<string | null>(null);
  const [source, setSource] = useState<unknown>(null);
  return {
    error,
    source,
    fail: (err: unknown) => {
      setError(getErrorMessage(err));
      setSource(err);
    },
  };
}

/** Manager: void a cash receipt that was counted in a closed till, and record why on that till. */
function CorrectTillForm({ receipt, onClose, onDone }: { receipt: CustomerReceipt; onClose: () => void; onDone: () => void }) {
  const state = useReasonState();
  const failure = useFailure();
  const mutation = useMutation({
    mutationFn: () => correctClosedTill(receipt.id, state.trimmed),
    onSuccess: onDone,
    onError: failure.fail,
  });
  return (
    <ActionDialog
      open
      title={t('receipts.tillTitle')}
      onClose={onClose}
      onConfirm={() => mutation.mutate()}
      confirmLabel={t('receipts.actionCorrectTill')}
      confirmColor="warning"
      confirmDisabled={state.tooShort}
      pending={mutation.isPending}
      error={failure.error}
      errorSource={failure.source}
    >
      <Typography variant="body2" color="text.secondary">
        {receipt.number ?? receipt.id} · {receipt.customerName} · {formatMoney(receipt.amount)}
      </Typography>
      <Typography variant="body2">{t('receipts.tillBody', { date: receipt.receiptDate })}</Typography>
      <ReasonField label={t('receipts.voidReasonLabel')} state={state} />
    </ActionDialog>
  );
}

export function CorrectClosedTillDialog(props: {
  receipt: CustomerReceipt | null;
  onClose: () => void;
  onDone: () => void;
}) {
  return props.receipt ? (
    <CorrectTillForm key={props.receipt.id} receipt={props.receipt} onClose={props.onClose} onDone={props.onDone} />
  ) : null;
}

/** Move money that landed on the walk-in account to the customer who actually paid. */
function ReassignForm({ receipt, onClose, onDone }: { receipt: CustomerReceipt; onClose: () => void; onDone: () => void }) {
  const state = useReasonState();
  const failure = useFailure();
  const [target, setTarget] = useState<Customer | null>(null);
  const [query, setQuery] = useState('');
  const debounced = useDebouncedValue(query, 300);
  const customers = useQuery({
    queryKey: ['customers-reassign-lookup', debounced],
    queryFn: () => listCustomersPage({ q: debounced.trim() || undefined, status: 'ACTIVE', pageSize: 50 }),
  });
  const choices = (customers.data?.results ?? []).filter((c) => !c.isPosWalkIn);
  const mutation = useMutation({
    mutationFn: () => reassignReceiptCustomer(receipt.id, { customer: target!.id, reason: state.trimmed }),
    onSuccess: onDone,
    onError: failure.fail,
  });
  return (
    <ActionDialog
      open
      title={t('receipts.reassignTitle')}
      onClose={onClose}
      onConfirm={() => mutation.mutate()}
      confirmLabel={t('receipts.actionReassign')}
      confirmDisabled={!target || state.tooShort}
      pending={mutation.isPending}
      error={failure.error}
      errorSource={failure.source}
    >
      <Typography variant="body2" color="text.secondary">
        {receipt.number ?? receipt.id} · {formatMoney(receipt.amount)}
      </Typography>
      <Typography variant="body2">{t('receipts.reassignHelp')}</Typography>
      <Autocomplete
        options={choices}
        getOptionLabel={(o) => `${o.name}${o.phone ? ` (${o.phone})` : ''}`}
        filterOptions={(opts) => opts}
        inputValue={query}
        onInputChange={(_, v, reason) => {
          if (reason === 'input' || reason === 'clear' || reason === 'reset') setQuery(v);
        }}
        value={target}
        onChange={(_, v) => setTarget(v)}
        loading={customers.isFetching}
        renderInput={(params) => (
          <TextField {...params} required label={t('billing.customer')} placeholder={t('receipts.searchCustomerPlaceholder')} />
        )}
      />
      <ReasonField label={t('receipts.refundReason')} state={state} />
    </ActionDialog>
  );
}

export function ReassignReceiptDialog(props: {
  receipt: CustomerReceipt | null;
  onClose: () => void;
  onDone: () => void;
}) {
  return props.receipt ? (
    <ReassignForm key={props.receipt.id} receipt={props.receipt} onClose={props.onClose} onDone={props.onDone} />
  ) : null;
}

/** Correct the descriptive fields of a posted receipt. Money fields need void and re-enter. */
function EditForm({ receipt, onClose, onDone }: { receipt: CustomerReceipt; onClose: () => void; onDone: () => void }) {
  const failure = useFailure();
  const [notes, setNotes] = useState(receipt.notes ?? '');
  const [reference, setReference] = useState(receipt.reference ?? '');
  const [utr, setUtr] = useState(receipt.utr ?? '');
  const [bank, setBank] = useState(receipt.bankAccount ? String(receipt.bankAccount) : '');
  const bankType = receipt.mode !== 'CASH' && receipt.source !== 'GATEWAY' && !receipt.reconciled;
  const hasUtr = receipt.mode === 'UPI' || receipt.mode === 'BANK';
  const banks = useQuery({ queryKey: ['bank-accounts'], queryFn: listBankAccounts, enabled: bankType });
  const choices = (banks.data ?? []).filter((a) => a.isActive !== false && a.accountType !== 'CASH_BOX');

  const changes: Parameters<typeof editReceipt>[1] = {};
  if (notes !== (receipt.notes ?? '')) changes.notes = notes;
  if (reference !== (receipt.reference ?? '')) changes.reference = reference;
  if (hasUtr && !receipt.reconciled && utr !== (receipt.utr ?? '')) changes.utr = utr;
  if (bankType && bank && Number(bank) !== receipt.bankAccount) changes.bankAccount = Number(bank);

  const mutation = useMutation({
    mutationFn: () => editReceipt(receipt.id, changes),
    onSuccess: onDone,
    onError: failure.fail,
  });
  return (
    <ActionDialog
      open
      title={t('receipts.editTitle')}
      onClose={onClose}
      onConfirm={() => mutation.mutate()}
      confirmDisabled={Object.keys(changes).length === 0}
      pending={mutation.isPending}
      error={failure.error}
      errorSource={failure.source}
    >
      <Typography variant="body2" color="text.secondary">
        {receipt.number ?? receipt.id} · {receipt.customerName} · {formatMoney(receipt.amount)}
      </Typography>
      <Typography variant="caption" color="text.secondary">
        {t('receipts.editLocked')}
      </Typography>
      <TextField label={t('receipts.editNotes')} value={notes} onChange={(e) => setNotes(e.target.value)} multiline minRows={2} />
      <TextField label={t('receipts.editReference')} value={reference} onChange={(e) => setReference(e.target.value)} />
      {hasUtr ? (
        <TextField
          label={t('sweep.utrReference')}
          value={utr}
          onChange={(e) => setUtr(e.target.value)}
          disabled={Boolean(receipt.reconciled)}
        />
      ) : null}
      {receipt.mode !== 'CASH' ? (
        <Box>
          <TextField
            select
            fullWidth
            label={t('sweep.depositToBank')}
            value={bank}
            onChange={(e) => setBank(e.target.value)}
            disabled={!bankType}
            helperText={!bankType ? t('receipts.editBankLocked') : undefined}
          >
            {choices.map((a) => (
              <MenuItem key={a.id} value={String(a.id)}>
                {a.name}
              </MenuItem>
            ))}
          </TextField>
        </Box>
      ) : null}
    </ActionDialog>
  );
}

export function EditReceiptDialog(props: {
  receipt: CustomerReceipt | null;
  onClose: () => void;
  onDone: () => void;
}) {
  return props.receipt ? (
    <EditForm key={props.receipt.id} receipt={props.receipt} onClose={props.onClose} onDone={props.onDone} />
  ) : null;
}
