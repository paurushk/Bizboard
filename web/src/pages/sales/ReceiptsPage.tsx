import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage, userGestureIdempotencyKey } from '@/api/client';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import {
  createAllocation,
  createReceipt,
  listCustomersPage,
  listBankAccounts,
  listReceiptsPage,
  listSalesInvoicesPage,
  voidReceipt,
} from '@/api/resources';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { useAuth } from '@/auth/AuthContext';
import { t } from '@/i18n';
import { todayIso } from '@/components/billing';
import type { Customer, PaymentMode, SalesInvoice } from '@/types/domain';
import { formatMoney, toNumber } from '@/utils/money';
import { canCreatePayments } from '@/utils/permissions';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';

export function ReceiptsPage() {
  const { user } = useAuth();
  const { writesBlocked } = useSubscriptionGate();
  const canWrite = canCreatePayments(user) && !writesBlocked;
  const qc = useQueryClient();
  const [customerQuery, setCustomerQuery] = useState('');
  const debouncedCustomerQuery = useDebouncedValue(customerQuery, 300);
  const [invoiceQuery, setInvoiceQuery] = useState('');
  const debouncedInvoiceQuery = useDebouncedValue(invoiceQuery, 300);
  const [open, setOpen] = useState(false);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [amount, setAmount] = useState('');
  const [mode, setMode] = useState<PaymentMode>('CASH');
  const [invoice, setInvoice] = useState<SalesInvoice | null>(null);
  const [allocAmount, setAllocAmount] = useState('');
  const [utr, setUtr] = useState('');
  const [bankAccount, setBankAccount] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [errorSource, setErrorSource] = useState<unknown>(null);
  const [message, setMessage] = useState<string | null>(null);

  const [page, setPage] = useState(1);

  const query = useQuery({
    queryKey: ['receipts', page],
    queryFn: () => listReceiptsPage({ page, pageSize: 50 }),
  });
  const customers = useQuery({
    queryKey: ['customers-search', debouncedCustomerQuery],
    queryFn: () => listCustomersPage({ q: debouncedCustomerQuery, pageSize: 50 }),
    enabled: debouncedCustomerQuery.trim().length >= 2,
  });
  // BB-000348: searchable invoices — do not silently truncate to first page only.
  const invoices = useQuery({
    queryKey: ['sales-invoices-open', debouncedInvoiceQuery, customer?.id],
    queryFn: () =>
      listSalesInvoicesPage({
        status: 'COMPLETED',
        pageSize: 50,
        q: debouncedInvoiceQuery.trim() || undefined,
        customer: customer?.id,
      }),
  });
  const bankAccounts = useQuery({ queryKey: ['bank-accounts'], queryFn: listBankAccounts });

  const createMutation = useMutation({
    mutationFn: async () => {
      if (!customer) throw new Error('Customer required');
      // BUG-528: a plain type="number" field with only a truthiness check
      // let a negative amount ("-500" is a non-empty string) through.
      const receiptAmount = Number(amount);
      if (!(receiptAmount > 0)) throw new Error('Amount must be greater than zero');
      const key = userGestureIdempotencyKey();
      const receipt = await createReceipt(
        {
          customer: customer.id,
          amount: receiptAmount,
          mode,
          receiptDate: todayIso(),
          utr: utr || undefined,
          bankAccount: bankAccount ? Number(bankAccount) : undefined,
        },
        { idempotencyKey: key },
      );
      if (invoice && Number(allocAmount) > 0) {
        const alloc = Number(allocAmount);
        const maxAlloc = Math.min(
          receiptAmount,
          toNumber(invoice.balance ?? invoice.grandTotal),
        );
        if (!(alloc > 0) || alloc > maxAlloc + 0.001) {
          throw new Error(
            `Allocation must be between 0.01 and ${maxAlloc.toFixed(2)}`,
          );
        }
        await createAllocation(
          {
            receipt: receipt.id,
            salesInvoice: invoice.id,
            amount: alloc,
          },
          { idempotencyKey: `${key}-alloc` },
        );
      }
      return receipt;
    },
    onSuccess: (receipt) => {
      setOpen(false);
      setMessage(receipt.utrWarning ? `Receipt created — note: ${receipt.utrWarning}` : 'Receipt created');
      setCustomer(null);
      setCustomerQuery('');
      setAmount('');
      setInvoice(null);
      setInvoiceQuery('');
      setAllocAmount('');
      setUtr('');
      setBankAccount('');
      setError(null);
      setErrorSource(null);
      void qc.invalidateQueries({ queryKey: ['receipts'] });
    },
    onError: (err) => {
      setError(getErrorMessage(err));
      setErrorSource(err);
    },
  });

  const voidMutation = useMutation({
    mutationFn: (id: number) => voidReceipt(id),
    onSuccess: () => {
      setMessage('Receipt voided');
      void qc.invalidateQueries({ queryKey: ['receipts'] });
      void qc.invalidateQueries({ queryKey: ['sales-invoices-open'] });
    },
    onError: (err) => {
      setError(getErrorMessage(err));
      setErrorSource(err);
    },
  });

  const receipts = query.data?.results ?? [];
  // BUG-529: only offer invoices that still have an outstanding balance —
  // previously any COMPLETED invoice was offered regardless of balance,
  // including already fully-paid ones.
  const openInvoices = (invoices.data?.results ?? []).filter(
    (inv) =>
      (!customer || inv.customer === customer.id) &&
      toNumber(inv.balance ?? inv.grandTotal) > 0,
  );

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="h4">{t('nav.receipts')}</Typography>
        {canWrite ? (
          <Button
            variant="contained"
            onClick={() => {
              setError(null);
      setErrorSource(null);
              setOpen(true);
            }}
          >
            {t('phase1.newReceipt')}
          </Button>
        ) : null}
      </Stack>
      {message ? <Alert severity="success">{message}</Alert> : null}
      {error ? <HelpErrorAlert message={error} error={errorSource} /> : null}
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {query.data && receipts.length === 0 ? (
        <EmptyState
          description="Record payments received from customers."
          action={
            canWrite ? (
              <Button
                variant="contained"
                onClick={() => {
                  setError(null);
      setErrorSource(null);
                  setOpen(true);
                }}
              >
                {t('phase1.newReceipt')}
              </Button>
            ) : undefined
          }
        />
      ) : null}
      {receipts.length > 0 ? (
        <Paper sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('common.number')}</TableCell>
                <TableCell>{t('common.date')}</TableCell>
                <TableCell>{t('billing.customer')}</TableCell>
                <TableCell>{t('receipts.mode')}</TableCell>
                <TableCell>{t('receipts.source')}</TableCell>
                <TableCell>UTR / Bank</TableCell>
                <TableCell align="right">{t('common.amount')}</TableCell>
                <TableCell align="right">{t('receipts.allocated')}</TableCell>
                <TableCell />
              </TableRow>
            </TableHead>
            <TableBody>
              {receipts.map((r) => {
                const unallocated = toNumber(r.amount) - toNumber(r.allocated);
                return (
                  <TableRow key={r.id}>
                    <TableCell>{r.number ?? r.id}</TableCell>
                    <TableCell>{r.receiptDate}</TableCell>
                    <TableCell>{r.customerName}</TableCell>
                    <TableCell>{r.mode}</TableCell>
                    <TableCell>
                      <Chip size="small" variant="outlined" label={r.source || 'MANUAL'} />
                    </TableCell>
                    <TableCell>
                      {r.utr ?? r.bankAccountName ?? '—'}
                      {r.utrWarning ? (
                        <Chip size="small" color="warning" sx={{ ml: 1 }} label="UTR warn" title={r.utrWarning} />
                      ) : null}
                    </TableCell>
                    <TableCell align="right">{formatMoney(r.amount)}</TableCell>
                    <TableCell align="right">
                      {formatMoney(r.allocated)}
                      {unallocated > 0 ? (
                        <Chip
                          size="small"
                          color="info"
                          sx={{ ml: 1 }}
                          label={`Advance ${formatMoney(unallocated)}`}
                        />
                      ) : null}
                    </TableCell>
                    <TableCell align="right">
                      {r.status && r.status !== 'POSTED' ? (
                        <Chip size="small" label={r.status} />
                      ) : r.source === 'GATEWAY' ? null : canWrite ? (
                        <Button
                          size="small"
                          color="warning"
                          disabled={voidMutation.isPending}
                          onClick={() => {
                            if (window.confirm(t('billing.confirmVoidReceipt'))) {
                              voidMutation.mutate(r.id);
                            }
                          }}
                        >
                          {t('billing.voidAction')}
                        </Button>
                      ) : null}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
          <Box display="flex" justifyContent="space-between" alignItems="center" p={2}>
            <Typography variant="body2" color="text.secondary">
              {t('common.page')} {page}
            </Typography>
            <Box display="flex" gap={1}>
              <Button
                size="small"
                disabled={page <= 1 || query.isFetching}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                {t('common.previous')}
              </Button>
              <Button
                size="small"
                disabled={!query.data?.next || query.isFetching}
                onClick={() => setPage((p) => p + 1)}
              >
                {t('common.next')}
              </Button>
            </Box>
          </Box>
        </Paper>
      ) : null}

      <Dialog open={open && canWrite} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Record Customer Payment (Payment In)</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {/* UXW2B-011: the Save error was only ever rendered on the page behind this
                modal Dialog, so a failed save looked exactly like a silently-dead button. */}
            {error ? <HelpErrorAlert message={error} error={errorSource} /> : null}
            <Autocomplete
              options={customers.data?.results ?? []}
              getOptionLabel={(o) => `${o.name}${o.phone ? ` (${o.phone})` : ''}`}
              filterOptions={(opts) => opts}
              inputValue={customerQuery}
              onInputChange={(_, v, reason) => {
                if (reason === 'input' || reason === 'clear') setCustomerQuery(v);
              }}
              value={customer}
              onChange={(_, v) => {
                setCustomer(v);
                setCustomerQuery(v?.name ?? '');
              }}
              loading={customers.isFetching}
              renderInput={(params) => (
                <TextField
                  {...params}
                  label={t('billing.customer')}
                  placeholder="Search customer by name or phone…"
                />
              )}
            />
            <TextField
              type="number"
              label={t('common.amount')}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
            <TextField select label="Payment Mode" value={mode} onChange={(e) => setMode(e.target.value as PaymentMode)}>
              {(['CASH', 'UPI', 'BANK', 'CARD', 'CREDIT'] as const).map((m) => (
                <MenuItem key={m} value={m}>
                  {m}
                </MenuItem>
              ))}
            </TextField>
            {(mode === 'BANK' || mode === 'UPI') ? <TextField label="UTR / Reference Number" value={utr} onChange={(e) => setUtr(e.target.value)} helperText="Duplicate UTRs in 90 days show a warning" /> : null}
            {(mode === 'BANK' || mode === 'UPI') ? <TextField select label="Deposit to Bank Account" value={bankAccount} onChange={(e) => setBankAccount(e.target.value)}>
              <MenuItem value="">Not specified / Cash Box</MenuItem>
              {(bankAccounts.data ?? []).map((account) => <MenuItem key={account.id} value={account.id}>{account.name}</MenuItem>)}
            </TextField> : null}
            <Autocomplete
              options={openInvoices}
              getOptionLabel={(o) =>
                `Invoice ${o.number ?? o.id} · Due: ${formatMoney(o.balance ?? o.grandTotal)}`
              }
              value={invoice}
              onInputChange={(_, v, reason) => {
                if (reason === 'input' || reason === 'clear') setInvoiceQuery(v);
              }}
              onChange={(_, v) => {
                setInvoice(v);
                if (v) {
                  setAllocAmount(
                    String(Math.min(toNumber(amount), toNumber(v.balance ?? v.grandTotal))),
                  );
                }
              }}
              renderInput={(params) => (
                <TextField
                  {...params}
                  label="Apply to specific invoice (optional)"
                  helperText="Leave blank if this is a general advance payment on account"
                />
              )}
            />
            {invoice ? (
              <TextField
                type="number"
                label="Amount applied to this bill (₹)"
                value={allocAmount}
                onChange={(e) => setAllocAmount(e.target.value)}
              />
            ) : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={createMutation.isPending}
            onClick={() => createMutation.mutate()}
          >
            {t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
