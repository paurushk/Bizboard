import { withGstinHoldOverride } from '@/utils/overrideRetry';
import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Divider from '@mui/material/Divider';
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
import { Link as RouterLink, useLocation, useParams } from 'react-router-dom';
import { getErrorCode, getErrorDetails, getErrorMessage, userGestureIdempotencyKey } from '@/api/client';
import { completeWithConfirms } from '@/utils/completeWithConfirms';
import { invalidatePurchaseSideEffects } from '@/pages/purchases/purchaseQueries';
import {
  cancelPurchase,
  completePurchase,
  downloadPurchasePdf,
  getPurchase,
  recordPurchasePayment,
} from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { ChequePaymentFields, type ChequePaymentValues } from '@/components/ChequePaymentFields';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { todayIso } from '@/components/billing';
import { PageTitle } from '@/contextHelp';
import { StatusChip } from '@/components/StatusChip';
import { t } from '@/i18n';
import { triggerBlobDownload } from '@/utils/blob';
import { formatMoney, toNumber } from '@/utils/money';
import { canAdjustInventory, canCancelDocuments, canCreatePurchases } from '@/utils/permissions';
import { labelItemsParam } from '@/pages/inventory/labelHelpers';
import { documentStatusTone, statusLabelKey } from '@/utils/status';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import type { PaymentMode, PurchaseInvoice, PurchasePayNow, PurchaseRelatedDocument } from '@/types/domain';

const RELATED_GROUPS: Array<{
  key: 'sourceOrders' | 'sourceReceipts' | 'returns' | 'creditNotes' | 'debitNotes';
  labelKey: string;
  href: (id: number) => string;
}> = [
  { key: 'sourceOrders', labelKey: 'purchaseDetail.sourceOrders', href: (id) => `/purchases/orders/${id}` },
  { key: 'sourceReceipts', labelKey: 'purchaseDetail.sourceReceipts', href: () => '/purchases/grns' },
  { key: 'returns', labelKey: 'purchaseDetail.returns', href: () => '/purchases/returns' },
  { key: 'creditNotes', labelKey: 'purchaseDetail.creditNotes', href: (id) => `/purchases/credit-notes/${id}` },
  { key: 'debitNotes', labelKey: 'purchaseDetail.debitNotes', href: (id) => `/purchases/debit-notes/${id}` },
];

function billLabel(inv: Pick<PurchaseInvoice, 'id' | 'number'>): string {
  return inv.number?.trim() ? inv.number : `#${inv.id}`;
}

export function PurchaseDetailPage() {
  const { user } = useAuth();
  const { id } = useParams();
  const location = useLocation();
  const purchaseId = Number(id);
  const qc = useQueryClient();
  // The editor hands over a payment the server refused after completing the bill (WP-1).
  const [paymentRetry, setPaymentRetry] = useState<{ payNow: PurchasePayNow; message: string } | null>(
    () => (location.state as { paymentRetry?: { payNow: PurchasePayNow; message: string } } | null)?.paymentRetry ?? null,
  );
  const [message, setMessage] = useState<string | null>(
    () => (location.state as { message?: string } | null)?.message ?? null,
  );
  const [warnings, setWarnings] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(
    () => (location.state as { paymentWarning?: string } | null)?.paymentWarning ?? null,
  );
  const [cancelOpen, setCancelOpen] = useState(false);
  const [payOpen, setPayOpen] = useState(false);
  const [payAmount, setPayAmount] = useState('');
  const [payMode, setPayMode] = useState<PaymentMode>('CASH');
  const [payDate, setPayDate] = useState(todayIso());
  const [payCheque, setPayCheque] = useState<ChequePaymentValues>({ chequeNumber: '', chequeBankName: '', chequeDate: '' });
  const [payError, setPayError] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ['purchase-invoice', purchaseId],
    queryFn: () => getPurchase(purchaseId),
    enabled: Number.isFinite(purchaseId),
  });

  const completeMutation = useMutation({
    mutationFn: () => completeWithConfirms((extra) => completePurchase(purchaseId, extra)),
    onSuccess: (data) => {
      setError(null);
      setMessage(t('history.completed', { label: billLabel(data) }));
      // Completion notices (duplicate bill, ITC, etc.) must stay visible, not vanish with a toast.
      setWarnings((data.warnings ?? []).filter(Boolean));
      invalidatePurchaseSideEffects(qc, { invoiceId: purchaseId, stock: true });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  // A cancelled supplier GSTIN holds payments: an Owner/Accountant can release it with a reason.
  const payWithHoldOverride = (payNow: PurchasePayNow) => {
    const key = userGestureIdempotencyKey();
    return withGstinHoldOverride((override) =>
      recordPurchasePayment(
        purchaseId,
        { ...payNow, ...override },
        { idempotencyKey: override.gstinHoldOverride ? `${key}:override` : key },
      ),
    );
  };

  const retryPaymentMutation = useMutation({
    mutationFn: (payNow: PurchasePayNow) => payWithHoldOverride(payNow),
    onSuccess: (data) => {
      setPaymentRetry(null);
      setError(null);
      setMessage(t('history.paymentRecorded', { label: billLabel(data) }));
      invalidatePurchaseSideEffects(qc, { invoiceId: purchaseId });
    },
    // Keep the banner (and its Retry) with the newest reason.
    onError: (err) =>
      setPaymentRetry((cur) => (cur ? { ...cur, message: getErrorMessage(err) } : cur)),
  });

  const recordPaymentMutation = useMutation({
    mutationFn: (payNow: PurchasePayNow) => payWithHoldOverride(payNow),
    onSuccess: (data) => {
      setPayOpen(false);
      setPayError(null);
      setPaymentRetry(null);
      setError(null);
      setMessage(t('history.paymentRecorded', { label: billLabel(data) }));
      invalidatePurchaseSideEffects(qc, { invoiceId: purchaseId });
    },
    onError: (err) => setPayError(getErrorMessage(err)),
  });

  const cancelMutation = useMutation({
    mutationFn: (reverseAllocations: boolean) => cancelPurchase(purchaseId, { reverseAllocations }),
    onSuccess: (data, reverseAllocations) => {
      setCancelOpen(false);
      setError(null);
      setWarnings([]);
      setMessage(
        reverseAllocations
          ? `${t('history.cancelled', { label: billLabel(data) })} ${t('purchaseDetail.unlinked')}`
          : t('history.cancelled', { label: billLabel(data) }),
      );
      invalidatePurchaseSideEffects(qc, { invoiceId: purchaseId, stock: true });
    },
    onError: (err) => {
      // The bill gained a payment since this page loaded: refresh so the dialog can explain it.
      if (getErrorCode(err) === 'HAS_ALLOCATIONS') {
        void qc.invalidateQueries({ queryKey: ['purchase-invoice', purchaseId] });
        const total = getErrorDetails(err)?.allocatedTotal;
        setError(
          typeof total === 'string' || typeof total === 'number'
            ? `${getErrorMessage(err)} (${formatMoney(total)})`
            : getErrorMessage(err),
        );
      } else {
        setError(getErrorMessage(err));
      }
      setCancelOpen(false);
    },
  });

  const pdfMutation = useMutation({
    mutationFn: async () => {
      const blob = await downloadPurchasePdf(purchaseId);
      triggerBlobDownload(blob, `${query.data?.number?.trim() || `purchase-${purchaseId}`}.pdf`);
    },
    onError: () => setError(t('purchaseDetail.pdfFailed')),
  });

  if (query.isLoading) return <LoadingState />;
  if (query.isError) {
    return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  }
  if (!query.data) return <EmptyState />;

  const inv = query.data;
  const showTax = inv.purchaseType === 'GST';
  const hasRcm =
    inv.isReverseCharge ||
    inv.rcmTaxable != null ||
    inv.rcmCgst != null ||
    inv.rcmSgst != null ||
    inv.rcmIgst != null;
  const balance = Math.max(0, toNumber(inv.balance));
  const payments = inv.payments ?? [];
  const allocatedTotal = payments.reduce((sum, p) => sum + toNumber(p.amount), 0);
  const related = inv.relatedDocuments;
  const hasRelated = related ? RELATED_GROUPS.some((g) => (related[g.key] ?? []).length > 0) : false;
  const canWrite = canCreatePurchases(user);
  // Amending a completed bill is Owner-only on the server; do not offer a button that dead-ends.
  const canEdit = inv.status === 'DRAFT' ? canWrite : inv.status === 'COMPLETED' && user?.role === 'OWNER';
  const canPay = canWrite && inv.status === 'COMPLETED' && balance > 0;
  const hasTds = toNumber(inv.tdsAmount) > 0 || Boolean(inv.tdsSection);

  const openPayDialog = () => {
    setPayAmount(balance.toFixed(2));
    setPayMode('CASH');
    setPayDate(todayIso());
    setPayCheque({ chequeNumber: '', chequeBankName: '', chequeDate: '' });
    setPayError(null);
    setPayOpen(true);
  };

  const submitPayment = () => {
    const amount = Number(payAmount);
    if (!(amount > 0) || amount > balance + 0.0001) {
      setPayError(t('purchaseDetail.amountInvalid', { amount: formatMoney(balance) }));
      return;
    }
    setPayError(null);
    recordPaymentMutation.mutate({
      amount,
      mode: payMode,
      paymentDate: payDate || undefined,
      chequeNumber: payCheque.chequeNumber || undefined,
      chequeBankName: payCheque.chequeBankName || undefined,
      chequeDate: payCheque.chequeDate || undefined,
      chequeImage: payCheque.chequeImage || undefined,
    });
  };

  const cancelBody =
    payments.length > 0
      ? t('purchaseDetail.cancelBodyPaid', {
          amount: formatMoney(allocatedTotal),
          count: String(payments.length),
        })
      : t('purchaseDetail.cancelBody');

  return (
    <Stack spacing={2}>
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        justifyContent="space-between"
        alignItems={{ xs: 'stretch', sm: 'flex-start' }}
        spacing={1}
      >
        <Box>
          <PageTitle sx={{ fontFamily: '"IBM Plex Sans", sans-serif' }}>
            {inv.number?.trim() ? inv.number : t('history.draftLabel', { id: inv.id })}
          </PageTitle>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 0.5, flexWrap: 'wrap' }} useFlexGap>
            <StatusChip tone={documentStatusTone(inv.status)} labelKey={statusLabelKey(inv.status)} />
            <Chip size="small" label={inv.purchaseType} variant="outlined" />
            {inv.isReverseCharge ? (
              <Chip size="small" label={t('sweep.reverseCharge')} color="warning" variant="outlined" />
            ) : null}
            {inv.itcEligibility ? (
              <Chip
                size="small"
                variant="outlined"
                label={`${t('purchaseDetail.itc')}: ${String(inv.itcEligibility).replace(/_/g, ' ').toLowerCase()}`}
              />
            ) : null}
            <Typography variant="body2" color="text.secondary">
              {inv.invoiceDate}
            </Typography>
          </Stack>
          <Typography sx={{ mt: 1 }}>{inv.supplierName}</Typography>
          <Stack direction="row" spacing={2} useFlexGap flexWrap="wrap" sx={{ mt: 0.5 }}>
            {inv.supplierBillNumber ? (
              <Typography variant="body2" color="text.secondary">
                {t('purchaseDetail.supplierBill')}: {inv.supplierBillNumber}
              </Typography>
            ) : null}
            {inv.dueDate ? (
              <Typography variant="body2" color="text.secondary">
                {t('purchaseDetail.dueDate')}: {inv.dueDate}
              </Typography>
            ) : null}
          </Stack>
        </Box>
        <Button component={RouterLink} to="/purchases/history">
          {t('common.back')}
        </Button>
      </Stack>

      {message ? <Alert severity="success">{message}</Alert> : null}
      {paymentRetry ? (
        <Alert
          severity="warning"
          action={
            <Stack direction="row" spacing={1}>
              <Button
                color="inherit"
                size="small"
                disabled={retryPaymentMutation.isPending}
                onClick={() => retryPaymentMutation.mutate(paymentRetry.payNow)}
              >
                {t('billing.retryPayment')}
              </Button>
              <Button color="inherit" size="small" onClick={() => setPaymentRetry(null)}>
                {t('billing.dismissPaymentNotice')}
              </Button>
            </Stack>
          }
        >
          {t('billing.paymentNotRecorded', {
            amount: formatMoney(paymentRetry.payNow.amount),
            reason: paymentRetry.message,
          })}
        </Alert>
      ) : null}
      {warnings.length > 0 ? (
        <Alert severity="warning">
          <Stack component="ul" spacing={0.25} sx={{ m: 0, pl: 2 }}>
            {warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </Stack>
        </Alert>
      ) : null}
      {error ? <HelpErrorAlert message={error} /> : null}

      <Paper
        elevation={0}
        sx={{
          p: 1.5,
          position: 'sticky',
          top: 0,
          zIndex: 2,
          bgcolor: 'background.paper',
          borderBottom: 1,
          borderColor: 'divider',
        }}
      >
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          {canEdit ? (
            <Button component={RouterLink} to={`/purchases/history/${inv.id}/edit`} variant="outlined">
              {t('common.edit')}
            </Button>
          ) : null}
          {inv.status === 'DRAFT' && canWrite ? (
            <Button
              variant="contained"
              disabled={completeMutation.isPending}
              onClick={() => completeMutation.mutate()}
            >
              {t('common.complete')}
            </Button>
          ) : null}
          {canPay ? (
            <Button variant="contained" onClick={openPayDialog}>
              {t('purchaseDetail.recordPayment')}
            </Button>
          ) : null}
          {inv.status !== 'DRAFT' ? (
            <Button variant="outlined" disabled={pdfMutation.isPending} onClick={() => pdfMutation.mutate()}>
              {t('purchaseDetail.downloadPdf')}
            </Button>
          ) : null}
          {inv.status === 'COMPLETED' && canAdjustInventory(user) && (inv.items ?? []).length > 0 ? (
            <Button
              variant="outlined"
              component={RouterLink}
              to={`/inventory/labels?items=${labelItemsParam((inv.items ?? []).map((i) => ({ product: Number(i.product), quantity: i.quantity })))}`}
            >
              {t('labels.printFromBill')}
            </Button>
          ) : null}
          {inv.status === 'COMPLETED' && canCancelDocuments(user) ? (
            <Button
              color="error"
              variant="outlined"
              disabled={cancelMutation.isPending}
              onClick={() => setCancelOpen(true)}
            >
              {t('common.cancel')}
            </Button>
          ) : null}
        </Stack>
      </Paper>

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
        <Paper sx={{ p: 2, flex: 1 }}>
          <Typography variant="subtitle2" color="text.secondary">
            {t('billing.paymentSummary')}
          </Typography>
          <Divider sx={{ my: 1 }} />
          <Stack spacing={0.75}>
            <Stack direction="row" justifyContent="space-between">
              <Typography>{t('billing.grandTotal')}</Typography>
              <Typography fontWeight={700}>{formatMoney(inv.grandTotal)}</Typography>
            </Stack>
            {hasTds ? (
              <Stack direction="row" justifyContent="space-between">
                <Typography>
                  {t('purchaseDetail.tds')}
                  {inv.tdsSection ? ` (${inv.tdsSection})` : ''}
                </Typography>
                <Typography>{formatMoney(inv.tdsAmount ?? 0)}</Typography>
              </Stack>
            ) : null}
            <Stack direction="row" justifyContent="space-between">
              <Typography>{t('billing.paid')}</Typography>
              <Typography>{formatMoney(inv.paid ?? 0)}</Typography>
            </Stack>
            <Stack direction="row" justifyContent="space-between">
              <Typography>{t('billing.balance')}</Typography>
              <Typography fontWeight={600}>{formatMoney(inv.balance)}</Typography>
            </Stack>
          </Stack>
        </Paper>
        <Paper sx={{ p: 2, flex: 1 }}>
          <Typography variant="subtitle2" color="text.secondary">
            {t('billing.taxTotals')}
          </Typography>
          <Divider sx={{ my: 1 }} />
          <Stack spacing={0.75}>
            <Stack direction="row" justifyContent="space-between">
              <Typography>{t('sweep2.taxable')}</Typography>
              <Typography>{formatMoney(inv.taxableTotal)}</Typography>
            </Stack>
            {showTax ? (
              <>
                <Stack direction="row" justifyContent="space-between">
                  <Typography>{t('purchaseDetail.cgst')}</Typography>
                  <Typography>{formatMoney(inv.cgstTotal)}</Typography>
                </Stack>
                <Stack direction="row" justifyContent="space-between">
                  <Typography>{t('purchaseDetail.sgst')}</Typography>
                  <Typography>{formatMoney(inv.sgstTotal)}</Typography>
                </Stack>
                <Stack direction="row" justifyContent="space-between">
                  <Typography>{t('purchaseDetail.igst')}</Typography>
                  <Typography>{formatMoney(inv.igstTotal)}</Typography>
                </Stack>
              </>
            ) : null}
            {hasRcm ? (
              <>
                <Divider sx={{ my: 0.5 }} />
                <Typography variant="caption" color="text.secondary">
                  {t('sweep2.reverseChargeRcm')}
                </Typography>
                {inv.rcmTaxable != null ? (
                  <Stack direction="row" justifyContent="space-between">
                    <Typography>{t('purchaseDetail.rcmTaxable')}</Typography>
                    <Typography>{formatMoney(inv.rcmTaxable)}</Typography>
                  </Stack>
                ) : null}
                {inv.rcmCgst != null ? (
                  <Stack direction="row" justifyContent="space-between">
                    <Typography>{t('purchaseDetail.rcmCgst')}</Typography>
                    <Typography>{formatMoney(inv.rcmCgst)}</Typography>
                  </Stack>
                ) : null}
                {inv.rcmSgst != null ? (
                  <Stack direction="row" justifyContent="space-between">
                    <Typography>{t('purchaseDetail.rcmSgst')}</Typography>
                    <Typography>{formatMoney(inv.rcmSgst)}</Typography>
                  </Stack>
                ) : null}
                {inv.rcmIgst != null ? (
                  <Stack direction="row" justifyContent="space-between">
                    <Typography>{t('purchaseDetail.rcmIgst')}</Typography>
                    <Typography>{formatMoney(inv.rcmIgst)}</Typography>
                  </Stack>
                ) : null}
              </>
            ) : null}
          </Stack>
        </Paper>
      </Stack>

      <Paper sx={{ p: 2 }} aria-labelledby="purchase-payments-heading">
        <Typography id="purchase-payments-heading" variant="subtitle2" color="text.secondary">
          {t('purchaseDetail.paymentsTitle')}
        </Typography>
        <Divider sx={{ my: 1 }} />
        {payments.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            {t('purchaseDetail.noPayments')}
          </Typography>
        ) : (
          <Box sx={{ overflowX: 'auto' }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>{t('purchaseDetail.colPayment')}</TableCell>
                  <TableCell>{t('purchaseDetail.colDate')}</TableCell>
                  <TableCell>{t('purchaseDetail.colMode')}</TableCell>
                  <TableCell align="right">{t('purchaseDetail.colAmount')}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {payments.map((p) => (
                  <TableRow key={p.allocation}>
                    <TableCell>
                      <RouterLink to="/purchases/payments">{p.number || `#${p.payment}`}</RouterLink>
                    </TableCell>
                    <TableCell>{p.date ?? '—'}</TableCell>
                    <TableCell>
                      {p.mode}
                      {p.chequeStatus ? ` · ${p.chequeStatus.replace(/_/g, ' ').toLowerCase()}` : ''}
                    </TableCell>
                    <TableCell align="right">{formatMoney(p.amount)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Box>
        )}
      </Paper>

      <Paper sx={{ p: 2 }} aria-labelledby="purchase-related-heading">
        <Typography id="purchase-related-heading" variant="subtitle2" color="text.secondary">
          {t('purchaseDetail.relatedTitle')}
        </Typography>
        <Divider sx={{ my: 1 }} />
        {!hasRelated || !related ? (
          <Typography variant="body2" color="text.secondary">
            {t('purchaseDetail.noRelated')}
          </Typography>
        ) : (
          <Stack spacing={1}>
            {RELATED_GROUPS.map((group) => {
              const rows: PurchaseRelatedDocument[] = related[group.key] ?? [];
              if (rows.length === 0) return null;
              return (
                <Stack key={group.key} direction="row" spacing={1} alignItems="center" useFlexGap flexWrap="wrap">
                  <Typography variant="body2" color="text.secondary" sx={{ minWidth: 140 }}>
                    {t(group.labelKey)}
                  </Typography>
                  {rows.map((row) => (
                    <Chip
                      key={row.id}
                      size="small"
                      variant="outlined"
                      component={RouterLink}
                      to={group.href(row.id)}
                      clickable
                      label={`${row.number || `#${row.id}`} · ${t(statusLabelKey(row.status))}`}
                    />
                  ))}
                </Stack>
              );
            })}
          </Stack>
        )}
      </Paper>

      <Paper tabIndex={0} role="region" aria-label={t('common.scrollableTable')} sx={{ overflow: 'auto' }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>#</TableCell>
              <TableCell>{t('nav.products')}</TableCell>
              <TableCell>HSN</TableCell>
              <TableCell align="right">{t('billing.qty')}</TableCell>
              <TableCell align="right">{t('billing.price')}</TableCell>
              <TableCell align="right" sx={{ display: { xs: 'none', md: 'table-cell' } }}>
                {t('purchaseDetail.discount')}
              </TableCell>
              <TableCell sx={{ display: { xs: 'none', md: 'table-cell' } }}>{t('purchaseDetail.batch')}</TableCell>
              {showTax ? <TableCell align="right">{t('billing.tax')}</TableCell> : null}
              <TableCell align="right">{t('common.total')}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {(inv.items ?? []).map((item, idx) => {
              const lineTax = toNumber(item.cgst) + toNumber(item.sgst) + toNumber(item.igst);
              return (
                <TableRow key={item.id ?? `${item.product}-${item.quantity}`}>
                  <TableCell>{idx + 1}</TableCell>
                  <TableCell>{item.productName ?? item.description ?? item.product}</TableCell>
                  <TableCell>{item.hsnCode || '—'}</TableCell>
                  <TableCell align="right">{toNumber(item.quantity)}</TableCell>
                  <TableCell align="right">{formatMoney(item.unitPrice)}</TableCell>
                  <TableCell align="right" sx={{ display: { xs: 'none', md: 'table-cell' } }}>
                    {toNumber(item.discountPercent) > 0 ? `${toNumber(item.discountPercent)}%` : '—'}
                  </TableCell>
                  <TableCell sx={{ display: { xs: 'none', md: 'table-cell' } }}>
                    {(item as { batchNo?: string }).batchNo || '—'}
                  </TableCell>
                  {showTax ? <TableCell align="right">{formatMoney(lineTax)}</TableCell> : null}
                  <TableCell align="right">{formatMoney(item.lineTotal)}</TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </Paper>

      <ConfirmDialog
        open={cancelOpen}
        title={t('purchaseDetail.cancelTitle', { label: billLabel(inv) })}
        body={cancelBody}
        confirmLabel={t('purchaseDetail.cancelConfirm')}
        confirmColor="error"
        confirming={cancelMutation.isPending}
        onConfirm={() => cancelMutation.mutate(payments.length > 0)}
        onClose={() => setCancelOpen(false)}
      />

      <Dialog open={payOpen} onClose={() => setPayOpen(false)} fullWidth maxWidth="xs" aria-labelledby="record-payment-title">
        <DialogTitle id="record-payment-title">
          {t('purchaseDetail.recordTitle', { label: billLabel(inv) })}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Typography variant="body2" color="text.secondary">
              {t('purchaseDetail.recordHint', { amount: formatMoney(balance) })}
            </Typography>
            {payError ? <Alert severity="error">{payError}</Alert> : null}
            <TextField
              label={t('purchaseDetail.amount')}
              value={payAmount}
              onChange={(e) => setPayAmount(e.target.value)}
              inputProps={{ inputMode: 'decimal' }}
              autoFocus
              fullWidth
            />
            <TextField
              select
              label={t('purchaseDetail.paymentMode')}
              value={payMode}
              onChange={(e) => setPayMode(e.target.value as PaymentMode)}
              fullWidth
            >
              <MenuItem value="CASH">{t('sweep2.cash')}</MenuItem>
              <MenuItem value="UPI">UPI</MenuItem>
              <MenuItem value="BANK">{t('sweep2.bank')}</MenuItem>
              <MenuItem value="CARD">{t('sweep2.card')}</MenuItem>
              <MenuItem value="CHEQUE">{t('sweep2.cheque')}</MenuItem>
            </TextField>
            {payMode === 'CHEQUE' ? <ChequePaymentFields value={payCheque} onChange={setPayCheque} /> : null}
            <TextField
              label={t('purchaseDetail.paymentDate')}
              type="date"
              value={payDate}
              onChange={(e) => setPayDate(e.target.value)}
              InputLabelProps={{ shrink: true }}
              fullWidth
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPayOpen(false)}>{t('common.cancel')}</Button>
          <Button variant="contained" disabled={recordPaymentMutation.isPending} onClick={submitPayment}>
            {t('purchaseDetail.recordSave')}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
