import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Divider from '@mui/material/Divider';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery } from '@tanstack/react-query';
import { getErrorMessage, userGestureIdempotencyKey } from '@/api/client';
import { createAllocation, listSalesInvoicesPage, unallocatePayment } from '@/api/resources';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { t } from '@/i18n';
import { ActionDialog } from '@/pages/sales/ActionDialog';
import { MAX_VOID_REASON_LENGTH, MIN_VOID_REASON_LENGTH } from '@/pages/sales/receiptStatus';
import type { CustomerReceipt, SalesInvoice } from '@/types/domain';
import { formatMoney, toNumber } from '@/utils/money';

/**
 * Everything about where one receipt's money went, in one place: the bills it is applied to (each
 * can be taken off again, with a reason), and a form to apply what is left to any open bill of the
 * customer, with an amount you choose. Bills are searched on the server, not cut off at a first page.
 */
function Manager({
  receipt,
  canCancel,
  canWrite,
  onClose,
  onChanged,
}: {
  receipt: CustomerReceipt;
  canCancel: boolean;
  canWrite: boolean;
  onClose: () => void;
  onChanged: (message: string) => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const [errorSource, setErrorSource] = useState<unknown>(null);
  const [removing, setRemoving] = useState<number | null>(null);
  const [reason, setReason] = useState('');
  const [query, setQuery] = useState('');
  const debounced = useDebouncedValue(query, 300);
  const [bill, setBill] = useState<SalesInvoice | null>(null);
  const [amount, setAmount] = useState('');
  const room = toNumber(receipt.allocatable ?? receipt.unallocated);
  const live = receipt.status === 'POSTED' || receipt.status === undefined;

  const bills = useQuery({
    queryKey: ['receipt-manage-bills', receipt.customer, debounced],
    queryFn: () =>
      listSalesInvoicesPage({
        status: 'COMPLETED',
        payment_status: 'UNPAID,PARTIAL',
        customer: receipt.customer,
        q: debounced.trim() || undefined,
        pageSize: 50,
      }),
    enabled: canWrite && live && room > 0,
  });
  const choices = (bills.data?.results ?? []).filter((row) => toNumber(row.balance) > 0);

  const fail = (err: unknown) => {
    setError(getErrorMessage(err));
    setErrorSource(err);
  };
  const remove = useMutation({
    mutationFn: (allocationId: number) => unallocatePayment(allocationId, reason.trim().replace(/\s+/g, ' ')),
    onSuccess: () => {
      setRemoving(null);
      setReason('');
      onChanged(t('receipts.manageUnallocated'));
    },
    onError: fail,
  });
  const apply = useMutation({
    mutationFn: () =>
      createAllocation(
        { receipt: receipt.id, salesInvoice: bill!.id, amount: Number(amount) },
        { idempotencyKey: userGestureIdempotencyKey() },
      ),
    onSuccess: () => {
      setBill(null);
      setAmount('');
      onChanged(t('receipts.manageApplyDone'));
    },
    onError: fail,
  });

  const cap = bill ? Math.min(room, toNumber(bill.balance)) : room;
  const lines = receipt.allocationLines ?? [];
  const reasonOk = reason.trim().replace(/\s+/g, ' ').length >= MIN_VOID_REASON_LENGTH;

  return (
    <ActionDialog
      open
      title={t('receipts.manageTitle')}
      onClose={onClose}
      maxWidth="sm"
      error={error}
      errorSource={errorSource}
    >
      <Typography variant="body2" color="text.secondary">
        {receipt.number ?? receipt.id} · {receipt.customerName} · {formatMoney(receipt.amount)}
      </Typography>
      <Typography variant="subtitle2" component="h3">
        {t('receipts.manageApplied')}
      </Typography>
      {lines.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          {t('receipts.manageNone')}
        </Typography>
      ) : (
        <Stack spacing={1}>
          {lines.map((line) => (
            <Box key={line.allocationId ?? `${line.salesInvoice}`}>
              <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
                <Box>
                  <Typography variant="body2">{line.invoiceNumber || `#${line.salesInvoice}`}</Typography>
                  {toNumber(line.discountApplied) > 0 || toNumber(line.tdsApplied) > 0 ? (
                    <Typography variant="caption" color="text.secondary">
                      {t('receipts.manageDiscountTds', {
                        discount: formatMoney(line.discountApplied ?? 0),
                        tds: formatMoney(line.tdsApplied ?? 0),
                      })}
                    </Typography>
                  ) : null}
                </Box>
                <Stack direction="row" spacing={1} alignItems="center">
                  <Typography variant="body2">{formatMoney(line.amount)}</Typography>
                  {canCancel && line.allocationId ? (
                    <Button
                      size="small"
                      color="warning"
                      disabled={remove.isPending}
                      onClick={() => {
                        setRemoving(removing === line.allocationId ? null : line.allocationId!);
                        setReason('');
                      }}
                    >
                      {t('receipts.manageUnallocate')}
                    </Button>
                  ) : null}
                </Stack>
              </Stack>
              {removing === line.allocationId ? (
                <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                  <TextField
                    size="small"
                    fullWidth
                    autoFocus
                    label={t('receipts.manageUnallocateReason')}
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    slotProps={{ htmlInput: { maxLength: MAX_VOID_REASON_LENGTH } }}
                  />
                  <Button
                    variant="contained"
                    color="warning"
                    disabled={!reasonOk || remove.isPending}
                    onClick={() => remove.mutate(line.allocationId!)}
                  >
                    {t('receipts.manageUnallocate')}
                  </Button>
                </Stack>
              ) : null}
            </Box>
          ))}
        </Stack>
      )}
      {canWrite && live && room > 0 ? (
        <>
          <Divider />
          <Typography variant="subtitle2" component="h3">
            {t('receipts.manageAddTitle')}
          </Typography>
          <Autocomplete
            options={choices}
            getOptionLabel={(o) => `${o.number ?? o.id} · ${formatMoney(o.balance)}`}
            filterOptions={(opts) => opts}
            inputValue={query}
            onInputChange={(_, v, why) => {
              if (why === 'input' || why === 'clear' || why === 'reset') setQuery(v);
            }}
            value={bill}
            onChange={(_, v) => {
              setBill(v);
              if (v) setAmount(String(Math.min(room, toNumber(v.balance))));
            }}
            loading={bills.isFetching}
            noOptionsText={t('receipts.manageNoBills')}
            renderInput={(params) => <TextField {...params} label={t('receipts.manageSearch')} />}
          />
          {bill ? (
            <Stack direction="row" spacing={1} alignItems="flex-start">
              <TextField
                type="number"
                label={t('receipts.manageAmount')}
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                error={Number(amount) > cap + 0.001}
                helperText={t('receipts.refundMax', { max: formatMoney(cap) })}
                slotProps={{ htmlInput: { min: 0, max: cap, step: '0.01' } }}
              />
              <Button
                variant="contained"
                sx={{ mt: 0.5 }}
                disabled={!(Number(amount) > 0) || Number(amount) > cap + 0.001 || apply.isPending}
                onClick={() => apply.mutate()}
              >
                {t('receipts.manageApply')}
              </Button>
            </Stack>
          ) : null}
        </>
      ) : null}
      {receipt.reviewFlags?.includes('invoice_returned_after_payment') ? (
        <Alert severity="warning">{t('receipts.reviewInvoiceReturned')}</Alert>
      ) : null}
    </ActionDialog>
  );
}

export function AllocationManagerDialog(props: {
  receipt: CustomerReceipt | null;
  canCancel: boolean;
  canWrite: boolean;
  onClose: () => void;
  onChanged: (message: string) => void;
}) {
  const { receipt, ...rest } = props;
  return receipt ? <Manager key={receipt.id} receipt={receipt} {...rest} /> : null;
}
