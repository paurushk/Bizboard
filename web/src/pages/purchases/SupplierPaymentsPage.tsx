import { withGstinHoldOverride } from '@/utils/overrideRetry';
import { useState } from 'react';
import { UnsavedChangesGuard } from '@/components/UnsavedChangesGuard';
import { dialogAmountDirty } from '@/pages/moneyFormDirty';
import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import FormControlLabel from '@mui/material/FormControlLabel';
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
import { Link as RouterLink, useSearchParams } from 'react-router-dom';
import { getErrorMessage, userGestureIdempotencyKey } from '@/api/client';
import {
  createAllocation,
  createSupplierPayment,
  getSupplierPaymentsSummary,
  listAllPurchases,
  listSupplierPaymentsPage,
  listSuppliers,
  setSupplierPaymentChequeStatus,
  voidSupplierPayment,
} from '@/api/resources';
import { ChequePaymentFields, type ChequePaymentValues } from '@/components/ChequePaymentFields';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { todayIso } from '@/components/billing';
import { MoneyHandoffBar } from '@/components/MoneyHandoffBar';
import { PageTitle } from '@/contextHelp';
import { isMoneyHubEnabled } from '@/config/featureFlags';
import { useAuth } from '@/auth/AuthContext';
import { canViewFinancialReports } from '@/utils/permissions';
import { confirmAction } from '@/utils/confirmBridge';
import { invalidatePurchaseSideEffects } from '@/pages/purchases/purchaseQueries';
import { t, useLocale } from '@/i18n';
import { trackShopFloor } from '@/lib/telemetry';
import type { PaymentMode, PurchaseInvoice, Supplier } from '@/types/domain';
import { formatMoney, toNumber } from '@/utils/money';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';

const PAGE_SIZE = 50;

export function SupplierPaymentsPage() {
  useLocale();
  const qc = useQueryClient();
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [page, setPage] = useState(1);
  // The Money hub links here with these three filters (cheques still to clear, money not yet
  // applied to a bill, one supplier).
  const [chequeStatus, setChequeStatus] = useState(() => {
    const raw = (searchParams.get('cheque_status') ?? '').toUpperCase();
    return ['PENDING_CLEARANCE', 'CLEARED', 'BOUNCED'].includes(raw) ? raw : '';
  });
  const [advanceOnly, setAdvanceOnly] = useState(() => searchParams.get('advance') === '1');
  const [supplierFilter, setSupplierFilter] = useState(() => {
    const raw = searchParams.get('supplier') ?? '';
    return /^\d+$/.test(raw) ? raw : '';
  });
  const filters = {
    cheque_status: chequeStatus || undefined,
    advance: advanceOnly ? 'true' : undefined,
    supplier: supplierFilter || undefined,
  };
  const filtersActive = Boolean(chequeStatus || advanceOnly || supplierFilter);
  const showAll = () => {
    setChequeStatus('');
    setAdvanceOnly(false);
    setSupplierFilter('');
    setSearchParams({}, { replace: true });
    setPage(1);
  };
  const query = useQuery({
    queryKey: ['supplier-payments', page, filters],
    queryFn: () => listSupplierPaymentsPage({ page, pageSize: PAGE_SIZE, ...filters }),
  });
  const summary = useQuery({
    queryKey: ['supplier-payments-summary', filters],
    queryFn: () => getSupplierPaymentsSummary(filters),
  });
  const suppliers = useQuery({ queryKey: ['suppliers'], queryFn: listSuppliers });
  const purchases = useQuery({
    queryKey: ['purchases', 'completed'],
    queryFn: () => listAllPurchases({ status: 'COMPLETED' }),
  });

  const payments = query.data?.results ?? [];

  const [open, setOpen] = useState(false);
  const [supplier, setSupplier] = useState<Supplier | null>(null);
  const [amount, setAmount] = useState('');
  const [mode, setMode] = useState<PaymentMode>('BANK');
  const [paidFromTill, setPaidFromTill] = useState(false);
  const [purchase, setPurchase] = useState<PurchaseInvoice | null>(null);
  const [allocAmount, setAllocAmount] = useState('');
  const [cheque, setCheque] = useState<ChequePaymentValues>({
    chequeNumber: '',
    chequeBankName: '',
    chequeDate: todayIso(),
  });
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [discardPrompt, setDiscardPrompt] = useState(false);
  const paymentDirty = dialogAmountDirty(open, Boolean(supplier), amount);
  const requestClose = () => {
    if (paymentDirty) setDiscardPrompt(true);
    else setOpen(false);
  };

  // F2-049: keep the allocation default clamped to min(payment, invoice balance)
  // as the payment amount / selected purchase change, instead of a one-shot
  // snapshot taken when the purchase was picked.
  const [seenAllocInputs, setSeenAllocInputs] = useState<{ amount: string; purchase: typeof purchase }>({
    amount,
    purchase,
  });
  if (seenAllocInputs.amount !== amount || seenAllocInputs.purchase !== purchase) {
    setSeenAllocInputs({ amount, purchase });
    if (!purchase) {
      setAllocAmount('');
    } else {
      const cap = Math.min(toNumber(amount), toNumber(purchase.balance));
      setAllocAmount(cap > 0 ? String(cap) : '');
    }
  }

  const createMutation = useMutation({
    mutationFn: async () => {
      if (!supplier) throw new Error(t('purchaseReview.supplierRequired'));
      // BUG-528: reject non-positive amounts (a plain type="number" field
      // let "-500" through since it's a non-empty string).
      const paymentAmount = Number(amount);
      if (!(paymentAmount > 0)) throw new Error(t('purchaseReview.amountAboveZero'));
      if (mode === 'CHEQUE' && (!cheque.chequeNumber.trim() || !cheque.chequeBankName.trim())) {
        throw new Error(`${t('billing.chequeNumber')} / ${t('billing.chequeBank')}`);
      }
      const key = userGestureIdempotencyKey();
      const payment = await withGstinHoldOverride((override) => createSupplierPayment(
        {
          supplier: supplier.id,
          amount: paymentAmount,
          mode,
          paymentDate: todayIso(),
          chequeNumber: mode === 'CHEQUE' ? cheque.chequeNumber.trim() : undefined,
          chequeBankName: mode === 'CHEQUE' ? cheque.chequeBankName.trim() : undefined,
          chequeDate: mode === 'CHEQUE' ? cheque.chequeDate || undefined : undefined,
          chequeImage: mode === 'CHEQUE' ? cheque.chequeImage || undefined : undefined,
          paidFromTill: mode === 'CASH' ? paidFromTill : undefined,
          ...override,
        },
        { idempotencyKey: override.gstinHoldOverride ? `${key}:override` : key },
      ));
      if (purchase && Number(allocAmount) > 0) {
        // F2-023: mirror ReceiptsPage — an over-typed allocation must not exceed
        // the payment amount or the invoice balance.
        const alloc = Number(allocAmount);
        const cap = Math.min(
          paymentAmount,
          toNumber(purchase.balance),
        );
        if (alloc > cap + 0.001) {
          throw new Error(
            t('purchaseReview.allocationTooHigh', { alloc: alloc.toFixed(2), cap: cap.toFixed(2) }),
          );
        }
        await createAllocation(
          {
            supplierPayment: payment.id,
            purchaseInvoice: purchase.id,
            amount: alloc,
          },
          { idempotencyKey: `${key}-alloc` },
        );
      }
      return payment;
    },
    onSuccess: () => {
      setOpen(false);
      setMessage(t('billing.supplierPaymentCreated'));
      // BUG-530: reset the form so reopening doesn't show stale values —
      // ReceiptsPage already did this, this page didn't.
      setSupplier(null);
      setAmount('');
      setPurchase(null);
      setAllocAmount('');
      setCheque({ chequeNumber: '', chequeBankName: '', chequeDate: todayIso() });
      invalidatePurchaseSideEffects(qc);
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const voidMutation = useMutation({
    mutationFn: (id: number) => voidSupplierPayment(id),
    onSuccess: () => {
      trackShopFloor('document_voided', { feature: 'form' });
      setMessage(t('billing.paymentVoided'));
      invalidatePurchaseSideEffects(qc);
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const chequeStatusMutation = useMutation({
    mutationFn: ({ id, chequeStatus }: { id: number; chequeStatus: string }) =>
      setSupplierPaymentChequeStatus(id, chequeStatus),
    onSuccess: () => {
      setMessage(t('billing.chequeStatusUpdated'));
      invalidatePurchaseSideEffects(qc);
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  // BUG-529: only offer purchases with an outstanding balance.
  const openPurchases = (purchases.data ?? []).filter(
    (p) =>
      p.status === 'COMPLETED' &&
      (!supplier || p.supplier === supplier.id) &&
      toNumber(p.balance) > 0,
  );

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <PageTitle>{t('nav.supplierPayments')}</PageTitle>
        <Button variant="contained" onClick={() => setOpen(true)}>
          {t('phase1.newSupplierPayment')}
        </Button>
      </Stack>
      {message ? <Alert severity="success">{message}</Alert> : null}
      {error ? <HelpErrorAlert message={error} /> : null}
      <MoneyHandoffBar
        filterLabel={
          advanceOnly
            ? t('money.filters.advancesPaid')
            : chequeStatus === 'PENDING_CLEARANCE'
              ? t('money.filters.chequesIssued')
              : t('money.filters.supplierPayments')
        }
        onShowAll={showAll}
      />
      {summary.data ? (
        <Box>
          <Box
            display="grid"
            gridTemplateColumns={{ xs: '1fr 1fr', md: summary.data.payable !== null ? 'repeat(5, 1fr)' : 'repeat(3, 1fr)' }}
            gap={2}
            role="group"
            aria-label={t('supplierPayments.kpiGroup')}
          >
            {summary.data.payable !== null ? (
              <Paper sx={{ p: 1.5, textAlign: 'center' }}>
                <Typography variant="caption" color="text.secondary">{t('supplierPayments.kpiPayable')}</Typography>
                <Typography variant="h6" component="p">{formatMoney(summary.data.payable)}</Typography>
              </Paper>
            ) : null}
            {summary.data.overdue !== null ? (
              <Paper sx={{ p: 1.5, textAlign: 'center' }}>
                <Typography variant="caption" color="text.secondary">{t('supplierPayments.kpiOverdue')}</Typography>
                <Typography variant="h6" component="p" color={toNumber(summary.data.overdue) > 0 ? 'error.main' : undefined}>
                  {formatMoney(summary.data.overdue)}
                </Typography>
              </Paper>
            ) : null}
            <Paper sx={{ p: 1.5, textAlign: 'center' }}>
              <Typography variant="caption" color="text.secondary">{t('supplierPayments.kpiPaid')}</Typography>
              <Typography variant="h6" component="p">{formatMoney(summary.data.paid)}</Typography>
            </Paper>
            <Paper sx={{ p: 1.5, textAlign: 'center' }}>
              <Typography variant="caption" color="text.secondary">{t('supplierPayments.kpiAdvance')}</Typography>
              <Typography variant="h6" component="p" color="info.main">{formatMoney(summary.data.advance)}</Typography>
            </Paper>
            <Paper sx={{ p: 1.5, textAlign: 'center' }}>
              <Typography variant="caption" color="text.secondary">{t('supplierPayments.kpiChequesPending')}</Typography>
              <Typography
                variant="h6"
                component="p"
                color={toNumber(summary.data.chequesPending) > 0 ? 'warning.main' : undefined}
              >
                {formatMoney(summary.data.chequesPending)}
              </Typography>
            </Paper>
          </Box>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
            {t('supplierPayments.kpiNote', { excluded: summary.data.excludedCount })}{' '}
            {canViewFinancialReports(user) && isMoneyHubEnabled() ? (
              <RouterLink to="/money">{t('receipts.kpiSeeMoney')}</RouterLink>
            ) : null}
          </Typography>
        </Box>
      ) : summary.isError ? (
        <Typography variant="caption" color="text.secondary">{t('receipts.kpiUnavailable')}</Typography>
      ) : null}
      <Paper sx={{ p: 1.5 }}>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} alignItems={{ xs: 'stretch', md: 'center' }} useFlexGap flexWrap="wrap">
          <TextField
            select
            size="small"
            label={t('receipts.chequeFilter')}
            value={chequeStatus}
            onChange={(e) => {
              setChequeStatus(e.target.value);
              setPage(1);
            }}
            sx={{ minWidth: 170 }}
          >
            <MenuItem value="">{t('common.all')}</MenuItem>
            <MenuItem value="PENDING_CLEARANCE">{t('supplierPayments.chequePending')}</MenuItem>
            <MenuItem value="CLEARED">{t('receipts.chequeCleared')}</MenuItem>
            <MenuItem value="BOUNCED">{t('receipts.chequeBounced')}</MenuItem>
          </TextField>
          <FormControlLabel
            control={
              <Checkbox
                size="small"
                checked={advanceOnly}
                onChange={(e) => {
                  setAdvanceOnly(e.target.checked);
                  setPage(1);
                }}
              />
            }
            label={t('supplierPayments.notYetApplied')}
          />
          {supplierFilter ? (
            <Chip
              size="small"
              label={t('supplierPayments.oneSupplier')}
              onDelete={() => {
                setSupplierFilter('');
                setPage(1);
              }}
            />
          ) : null}
          {filtersActive ? (
            <Button size="small" onClick={showAll}>
              {t('common.clearFilters')}
            </Button>
          ) : null}
        </Stack>
      </Paper>
      <Typography variant="caption" color="text.secondary">
        {t('billing.paymentActionsHelp')}
      </Typography>
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {payments.length === 0 && query.isSuccess ? (
        <EmptyState
          description={t('purchaseReview.recordPaymentsHint')}
          action={
            <Button variant="contained" onClick={() => setOpen(true)}>
              {t('phase1.newSupplierPayment')}
            </Button>
          }
        />
      ) : null}
      {payments.length > 0 ? (
        <Paper tabIndex={0} role="region" aria-label={t('common.scrollableTable')} sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('common.number')}</TableCell>
                <TableCell>{t('common.date')}</TableCell>
                <TableCell>{t('billing.supplier')}</TableCell>
                <TableCell>{t('sweep2.mode')}</TableCell>
                <TableCell align="right">{t('common.amount')}</TableCell>
                <TableCell align="right">{t('sweep2.allocated')}</TableCell>
                <TableCell align="right">{t('supplierPayments.colNotApplied')}</TableCell>
                <TableCell align="right">{t('common.actions')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {payments.map((p) => (
                <TableRow key={p.id}>
                  <TableCell>{p.number ?? p.id}</TableCell>
                  <TableCell>{p.paymentDate}</TableCell>
                  <TableCell>{p.supplierName}</TableCell>
                  <TableCell>{p.mode}</TableCell>
                  <TableCell align="right">{formatMoney(p.amount)}</TableCell>
                  <TableCell align="right">{formatMoney(p.allocated)}</TableCell>
                  <TableCell align="right">{formatMoney(p.unallocated ?? 0)}</TableCell>
                  <TableCell align="right">
                    {p.status && p.status !== 'POSTED' ? (
                      <Chip size="small" label={p.status} />
                    ) : (
                      <Stack direction="row" spacing={0.5} justifyContent="flex-end" useFlexGap flexWrap="wrap">
                        {p.mode === 'CHEQUE' && p.chequeStatus === 'PENDING_CLEARANCE' ? (
                          <Button
                            size="small"
                            title={t('billing.clearChequeHint')}
                            disabled={chequeStatusMutation.isPending}
                            onClick={() =>
                              chequeStatusMutation.mutate({ id: p.id, chequeStatus: 'CLEARED' })
                            }
                          >
                            {t('billing.clearCheque')}
                          </Button>
                        ) : null}
                        {p.mode === 'CHEQUE' &&
                        (p.chequeStatus === 'PENDING_CLEARANCE' || p.chequeStatus === 'CLEARED') ? (
                          <Button
                            size="small"
                            color="warning"
                            title={t('billing.bounceChequeHint')}
                            disabled={chequeStatusMutation.isPending}
                            onClick={() => {
                              void confirmAction(t('billing.confirmBounceCheque')).then((ok) => {
                                if (ok) chequeStatusMutation.mutate({ id: p.id, chequeStatus: 'BOUNCED' });
                              });
                            }}
                          >
                            {t('billing.bounceCheque')}
                          </Button>
                        ) : null}
                        <Button
                          size="small"
                          color="warning"
                          title={t('billing.voidHint')}
                          disabled={voidMutation.isPending}
                          onClick={() => {
                            void confirmAction(t('billing.confirmVoidPayment')).then((ok) => {
                              if (ok) voidMutation.mutate(p.id);
                            });
                          }}
                        >
                          {t('billing.void')}
                        </Button>
                      </Stack>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}
      {query.data && (query.data.next || page > 1) ? (
        <Stack direction="row" spacing={1} justifyContent="flex-end" alignItems="center">
          <Typography variant="body2" color="text.secondary">
            {t('common.page')} {page}
          </Typography>
          <Button variant="outlined" size="small" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            {t('common.previous')}
          </Button>
          <Button
            variant="outlined"
            size="small"
            disabled={!query.data.next}
            onClick={() => setPage((p) => p + 1)}
          >
            {t('common.next')}
          </Button>
        </Stack>
      ) : null}

      <UnsavedChangesGuard
        when={paymentDirty}
        prompt={discardPrompt}
        onStay={() => setDiscardPrompt(false)}
        onLeave={() => {
          setDiscardPrompt(false);
          setOpen(false);
          setAmount('');
          setSupplier(null);
        }}
      />
      <Dialog open={open} onClose={requestClose} fullWidth maxWidth="sm">
        <DialogTitle>{t('billing.newSupplierPayment')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Autocomplete
              options={suppliers.data ?? []}
              getOptionLabel={(o) => o.name}
              value={supplier}
              onChange={(_, v) => setSupplier(v)}
              renderInput={(params) => <TextField {...params} label={t('billing.supplier')} />}
            />
            <TextField
              type="number"
              label={t('common.amount')}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
            <TextField select label={t('billing.paymentMode')} value={mode} onChange={(e) => setMode(e.target.value as PaymentMode)}>
              {(['CASH', 'UPI', 'BANK', 'CARD', 'CREDIT', 'CHEQUE'] as const).map((m) => (
                <MenuItem key={m} value={m}>
                  {t(`billing.payMode.${m}`)}
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
            <Autocomplete
              options={openPurchases}
              getOptionLabel={(o) => `${o.number ?? o.id} · ${formatMoney(o.grandTotal)}`}
              value={purchase}
              onChange={(_, v) => setPurchase(v)}
              renderInput={(params) => (
                <TextField {...params} label={t('billing.allocateToPurchase')} />
              )}
            />
            {purchase ? (
              <TextField
                type="number"
                label={t('common.allocate')}
                value={allocAmount}
                onChange={(e) => setAllocAmount(e.target.value)}
              />
            ) : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={requestClose}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={!supplier || !amount || createMutation.isPending}
            onClick={() => createMutation.mutate()}
          >
            {t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
