import { useState } from 'react';
import { UnsavedChangesGuard } from '@/components/UnsavedChangesGuard';
import { dialogAmountDirty } from '@/pages/moneyFormDirty';
import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import Chip from '@mui/material/Chip';
import FormControlLabel from '@mui/material/FormControlLabel';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Drawer from '@mui/material/Drawer';
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
import useMediaQuery from '@mui/material/useMediaQuery';
import { getErrorMessage, userGestureIdempotencyKey } from '@/api/client';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import {
  createAllocation,
  createReceipt,
  listCustomersPage,
  listBankAccounts,
  listReceiptsPage,
  listSalesInvoicesPage,
  setReceiptChequeStatus,
  voidReceipt,
} from '@/api/resources';
import { ChequePaymentFields, type ChequePaymentValues } from '@/components/ChequePaymentFields';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { useAuth } from '@/auth/AuthContext';
import { PageTitle } from '@/contextHelp';
import { t, useLocale } from '@/i18n';
import { trackShopFloor } from '@/lib/telemetry';
import { todayIso } from '@/components/billing';
import type { Customer, CustomerReceipt, PaymentMode, SalesInvoice } from '@/types/domain';
import { formatMoney, toNumber } from '@/utils/money';
import { planOldestFirstAllocation } from '@/pages/sales/receiptAllocation';
import { canCreatePayments } from '@/utils/permissions';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';

export function ReceiptsPage() {
  useLocale();
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
  const [oldestFirst, setOldestFirst] = useState(false);
  const [mode, setMode] = useState<PaymentMode>('CASH');
  const [paidFromTill, setPaidFromTill] = useState(false);
  const [invoice, setInvoice] = useState<SalesInvoice | null>(null);
  const [allocAmount, setAllocAmount] = useState('');
  const [utr, setUtr] = useState('');
  const [bankAccount, setBankAccount] = useState('');
  const [cheque, setCheque] = useState<ChequePaymentValues>({
    chequeNumber: '',
    chequeBankName: '',
    chequeDate: todayIso(),
  });
  const [error, setError] = useState<string | null>(null);
  const [errorSource, setErrorSource] = useState<unknown>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [discardPrompt, setDiscardPrompt] = useState(false);
  const receiptDirty = dialogAmountDirty(open, Boolean(customer), amount);
  const requestClose = () => {
    if (receiptDirty) setDiscardPrompt(true);
    else setOpen(false);
  };
  const [advance, setAdvance] = useState<CustomerReceipt | null>(null);
  const advanceInvoices = useQuery({
    queryKey: ['receipt-allocate-invoices', advance?.customer],
    queryFn: () =>
      listSalesInvoicesPage({ status: 'COMPLETED', customer: advance!.customer, pageSize: 20 }),
    enabled: Boolean(advance?.customer),
  });
  const allocateMutation = useMutation({
    mutationFn: async (invoiceId: number) => {
      if (!advance) throw new Error('Receipt required');
      const bill = (advanceInvoices.data?.results ?? []).find((row) => row.id === invoiceId);
      const amount = Math.min(toNumber(advance.unallocated), toNumber(bill?.balance));
      if (!(amount > 0)) throw new Error('Nothing to allocate');
      await createAllocation(
        { receipt: advance.id, salesInvoice: invoiceId, amount },
        { idempotencyKey: userGestureIdempotencyKey() },
      );
    },
    onSuccess: () => {
      setAdvance(null);
      void qc.invalidateQueries({ queryKey: ['receipts'] });
      void qc.invalidateQueries({ queryKey: ['sales-invoices-open'] });
      void qc.invalidateQueries({ queryKey: ['receipt-allocate-invoices'] });
    },
    onError: (err) => {
      setError(getErrorMessage(err));
      setErrorSource(err);
    },
  });

  const narrowVoid = useMediaQuery('(max-width:899.95px)');
  const [voidId, setVoidId] = useState<number | null>(null);
  const [page, setPage] = useState(1);

  const query = useQuery({
    queryKey: ['receipts', page],
    queryFn: () => listReceiptsPage({ page, pageSize: 50 }),
  });
  const customers = useQuery({
    queryKey: ['customers-receipt-lookup', debouncedCustomerQuery],
    queryFn: () =>
      listCustomersPage({
        q: debouncedCustomerQuery.trim() || undefined,
        status: 'ACTIVE',
        pageSize: 50,
      }),
    enabled: open && canWrite,
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
      if (mode === 'CHEQUE' && (!cheque.chequeNumber.trim() || !cheque.chequeBankName.trim())) {
        throw new Error(`${t('billing.chequeNumber')} / ${t('billing.chequeBank')}`);
      }
      const key = userGestureIdempotencyKey();
      const receipt = await createReceipt(
        {
          customer: customer.id,
          amount: receiptAmount,
          mode,
          receiptDate: todayIso(),
          utr: utr || undefined,
          bankAccount: bankAccount ? Number(bankAccount) : undefined,
          paidFromTill: mode === 'CASH' ? paidFromTill : undefined,
          chequeNumber: mode === 'CHEQUE' ? cheque.chequeNumber.trim() : undefined,
          chequeBankName: mode === 'CHEQUE' ? cheque.chequeBankName.trim() : undefined,
          chequeDate: mode === 'CHEQUE' ? cheque.chequeDate || undefined : undefined,
          chequeImage: mode === 'CHEQUE' ? cheque.chequeImage || undefined : undefined,
          allocateOldest: oldestFirst || undefined,
        },
        { idempotencyKey: key },
      );
      if (!oldestFirst && invoice && Number(allocAmount) > 0) {
        const alloc = Number(allocAmount);
        const maxAlloc = Math.min(
          receiptAmount,
          toNumber(invoice.balance),
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
      setOldestFirst(false);
      setUtr('');
      setBankAccount('');
      setCheque({ chequeNumber: '', chequeBankName: '', chequeDate: todayIso() });
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
      trackShopFloor('document_voided', { feature: 'form' });
      setMessage(t('billing.receiptVoided'));
      void qc.invalidateQueries({ queryKey: ['receipts'] });
      void qc.invalidateQueries({ queryKey: ['sales-invoices-open'] });
    },
    onError: (err) => {
      setError(getErrorMessage(err));
      setErrorSource(err);
    },
  });

  const chequeStatusMutation = useMutation({
    mutationFn: ({ id, chequeStatus }: { id: number; chequeStatus: string }) =>
      setReceiptChequeStatus(id, chequeStatus),
    onSuccess: (receipt) => {
      setMessage(
        receipt.chequeStatus === 'BOUNCED' ? t('billing.bounceCheque') : t('billing.clearCheque'),
      );
      void qc.invalidateQueries({ queryKey: ['receipts'] });
      void qc.invalidateQueries({ queryKey: ['sales-invoices-open'] });
    },
    onError: (err) => {
      setError(getErrorMessage(err));
      setErrorSource(err);
    },
  });

  const receipts = query.data?.results ?? [];
  const showSource = receipts.some((row) => Boolean(row.source && row.source !== 'MANUAL'));
  const showBank = receipts.some((row) => Boolean(row.utr || row.bankAccountName || row.chequeNumber || row.utrWarning));
  // BUG-529: only offer invoices that still have an outstanding balance —
  // previously any COMPLETED invoice was offered regardless of balance,
  // including already fully-paid ones.
  const openInvoices = (invoices.data?.results ?? []).filter(
    (inv) =>
      (!customer || inv.customer === customer.id) &&
      toNumber(inv.balance) > 0,
  );
  const oldestPlan =
    oldestFirst && customer && Number(amount) > 0
      ? planOldestFirstAllocation(openInvoices, Number(amount))
      : [];
  const oldestPreview = !oldestFirst || !customer
    ? ''
    : !(Number(amount) > 0)
      ? t('receipts.oldestPreviewNeedAmount')
      : oldestPlan.length === 0
        ? t('receipts.oldestPreviewAdvance')
        : t('receipts.oldestPreview', {
            list: oldestPlan
              .map((slice) =>
                t(slice.partial ? 'receipts.oldestSlicePartial' : 'receipts.oldestSliceFull', {
                  number: slice.number,
                  amount: formatMoney(slice.amount),
                }),
              )
              .join(', '),
          });

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <PageTitle>{t('nav.receipts')}</PageTitle>
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
          description={t('receipts.empty')}
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
        <Paper tabIndex={0} role="region" aria-label={t('common.scrollableTable')} sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('common.number')}</TableCell>
                <TableCell>{t('common.date')}</TableCell>
                <TableCell>{t('billing.customer')}</TableCell>
                <TableCell>{t('receipts.mode')}</TableCell>
                {showSource ? <TableCell>{t('receipts.source')}</TableCell> : null}
                {showBank ? <TableCell>{t('receipts.utrBank')}</TableCell> : null}
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
                    {showSource ? (
                      <TableCell>
                        {r.source && r.source !== 'MANUAL' ? (
                          <Chip size="small" variant="outlined" label={r.source} />
                        ) : (
                          '—'
                        )}
                      </TableCell>
                    ) : null}
                    {showBank ? (
                      <TableCell>
                        {r.mode === 'CHEQUE'
                          ? [r.chequeNumber, r.chequeBankName, r.chequeStatus].filter(Boolean).join(' · ') || '—'
                          : r.utr ?? r.bankAccountName ?? '—'}
                        {r.utrWarning ? (
                          <Chip size="small" color="warning" sx={{ ml: 1 }} label={t('receipts.utrWarn')} title={r.utrWarning} />
                        ) : null}
                      </TableCell>
                    ) : null}
                    <TableCell align="right">{formatMoney(r.amount)}</TableCell>
                    <TableCell align="right">
                      {formatMoney(r.allocated)}
                      {unallocated > 0 ? (
                        <Chip
                          size="small"
                          color="info"
                          sx={{ ml: 1 }}
                          label={t('receipts.advance', { amount: formatMoney(unallocated) })}
                        />
                      ) : null}
                    </TableCell>
                    <TableCell align="right">
                      {r.status && r.status !== 'POSTED' ? (
                        <Chip size="small" label={r.status} />
                      ) : r.source === 'GATEWAY' ? null : canWrite ? (
                        <Stack direction="row" spacing={0.5} justifyContent="flex-end" useFlexGap flexWrap="wrap">
                          {r.mode === 'CHEQUE' && r.chequeStatus === 'PENDING_CLEARANCE' ? (
                            <Button
                              size="small"
                              disabled={chequeStatusMutation.isPending}
                              onClick={() =>
                                chequeStatusMutation.mutate({ id: r.id, chequeStatus: 'CLEARED' })
                              }
                            >
                              {t('billing.clearCheque')}
                            </Button>
                          ) : null}
                          {r.mode === 'CHEQUE' &&
                          (r.chequeStatus === 'PENDING_CLEARANCE' || r.chequeStatus === 'CLEARED') ? (
                            <Button
                              size="small"
                              color="warning"
                              disabled={chequeStatusMutation.isPending}
                              onClick={() => {
                                if (window.confirm(t('billing.confirmBounceCheque'))) {
                                  chequeStatusMutation.mutate({ id: r.id, chequeStatus: 'BOUNCED' });
                                }
                              }}
                            >
                              {t('billing.bounceCheque')}
                            </Button>
                          ) : null}
                          {r.source === 'GATEWAY' ? null : (
                            <Button
                              size="small"
                              color="warning"
                              disabled={voidMutation.isPending}
                              onClick={() => setVoidId(r.id)}
                            >
                              {t('billing.voidAction')}
                            </Button>
                          )}
                          {unallocated > 0 ? (
                            <Button size="small" variant="outlined" onClick={() => setAdvance(r)}>
                              {t('receipts.allocate')}
                            </Button>
                          ) : null}
                        </Stack>
                      ) : null}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
          <Box display="flex" justifyContent="space-between" alignItems="center" p={2}>
            <Typography variant="body2" color="text.secondary">
              {t('common.pageOf', {
                page,
                pages: Math.max(1, Math.ceil((query.data?.count ?? receipts.length) / 50)),
                total: query.data?.count ?? receipts.length,
              })}
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

      <UnsavedChangesGuard
        when={receiptDirty}
        prompt={discardPrompt}
        onStay={() => setDiscardPrompt(false)}
        onLeave={() => {
          setDiscardPrompt(false);
          setOpen(false);
          setAmount('');
          setCustomer(null);
        }}
      />
      <Dialog open={open && canWrite} onClose={requestClose} fullWidth maxWidth="sm">
        <DialogTitle>{t('sweep2.recordCustomerPayment')}</DialogTitle>
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
                if (reason === 'input' || reason === 'clear' || reason === 'reset') setCustomerQuery(v);
              }}
              value={customer}
              onChange={(_, v) => {
                setCustomer(v);
                setCustomerQuery(v?.name ?? '');
              }}
              loading={customers.isFetching}
              renderOption={(props, option) => (
                <li {...props} key={option.id}>
                  <Box display="flex" justifyContent="space-between" width="100%" alignItems="center">
                    <Typography variant="body2">{option.name}{option.phone ? ` (${option.phone})` : ''}</Typography>
                    {toNumber(option.outstanding) > 0 ? (
                      <Chip
                        size="small"
                        color="warning"
                        variant="outlined"
                        label={t('receipts.dueChip', { amount: formatMoney(option.outstanding) })}
                        sx={{ ml: 1 }}
                      />
                    ) : null}
                  </Box>
                </li>
              )}
              renderInput={(params) => (
                <TextField
                  {...params}
                  label={t('billing.customer')}
                  placeholder={t('receipts.searchCustomerPlaceholder')}
                />
              )}
            />
            <TextField
              type="number"
              label={t('common.amount')}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={oldestFirst}
                  onChange={(e) => {
                    setOldestFirst(e.target.checked);
                    if (e.target.checked) {
                      setInvoice(null);
                      setAllocAmount('');
                    }
                  }}
                />
              }
              label={t('receipts.oldestFirst')}
            />
            {!oldestFirst && customer && Number(amount) > 0 && openInvoices.length > 0 ? (
              <Alert
                severity="info"
                action={
                  <Button color="inherit" size="small" onClick={() => setOldestFirst(true)}>
                    {t('receipts.suggestOldestAction')}
                  </Button>
                }
              >
                {t('receipts.suggestOldest')}
              </Alert>
            ) : null}
            {oldestPreview ? (
              <Typography variant="body2" color="text.secondary">
                {oldestPreview}
              </Typography>
            ) : null}
            <TextField select label={t('sweep.paymentMode')} value={mode} onChange={(e) => setMode(e.target.value as PaymentMode)}>
              {(['CASH', 'UPI', 'BANK', 'CARD', 'CREDIT', 'CHEQUE'] as const).map((m) => (
                <MenuItem key={m} value={m}>
                  {m}
                </MenuItem>
              ))}
            </TextField>
            {mode === 'CASH' ? (
              <FormControlLabel
                control={<Checkbox checked={paidFromTill} onChange={(event) => setPaidFromTill(event.target.checked)} />}
                label={t('phase1.paidFromTill')}
              />
            ) : null}
            {mode === 'CHEQUE' ? <ChequePaymentFields value={cheque} onChange={setCheque} /> : null}
            {(mode === 'BANK' || mode === 'UPI') ? <TextField label={t('sweep.utrReference')} value={utr} onChange={(e) => setUtr(e.target.value)} helperText={t('sweep.utrDuplicateHelp')} /> : null}
            {(mode === 'BANK' || mode === 'UPI') ? <TextField select label={t('sweep.depositToBank')} value={bankAccount} onChange={(e) => setBankAccount(e.target.value)}>
              <MenuItem value="">{t('sweep2.notSpecifiedCashBox')}</MenuItem>
              {(bankAccounts.data ?? []).map((account) => <MenuItem key={account.id} value={account.id}>{account.name}</MenuItem>)}
            </TextField> : null}
            {oldestFirst ? null : (
              <>
                <Autocomplete
                  options={openInvoices}
                  getOptionLabel={(o) =>
                    `Invoice ${o.number ?? o.id} · Due: ${formatMoney(o.balance)}`
                  }
                  value={invoice}
                  onInputChange={(_, v, reason) => {
                    if (reason === 'input' || reason === 'clear' || reason === 'reset') setInvoiceQuery(v);
                  }}
                  onChange={(_, v) => {
                    setInvoice(v);
                    if (v) {
                      setAllocAmount(
                        String(Math.min(toNumber(amount), toNumber(v.balance))),
                      );
                    }
                  }}
                  renderInput={(params) => (
                    <TextField
                      {...params}
                      label={t('sweep.applyToInvoice')}
                      helperText={t('sweep.advanceHelp')}
                    />
                  )}
                />
                {invoice ? (
                  <TextField
                    type="number"
                    label={t('sweep.amountApplied')}
                    value={allocAmount}
                    onChange={(e) => setAllocAmount(e.target.value)}
                  />
                ) : null}
              </>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={requestClose}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={createMutation.isPending}
            onClick={() => createMutation.mutate()}
          >
            {t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>
      {narrowVoid ? (
        <Drawer anchor="bottom" open={voidId != null} onClose={() => setVoidId(null)}>
          <Box sx={{ p: 2 }}>
            <Typography>{t('billing.confirmVoidReceipt')}</Typography>
            <Stack direction="row" spacing={1} sx={{ mt: 2 }}>
              <Button onClick={() => setVoidId(null)}>{t('common.cancel')}</Button>
              <Button
                color="warning"
                variant="contained"
                onClick={() => {
                  if (voidId != null) voidMutation.mutate(voidId);
                  setVoidId(null);
                }}
              >
                {t('billing.voidAction')}
              </Button>
            </Stack>
          </Box>
        </Drawer>
      ) : (
        <Dialog open={voidId != null} onClose={() => setVoidId(null)}>
          <DialogTitle>{t('billing.voidAction')}</DialogTitle>
          <DialogContent>
            <Typography>{t('billing.confirmVoidReceipt')}</Typography>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setVoidId(null)}>{t('common.cancel')}</Button>
            <Button
              color="warning"
              variant="contained"
              onClick={() => {
                if (voidId != null) voidMutation.mutate(voidId);
                setVoidId(null);
              }}
            >
              {t('billing.voidAction')}
            </Button>
          </DialogActions>
        </Dialog>
      )}
      <Dialog open={Boolean(advance)} onClose={() => setAdvance(null)} fullWidth maxWidth="sm">
        <DialogTitle>{t('receipts.allocate')}</DialogTitle>
        <DialogContent>
          <Stack spacing={1} sx={{ mt: 1 }}>
            {(advanceInvoices.data?.results ?? [])
              .filter((row) => toNumber(row.balance) > 0)
              .map((row) => (
                <Button
                  key={row.id}
                  variant="outlined"
                  disabled={allocateMutation.isPending}
                  onClick={() => allocateMutation.mutate(row.id)}
                >
                  {row.number} · {formatMoney(row.balance)}
                </Button>
              ))}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAdvance(null)}>{t('common.cancel')}</Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
