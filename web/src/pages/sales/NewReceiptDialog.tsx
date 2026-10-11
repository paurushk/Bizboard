import { useMemo, useState } from 'react';
import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import Chip from '@mui/material/Chip';
import Collapse from '@mui/material/Collapse';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import FormControlLabel from '@mui/material/FormControlLabel';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage, userGestureIdempotencyKey } from '@/api/client';
import {
  createReceipt,
  getCompany,
  listBankAccounts,
  listCustomersPage,
  listSalesInvoicesPage,
} from '@/api/resources';
import { todayIso } from '@/components/billing';
import { ChequePaymentFields, type ChequePaymentValues } from '@/components/ChequePaymentFields';
import { UnsavedChangesGuard } from '@/components/UnsavedChangesGuard';
import { useAuth } from '@/auth/AuthContext';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { t } from '@/i18n';
import { canQueueReceipt, queueReceipt } from '@/offline/receiptOutbox';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { dialogAmountDirty } from '@/pages/moneyFormDirty';
import { maxCashForBill, planOldestFirstAllocation } from '@/pages/sales/receiptAllocation';
import { BANK_MODES, defaultBankFor } from '@/pages/sales/receiptBank';
import type { Customer, PaymentMode, SalesInvoice } from '@/types/domain';
import { formatMoney, toNumber } from '@/utils/money';

/** New receipts are cash, UPI, bank, card or cheque. CREDIT is not a way of being paid. */
const RECEIPT_MODES = ['CASH', 'UPI', 'BANK', 'CARD', 'CHEQUE'] as const;
const TDS_SECTIONS = ['194C', '194J', '194Q', '194H', '194I', '194A'] as const;
const CASH_LIMIT = 200000;

const EMPTY_CHEQUE = (): ChequePaymentValues => ({ chequeNumber: '', chequeBankName: '', chequeDate: todayIso() });

type Props = {
  open: boolean;
  onClose: () => void;
  /** Called with the message to show once a receipt is saved (or queued offline). */
  onCreated: (message: string) => void;
  /** Called when a receipt was kept on this device instead of being sent. */
  onQueued?: () => void;
};

export function NewReceiptDialog({ open, onClose, onCreated, onQueued }: Props) {
  const { user } = useAuth();
  const qc = useQueryClient();
  const [customerQuery, setCustomerQuery] = useState('');
  const debouncedCustomerQuery = useDebouncedValue(customerQuery, 300);
  const [showInactive, setShowInactive] = useState(false);
  const [invoiceQuery, setInvoiceQuery] = useState('');
  const debouncedInvoiceQuery = useDebouncedValue(invoiceQuery, 300);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [amount, setAmount] = useState('');
  const [receiptDate, setReceiptDate] = useState(todayIso());
  const [oldestFirst, setOldestFirst] = useState(false);
  const [mode, setMode] = useState<PaymentMode>('CASH');
  const [paidFromTill, setPaidFromTill] = useState(false);
  const [invoice, setInvoice] = useState<SalesInvoice | null>(null);
  const [allocAmount, setAllocAmount] = useState('');
  // Once the person types in the applied-amount field it is theirs; until then it follows the amount.
  const [allocTouched, setAllocTouched] = useState(false);
  const [utr, setUtr] = useState('');
  const [bankAccount, setBankAccount] = useState('');
  const [cheque, setCheque] = useState<ChequePaymentValues>(EMPTY_CHEQUE);
  const [showMore, setShowMore] = useState(false);
  const [tds, setTds] = useState('');
  const [tdsSection, setTdsSection] = useState('');
  const [discount, setDiscount] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [errorSource, setErrorSource] = useState<unknown>(null);
  const [discardPrompt, setDiscardPrompt] = useState(false);

  const dirty = dialogAmountDirty(open, Boolean(customer), amount);
  const requestClose = () => {
    if (dirty) setDiscardPrompt(true);
    else onClose();
  };

  const reset = () => {
    setCustomer(null);
    setCustomerQuery('');
    setAmount('');
    setReceiptDate(todayIso());
    setInvoice(null);
    setInvoiceQuery('');
    setAllocAmount('');
    setAllocTouched(false);
    setOldestFirst(false);
    // The last receipt's payment details must not carry into the next one.
    setMode('CASH');
    setPaidFromTill(false);
    setUtr('');
    setBankAccount('');
    setCheque(EMPTY_CHEQUE());
    setShowMore(false);
    setTds('');
    setTdsSection('');
    setDiscount('');
    setError(null);
    setErrorSource(null);
  };

  const company = useQuery({ queryKey: ['company'], queryFn: getCompany, enabled: open, staleTime: 60_000 });
  const customers = useQuery({
    queryKey: ['customers-receipt-lookup', debouncedCustomerQuery, showInactive],
    queryFn: () =>
      listCustomersPage({
        q: debouncedCustomerQuery.trim() || undefined,
        // Active only, unless asked: an archived debtor who finally pays an old bill must be findable.
        status: showInactive ? undefined : 'ACTIVE',
        pageSize: 50,
      }),
    enabled: open,
  });
  // BB-000348: searchable invoices — do not silently truncate to first page only.
  const invoices = useQuery({
    queryKey: ['sales-invoices-open', debouncedInvoiceQuery, customer?.id],
    queryFn: () =>
      listSalesInvoicesPage({
        status: 'COMPLETED',
        // Only bills with money due. Paid bills would push the old unpaid ones off the page.
        payment_status: 'UNPAID,PARTIAL',
        pageSize: 50,
        q: debouncedInvoiceQuery.trim() || undefined,
        customer: customer?.id,
      }),
    enabled: open && Boolean(customer),
  });
  const bankAccounts = useQuery({ queryKey: ['bank-accounts'], queryFn: listBankAccounts, enabled: open });
  const defaultBank = useMemo(() => defaultBankFor(bankAccounts.data ?? []), [bankAccounts.data]);
  const needsBank = (BANK_MODES as readonly string[]).includes(mode);
  const selectableBanks = (bankAccounts.data ?? []).filter(
    (a) => a.isActive !== false && a.accountType !== 'CASH_BOX',
  );

  // Bank-type money lands in the company's default bank unless the person picks another.
  const effectiveBank = bankAccount || (needsBank && defaultBank ? String(defaultBank.id) : '');
  // The applied amount follows the amount until the person edits it, then it is theirs.
  const discountNumber = Number(discount) || 0;
  const tdsNumber = Number(tds) || 0;
  const invoiceCap = invoice
    ? maxCashForBill(invoice.balance, Number(amount) || 0, { discount: discountNumber, tds: tdsNumber })
    : 0;
  const appliedAmount = allocTouched || !invoice || oldestFirst ? allocAmount : String(invoiceCap);

  const openInvoices = (invoices.data?.results ?? []).filter(
    (inv) => (!customer || inv.customer === customer.id) && toNumber(inv.balance) > 0,
  );
  const oldestPlan =
    oldestFirst && customer && Number(amount) > 0
      ? planOldestFirstAllocation(openInvoices, Number(amount), { discount: discountNumber, tds: tdsNumber })
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

  const createMutation = useMutation({
    mutationFn: async () => {
      if (!customer) throw new Error(t('billing.customer'));
      // BUG-528: a plain type="number" field with only a truthiness check
      // let a negative amount ("-500" is a non-empty string) through.
      const receiptAmount = Number(amount);
      if (!(receiptAmount > 0)) throw new Error(t('receipts.amountPositive'));
      if (receiptDate > todayIso()) throw new Error(t('receipts.futureDate'));
      if (mode === 'CHEQUE' && (!cheque.chequeNumber.trim() || !cheque.chequeBankName.trim())) {
        throw new Error(`${t('billing.chequeNumber')} / ${t('billing.chequeBank')}`);
      }
      if (needsBank && !effectiveBank) throw new Error(t('receipts.bankRequired'));
      if (discountNumber < 0 || discountNumber > receiptAmount + 0.001) throw new Error(t('receipts.discountTooHigh'));
      if (tdsNumber < 0 || tdsNumber > receiptAmount + 0.001) throw new Error(t('receipts.tdsTooHigh'));
      if (discountNumber > 0 && !oldestFirst && !invoice) throw new Error(t('receipts.discountNeedsInvoice'));
      let applied: number | undefined;
      if (!oldestFirst && invoice) {
        applied = Number(appliedAmount);
        const maxAlloc = invoiceCap;
        if (!(applied > 0) || applied > maxAlloc + 0.001) {
          throw new Error(t('receipts.allocationRange', { max: maxAlloc.toFixed(2) }));
        }
      }
      // A walk-in has no account to hold an advance. The server enforces this too; this
      // just says so before the round trip. Oldest-first is judged by the server, which sees
      // every open bill rather than the first page of them.
      if (customer.isPosWalkIn) {
        if (!oldestFirst && (applied == null || Math.abs(applied - receiptAmount) > 0.005)) {
          throw new Error(t('receipts.walkInNeedsFull'));
        }
      }
      const payload = {
        customer: customer.id,
        amount: receiptAmount,
        mode,
        receiptDate: receiptDate || todayIso(),
        utr: utr || undefined,
        bankAccount: effectiveBank ? Number(effectiveBank) : undefined,
        paidFromTill: mode === 'CASH' ? paidFromTill : undefined,
        chequeNumber: mode === 'CHEQUE' ? cheque.chequeNumber.trim() : undefined,
        chequeBankName: mode === 'CHEQUE' ? cheque.chequeBankName.trim() : undefined,
        chequeDate: mode === 'CHEQUE' ? cheque.chequeDate || undefined : undefined,
        chequeImage: mode === 'CHEQUE' ? cheque.chequeImage || undefined : undefined,
        allocateOldest: oldestFirst || undefined,
        salesInvoice: applied != null && invoice ? invoice.id : undefined,
        allocateAmount: applied,
        settlementDiscount: discountNumber > 0 ? discountNumber : undefined,
        tdsDeducted: tdsNumber > 0 ? tdsNumber : undefined,
        tdsSection: tdsNumber > 0 && tdsSection ? tdsSection : undefined,
      };
      const key = userGestureIdempotencyKey();
      const queueOffline = async () => {
        if (!user || !canQueueReceipt(mode)) return null;
        try {
          await queueReceipt({
            id: key,
            companyId: user.companyId ?? 0,
            userId: user.id,
            payload,
            customerName: customer.name,
          });
          return 'queued' as const;
        } catch {
          // No local storage to keep it in: fall through to the real error.
          return null;
        }
      };
      // No connection: keep a cash or cheque receipt on this device and send it later.
      if (typeof navigator !== 'undefined' && navigator.onLine === false) {
        const queued = await queueOffline();
        if (queued) return queued;
      }
      try {
        // One request: the receipt and its invoice allocation succeed or fail together.
        return await createReceipt(payload, { idempotencyKey: key });
      } catch (err) {
        // The answer never arrived (a request error with no response). The same key makes a later
        // send safe even if this one landed.
        const lost = Boolean((err as { isAxiosError?: boolean })?.isAxiosError) && !(err as { response?: unknown }).response;
        if (lost) {
          const queued = await queueOffline();
          if (queued) return queued;
        }
        throw err;
      }
    },
    onSuccess: (result) => {
      if (result === 'queued') {
        onCreated(t('receipts.offlineQueued'));
        onQueued?.();
      } else {
        const notes = [result.utrWarning, ...(result.warnings ?? [])].filter(Boolean).join(' ');
        onCreated(notes ? t('receipts.createdNote', { note: notes }) : t('receipts.created'));
      }
      reset();
      onClose();
      void qc.invalidateQueries({ queryKey: ['receipts'] });
      void qc.invalidateQueries({ queryKey: ['receipts-summary'] });
      void qc.invalidateQueries({ queryKey: ['sales-invoices-open'] });
      void qc.invalidateQueries({ queryKey: ['receipt-outbox'] });
    },
    onError: (err) => {
      setError(getErrorMessage(err));
      setErrorSource(err);
    },
  });

  const holdCheque = Boolean(company.data?.chequeAllocationOnClearance) && mode === 'CHEQUE' && (oldestFirst || invoice);
  const cashLimitHit = mode === 'CASH' && Number(amount) >= CASH_LIMIT && company.data?.cash269stMode !== 'off';

  return (
    <>
      <UnsavedChangesGuard
        when={dirty}
        prompt={discardPrompt}
        onStay={() => setDiscardPrompt(false)}
        onLeave={() => {
          setDiscardPrompt(false);
          reset();
          onClose();
        }}
      />
      <Dialog open={open} onClose={requestClose} fullWidth maxWidth="sm">
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
                // The bill and the applied amount belong to the customer they were chosen for.
                if (v?.id !== customer?.id) {
                  setInvoice(null);
                  setAllocAmount('');
                  setAllocTouched(false);
                  setInvoiceQuery('');
                }
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
            <FormControlLabel
              control={<Checkbox size="small" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} />}
              label={t('receipts.showInactiveCustomers')}
            />
            {customer?.isPosWalkIn ? <Alert severity="info">{t('receipts.walkInNotice')}</Alert> : null}
            <TextField
              type="date"
              label={t('common.date')}
              value={receiptDate}
              onChange={(e) => setReceiptDate(e.target.value)}
              error={receiptDate > todayIso()}
              helperText={
                receiptDate > todayIso()
                  ? t('receipts.futureDate')
                  : receiptDate && receiptDate < todayIso()
                    ? t('receipts.backdated')
                    : undefined
              }
              slotProps={{ inputLabel: { shrink: true }, htmlInput: { max: todayIso() } }}
            />
            <TextField
              type="number"
              label={t('common.amount')}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
            {cashLimitHit ? <Alert severity="warning">{t('receipts.cashLimitNote')}</Alert> : null}
            <FormControlLabel
              control={
                <Checkbox
                  checked={oldestFirst}
                  onChange={(e) => {
                    setOldestFirst(e.target.checked);
                    if (e.target.checked) {
                      setInvoice(null);
                      setAllocAmount('');
                      setAllocTouched(false);
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
              {RECEIPT_MODES.map((m) => (
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
            {holdCheque ? <Alert severity="info">{t('receipts.chequeHeldNote')}</Alert> : null}
            {needsBank ? (
              <>
                {mode !== 'CARD' ? (
                  <TextField
                    label={t('sweep.utrReference')}
                    value={utr}
                    onChange={(e) => setUtr(e.target.value)}
                    helperText={t('sweep.utrDuplicateHelp')}
                  />
                ) : null}
                {bankAccounts.isSuccess && selectableBanks.length === 0 ? (
                  <Alert severity="warning">{t('receipts.noBankAccount')}</Alert>
                ) : (
                  <TextField
                    select
                    required
                    label={t('sweep.depositToBank')}
                    value={effectiveBank}
                    onChange={(e) => setBankAccount(e.target.value)}
                    error={!effectiveBank}
                    helperText={!effectiveBank ? t('receipts.bankRequired') : undefined}
                  >
                    {selectableBanks.map((account) => (
                      <MenuItem key={account.id} value={String(account.id)}>
                        {account.name}
                      </MenuItem>
                    ))}
                  </TextField>
                )}
              </>
            ) : null}
            {oldestFirst ? null : (
              <>
                <Autocomplete
                  options={openInvoices}
                  getOptionLabel={(o) => `Invoice ${o.number ?? o.id} · Due: ${formatMoney(o.balance)}`}
                  value={invoice}
                  disabled={!customer}
                  onInputChange={(_, v, reason) => {
                    if (reason === 'input' || reason === 'clear' || reason === 'reset') setInvoiceQuery(v);
                  }}
                  onChange={(_, v) => {
                    setInvoice(v);
                    setAllocTouched(false);
                    setAllocAmount('');
                  }}
                  renderInput={(params) => (
                    <TextField {...params} label={t('sweep.applyToInvoice')} helperText={t('sweep.advanceHelp')} />
                  )}
                />
                {invoice ? (
                  <TextField
                    type="number"
                    label={t('sweep.amountApplied')}
                    value={appliedAmount}
                    onChange={(e) => {
                      setAllocTouched(true);
                      setAllocAmount(e.target.value);
                    }}
                  />
                ) : null}
              </>
            )}
            <Box>
              <Button size="small" onClick={() => setShowMore((v) => !v)} aria-expanded={showMore}>
                {t('receipts.moreOptions')}
              </Button>
              <Collapse in={showMore} unmountOnExit>
                <Stack spacing={2} sx={{ mt: 1 }}>
                  <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
                    <TextField
                      type="number"
                      label={t('receipts.tdsDeducted')}
                      value={tds}
                      onChange={(e) => setTds(e.target.value)}
                      helperText={t('receipts.tdsHelp')}
                      slotProps={{ htmlInput: { min: 0 } }}
                      sx={{ flex: 1 }}
                    />
                    <TextField
                      select
                      label={t('receipts.tdsSection')}
                      value={tdsSection}
                      onChange={(e) => setTdsSection(e.target.value)}
                      disabled={!(tdsNumber > 0)}
                      sx={{ minWidth: 140 }}
                    >
                      <MenuItem value="">{t('receipts.tdsSectionOther')}</MenuItem>
                      {TDS_SECTIONS.map((section) => (
                        <MenuItem key={section} value={section}>
                          {section}
                        </MenuItem>
                      ))}
                    </TextField>
                  </Stack>
                  <TextField
                    type="number"
                    label={t('receipts.settlementDiscount')}
                    value={discount}
                    onChange={(e) => setDiscount(e.target.value)}
                    helperText={t('receipts.discountHelp')}
                    slotProps={{ htmlInput: { min: 0 } }}
                  />
                </Stack>
              </Collapse>
            </Box>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={requestClose}>{t('common.cancel')}</Button>
          <Button variant="contained" disabled={createMutation.isPending} onClick={() => createMutation.mutate()}>
            {t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
