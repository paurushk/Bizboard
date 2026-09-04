import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Divider from '@mui/material/Divider';
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
import { Link as RouterLink, useLocation, useParams, useSearchParams } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import {
  amendInvoiceFilingIdentity,
  cancelSalesInvoice,
  completeSalesInvoice,
  createPaymentLink,
  cancelPaymentLink,
  downloadInvoicePdf,
  downloadInvoiceThermalPdf,
  getCustomer,
  getInvoiceAudit,
  getSalesInvoice,
  getUpiQr,
  listAllocationsPage,
  listPaymentLinksPage,
  shareInvoice,
  sharePaymentLink,
  unallocatePayment,
  updateSalesInvoice,
} from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { EinvoiceEwayPanel } from '@/components/EinvoiceEwayPanel';
import { safePaymentHref } from '@/utils/safeUrl';
import { DetailSkeleton, EmptyState, ErrorState } from '@/components/PageState';
import { PdfStatusPoller } from '@/components/PdfStatusPoller';
import { StatusChip } from '@/components/StatusChip';
import { isRuntimeFlagEnabled } from '@/config/featureFlags';
import { t } from '@/i18n';
import { printBlob, triggerBlobDownload } from '@/utils/blob';
import { completeWithConfirms } from '@/utils/completeWithConfirms';
import { formatMoney, toNumber } from '@/utils/money';
import { canCancelDocuments, canCreateSales, canViewFinancialReports } from '@/utils/permissions';
import { isAllowedPaymentUrl, isAllowedShareUrl, openShareUrl } from '@/utils/safeUrl';
import { documentStatusTone, paidAwareStatus, statusLabelKey } from '@/utils/status';

export function InvoiceDetailPage() {
  const { user } = useAuth();
  const { id } = useParams();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const invoiceId = Number(id);
  const invoiceIdValid = Number.isFinite(invoiceId) && invoiceId > 0;
  const qc = useQueryClient();
  const [sharePhone, setSharePhone] = useState('');
  const [shareEmail, setShareEmail] = useState('');
  const [prefilled, setPrefilled] = useState(false);
  const [amendOpen, setAmendOpen] = useState(false);
  const [amendGstin, setAmendGstin] = useState('');
  const [amendPos, setAmendPos] = useState('');
  const [amendReason, setAmendReason] = useState('');
  const [vehicleNumber, setVehicleNumber] = useState('');
  const [transporterName, setTransporterName] = useState('');
  const [transporterId, setTransporterId] = useState('');
  const [transportDistanceKm, setTransportDistanceKm] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(
    () => (location.state as { paymentWarning?: string } | null)?.paymentWarning ?? null,
  );
  const [errorSource, setErrorSource] = useState<unknown>(null);
  const cancelBtnRef = useRef<HTMLButtonElement>(null);
  const helpCancel = searchParams.get('helpAction') === 'cancel';

  const captureError = (err: unknown) => {
    setError(getErrorMessage(err));
    setErrorSource(err);
  };

  const query = useQuery({
    queryKey: ['sales-invoice', invoiceId],
    queryFn: () => getSalesInvoice(invoiceId),
    enabled: invoiceIdValid,
  });

  // F2-025: fetch the single customer this invoice belongs to by id
  // instead of paging through the entire customer list just to find it.
  const customerId = query.data?.customer;
  const customerQuery = useQuery({
    queryKey: ['customer', customerId],
    queryFn: () => getCustomer(customerId as number),
    enabled: !!customerId,
  });

  const showAudit = canViewFinancialReports(user);
  const auditQuery = useQuery({
    queryKey: ['sales-invoice-audit', invoiceId],
    queryFn: () => getInvoiceAudit(invoiceId),
    enabled: invoiceIdValid && showAudit,
  });

  useEffect(() => {
    if (!query.data) return;
    setVehicleNumber(query.data.vehicleNumber ?? '');
    setTransporterName(query.data.transporterName ?? '');
    setTransporterId(query.data.transporterId ?? '');
    setTransportDistanceKm(String(query.data.transportDistanceKm ?? ''));
    setAmendGstin(query.data.filingPartyGstin ?? '');
    setAmendPos(query.data.filingPlaceOfSupply ?? '');
  }, [query.data]);

  useEffect(() => {
    if (!helpCancel) return;
    cancelBtnRef.current?.focus();
    cancelBtnRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, [helpCancel, query.data?.status]);

  useEffect(() => {
    if (prefilled || !query.data) return;
    const fromOffer = query.data.whatsappOffer?.phone?.trim();
    const customer = customerQuery.data;
    if (fromOffer) setSharePhone(fromOffer);
    else if (customer?.phone) setSharePhone(customer.phone);
    if (customer?.email) setShareEmail(customer.email);
    if (fromOffer || customer || customerQuery.isFetched) setPrefilled(true);
  }, [query.data, customerQuery.data, customerQuery.isFetched, prefilled]);

  const completeMutation = useMutation({
    // F2-035: completeWithConfirms loops over known confirm codes in any
    // order — the hand-nested try/catch here only recovered
    // place_of_supply_unresolved -> GSTIN_TOTAL_CHANGED in that exact order.
    mutationFn: () => completeWithConfirms((extra) => completeSalesInvoice(invoiceId, extra)),
    onSuccess: (data) => {
      const warns = (data?.warnings ?? []).filter(Boolean).join(' ');
      setMessage(warns ? `${t('billing.invoiceCompleted')} ${warns}` : t('billing.invoiceCompleted'));
      void qc.invalidateQueries({ queryKey: ['sales-invoice', invoiceId] });
    },
    onError: (err) => captureError(err),
  });

  const cancelMutation = useMutation({
    mutationFn: () => cancelSalesInvoice(invoiceId),
    onSuccess: () => {
      setMessage(t('billing.invoiceCancelled'));
      void qc.invalidateQueries({ queryKey: ['sales-invoice', invoiceId] });
    },
    onError: (err) => captureError(err),
  });

  const [shareLink, setShareLink] = useState<string | null>(null);
  const [upiQr, setUpiQr] = useState<Record<string, string> | null>(null);
  const [upiError, setUpiError] = useState<string | null>(null);
  const [payLinkMsg, setPayLinkMsg] = useState<string | null>(null);
  const [linkSharePhone, setLinkSharePhone] = useState('');
  const [linkShareEmail, setLinkShareEmail] = useState('');

  const paymentLinks = useQuery({
    queryKey: ['payment-links', invoiceId],
    queryFn: async () => {
      const page = await listPaymentLinksPage({ pageSize: 50, sales_invoice: invoiceId });
      return page.results;
    },
    enabled: Number.isFinite(invoiceId) && (query.data?.status === 'COMPLETED' || query.data?.status === 'RETURNED'),
  });

  const allocations = useQuery({
    queryKey: ['invoice-allocations', invoiceId],
    queryFn: () => listAllocationsPage({ sales_invoice: invoiceId, pageSize: 50 }),
    enabled: Number.isFinite(invoiceId) && (query.data?.status === 'COMPLETED' || query.data?.status === 'RETURNED'),
  });

  const unallocateMutation = useMutation({
    mutationFn: (allocationId: number) => unallocatePayment(allocationId),
    onSuccess: () => {
      setMessage(t('billing.paymentUnallocated'));
      void qc.invalidateQueries({ queryKey: ['sales-invoice', invoiceId] });
      void qc.invalidateQueries({ queryKey: ['invoice-allocations', invoiceId] });
    },
    onError: (err) => captureError(err),
  });

  const transportForPanel = useMemo(
    () => ({
      vehicleNumber,
      transporterName,
      transporterId,
      transportDistanceKm,
    }),
    [vehicleNumber, transporterName, transporterId, transportDistanceKm],
  );

  const upiMutation = useMutation({
    mutationFn: () => getUpiQr({ salesInvoice: invoiceId }),
    onSuccess: (data) => {
      setUpiQr(data);
      setUpiError(null);
    },
    onError: (err) => setUpiError(getErrorMessage(err)),
  });

  const createLinkMutation = useMutation({
    mutationFn: () =>
      createPaymentLink({
        salesInvoice: invoiceId,
        customer: query.data?.customer,
      }),
    onSuccess: () => {
      setPayLinkMsg('Payment link created');
      void qc.invalidateQueries({ queryKey: ['payment-links', invoiceId] });
    },
    onError: (err) => setPayLinkMsg(getErrorMessage(err)),
  });

  const cancelLinkMutation = useMutation({
    mutationFn: (id: number) => cancelPaymentLink(id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['payment-links', invoiceId] }),
    onError: (err) => setPayLinkMsg(getErrorMessage(err)),
  });

  const shareLinkMutation = useMutation({
    mutationFn: (payload: { id: number; channel: 'EMAIL' | 'WHATSAPP'; recipient: string }) =>
      sharePaymentLink(payload.id, { channel: payload.channel, recipient: payload.recipient }),
    onSuccess: (res) => {
      setPayLinkMsg('Payment link shared');
      if (res.shareLink) {
        try {
          openShareUrl(String(res.shareLink));
        } catch {
          setPayLinkMsg('Payment link shared (blocked unsafe URL)');
        }
      }
      void qc.invalidateQueries({ queryKey: ['payment-links', invoiceId] });
    },
    onError: (err) => setPayLinkMsg(getErrorMessage(err)),
  });

  const shareMutation = useMutation({
    mutationFn: (payload: { channel: 'EMAIL' | 'WHATSAPP'; recipient: string }) =>
      shareInvoice(invoiceId, payload),
    onSuccess: (res, variables) => {
      setShareLink(res.shareLink ?? null);
      if (variables.channel === 'WHATSAPP') {
        const mode = res.mode ?? (res.status === 'SENT' ? 'cloud' : 'link');
        if (mode === 'cloud' && res.status === 'SENT') {
          setMessage(t('common.whatsappCloudSent'));
          setError(null);
          setErrorSource(null);
        } else if (res.error) {
          // BB-000743: Cloud attempted but fell back to wa.me — never silent.
          setError(res.error || t('common.whatsappFallbackWarn'));
          setMessage(t('common.whatsappFallbackWarn'));
        } else {
          setMessage(t('common.whatsappLinkHint'));
          setError(null);
          setErrorSource(null);
        }
      } else {
        setMessage(res.shareLink ? `Share ready` : `Share ${res.status}`);
      }
      // BUG-519: window.open here is frequently blocked by popup blockers
      // since it fires from an async callback, not directly from the click;
      // the link is also rendered as a clickable fallback below.
      if (res.shareLink) {
        const mode =
          variables.channel === 'WHATSAPP'
            ? (res.mode ?? (res.status === 'SENT' ? 'cloud' : 'link'))
            : 'link';
        if (mode !== 'cloud') {
          try {
            openShareUrl(res.shareLink);
          } catch {
            setMessage('Share ready (blocked unsafe URL)');
          }
        }
      }
      void qc.invalidateQueries({ queryKey: ['sales-invoice', invoiceId] });
    },
    onError: (err) => captureError(err),
  });

  const whatsappButtonHint = query.data?.whatsappOffer && !query.data.whatsappOffer.optIn
    ? t('common.whatsappOptInOffHint')
    : isRuntimeFlagEnabled('ENABLE_WHATSAPP_CLOUD')
      ? t('common.whatsapp')
      : t('common.whatsappLinkHint');

  // F2-036: this calls the same updateSalesInvoice endpoint NewInvoicePage
  // uses for an amend (which on a COMPLETED doc requires Owner +
  // confirmAmend), but with none of that guard — it works today only
  // because the backend treats vehicle/transporter fields as non-amending.
  // Not user-visible, but if that backend allowlist ever changes this call
  // needs its own confirmAmend wiring or a dedicated transport-update route.
  const transportMutation = useMutation({
    mutationFn: () =>
      updateSalesInvoice(invoiceId, {
        vehicleNumber: vehicleNumber.trim(),
        transporterName: transporterName.trim(),
        transporterId: transporterId.trim(),
        transportDistanceKm: transportDistanceKm.trim() || null,
      }),
    onSuccess: () => {
      setMessage('Transport details saved');
      void qc.invalidateQueries({ queryKey: ['sales-invoice', invoiceId] });
    },
    onError: (err) => captureError(err),
  });

  const amendMutation = useMutation({
    mutationFn: () =>
      amendInvoiceFilingIdentity(invoiceId, {
        filingPartyGstin: amendGstin.trim() || undefined,
        filingPlaceOfSupply: amendPos.trim() || undefined,
        reason: amendReason.trim(),
      }),
    onSuccess: () => {
      setMessage(t('einvoice.filingIdentityAmended'));
      setAmendOpen(false);
      setAmendReason('');
      void qc.invalidateQueries({ queryKey: ['sales-invoice', invoiceId] });
    },
    onError: (err) => captureError(err),
  });

  const downloadCopy = useCallback(
    async (copy: 'ORIGINAL' | 'DUPLICATE') => {
      try {
        const blob = await downloadInvoicePdf(invoiceId, { copy });
        const base = query.data?.number ?? `invoice-${invoiceId}`;
        triggerBlobDownload(blob, `${base}_${copy.toLowerCase()}.pdf`);
      } catch (err) {
        setError(getErrorMessage(err));
        setErrorSource(err);
      }
    },
    [invoiceId, query.data?.number],
  );

  const handlePrint = useCallback(async () => {
    try {
      const blob = await downloadInvoicePdf(invoiceId, { copy: 'ORIGINAL' });
      printBlob(blob);
    } catch (err) {
      setError(getErrorMessage(err));
      setErrorSource(err);
    }
  }, [invoiceId]);

  const handleThermalPrint = useCallback(
    async (width: 80 | 58) => {
      try {
        const blob = await downloadInvoiceThermalPdf(invoiceId, width);
        printBlob(blob);
      } catch (err) {
        setError(getErrorMessage(err));
        setErrorSource(err);
      }
    },
    [invoiceId],
  );

  if (!invoiceIdValid) {
    return <ErrorState message={t('billing.invalidInvoice')} />;
  }
  if (query.isLoading) return <DetailSkeleton />;
  if (query.isError) {
    return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  }
  if (!query.data) return <EmptyState />;

  const inv = query.data;
  const canAct = inv.status === 'COMPLETED' || inv.status === 'RETURNED';
  const showTax = inv.invoiceType === 'GST' || inv.invoiceType === 'TAX' || inv.invoiceType === 'RETAIL';
  const showEinvoicePanel =
    canAct && (inv.invoiceType === 'GST' || inv.invoiceType === 'TAX');
  const isOwner = user?.role === 'OWNER';
  const activeAllocations = (allocations.data?.results ?? []).filter((row) => !row.reversedAt);

  return (
    <Stack spacing={2}>
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        justifyContent="space-between"
        alignItems={{ xs: 'stretch', sm: 'flex-start' }}
        spacing={1}
      >
        <Box>
          <Typography variant="h4">
            {inv.number?.trim() ? inv.number : `Draft #${inv.id}`}
          </Typography>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 0.5, flexWrap: 'wrap' }}>
            <StatusChip
              tone={documentStatusTone(paidAwareStatus(inv.status, inv.balance, inv.paymentState))}
              labelKey={statusLabelKey(paidAwareStatus(inv.status, inv.balance, inv.paymentState))}
            />
            <Chip size="small" label={inv.invoiceType} variant="outlined" />
            <Typography variant="body2" color="text.secondary">
              {inv.invoiceDate}
            </Typography>
          </Stack>
          <Typography sx={{ mt: 1 }}>{inv.customerName}</Typography>
        </Box>
        <Button component={RouterLink} to="/sales/history">
          {t('common.back')}
        </Button>
      </Stack>

      {message ? (
        <Alert severity="success" role="status" aria-live="polite">
          {message}
        </Alert>
      ) : null}
      {error ? (
        <HelpErrorAlert message={error} error={errorSource} invoiceId={invoiceId} />
      ) : null}

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
          {inv.status === 'DRAFT' || inv.status === 'COMPLETED' ? (
            <Button
              component={RouterLink}
              to={`/sales/history/${inv.id}/edit`}
              variant="outlined"
            >
              {t('common.edit')}
            </Button>
          ) : null}
          {inv.status === 'DRAFT' && canCreateSales(user) ? (
            <Button
              variant="contained"
              disabled={completeMutation.isPending}
              onClick={() => completeMutation.mutate()}
            >
              {t('common.complete')}
            </Button>
          ) : null}
          {inv.status === 'COMPLETED' && canCancelDocuments(user) ? (
            <Button
              ref={cancelBtnRef}
              id="invoice-cancel"
              color="error"
              variant={helpCancel ? 'contained' : 'outlined'}
              disabled={cancelMutation.isPending}
              onClick={() => {
                // BUG-520: a single mis-click used to cancel a completed,
                // potentially already-shared GST invoice with no recovery.
                if (window.confirm(t('history.confirmCancel', { label: inv.number ?? inv.id }))) {
                  cancelMutation.mutate();
                }
              }}
            >
              {t('common.cancel')}
            </Button>
          ) : null}
          {canAct ? (
            <>
              <Button variant="outlined" onClick={() => void downloadCopy('ORIGINAL')}>
                {t('billing.downloadOriginal')}
              </Button>
              <Button variant="outlined" onClick={() => void downloadCopy('DUPLICATE')}>
                {t('billing.downloadDuplicate')}
              </Button>
              <Button variant="outlined" onClick={() => void handlePrint()}>
                {t('billing.print')}
              </Button>
              <Button variant="outlined" onClick={() => void handleThermalPrint(80)}>
                Print receipt (80mm)
              </Button>
              <Button variant="outlined" onClick={() => void handleThermalPrint(58)}>
                Print receipt (58mm)
              </Button>
            </>
          ) : null}
        </Stack>
      </Paper>

      {inv.status === 'COMPLETED' || inv.status === 'RETURNED' ? (
        <PdfStatusPoller invoiceId={inv.id} filenameBase={inv.number ?? undefined} />
      ) : null}

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
            <Stack direction="row" justifyContent="space-between">
              <Typography>{t('billing.received')}</Typography>
              <Typography>{formatMoney(inv.received ?? 0)}</Typography>
            </Stack>
            <Stack direction="row" justifyContent="space-between">
              <Typography>{t('billing.balance')}</Typography>
              <Typography fontWeight={600}>{formatMoney(inv.balance ?? inv.grandTotal)}</Typography>
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
              <Typography>Taxable</Typography>
              <Typography>{formatMoney(inv.taxableTotal)}</Typography>
            </Stack>
            {showTax ? (
              <>
                <Stack direction="row" justifyContent="space-between">
                  <Typography>CGST</Typography>
                  <Typography>{formatMoney(inv.cgstTotal)}</Typography>
                </Stack>
                <Stack direction="row" justifyContent="space-between">
                  <Typography>SGST</Typography>
                  <Typography>{formatMoney(inv.sgstTotal)}</Typography>
                </Stack>
                <Stack direction="row" justifyContent="space-between">
                  <Typography>IGST</Typography>
                  <Typography>{formatMoney(inv.igstTotal)}</Typography>
                </Stack>
              </>
            ) : null}
          </Stack>
        </Paper>
      </Stack>

      {canAct ? (
        <Paper sx={{ p: 2 }}>
          <Typography variant="subtitle2" color="text.secondary">
            Allocations
          </Typography>
          <Divider sx={{ my: 1 }} />
          {activeAllocations.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              No active allocations on this invoice.
            </Typography>
          ) : (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Receipt</TableCell>
                  <TableCell align="right">Amount</TableCell>
                  <TableCell align="right" />
                </TableRow>
              </TableHead>
              <TableBody>
                {activeAllocations.map((row) => (
                  <TableRow key={row.id}>
                    <TableCell>#{row.receipt ?? '—'}</TableCell>
                    <TableCell align="right">{formatMoney(row.amount)}</TableCell>
                    <TableCell align="right">
                      {canCancelDocuments(user) ? (
                        <Button
                          size="small"
                          color="warning"
                          disabled={unallocateMutation.isPending}
                          onClick={() => {
                            if (window.confirm(t('billing.confirmUnallocate'))) {
                              unallocateMutation.mutate(row.id);
                            }
                          }}
                        >
                          Unallocate
                        </Button>
                      ) : null}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Paper>
      ) : null}

      {canAct && toNumber(inv.balance ?? inv.grandTotal) > 0 ? (
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
          <Paper sx={{ p: 2, flex: 1 }}>
            <Typography variant="h6" sx={{ mb: 1 }}>
              UPI collect
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
              Amount-locked QR for outstanding {formatMoney(inv.balance ?? inv.grandTotal)}.
            </Typography>
            {upiError ? <HelpErrorAlert message={upiError} sx={{ mb: 1 }} /> : null}
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 1.5 }}>
              <Button
                variant="contained"
                size="small"
                disabled={upiMutation.isPending}
                onClick={() => upiMutation.mutate()}
              >
                Generate UPI QR
              </Button>
              {upiQr?.intentUrl && isAllowedPaymentUrl(String(upiQr.intentUrl)) ? (
                <Button
                  size="small"
                  variant="outlined"
                  onClick={() => {
                    void navigator.clipboard.writeText(String(upiQr.intentUrl));
                    setMessage('UPI intent copied');
                  }}
                >
                  Copy intent link
                </Button>
              ) : null}
            </Stack>
            {upiQr?.intentUrl && isAllowedPaymentUrl(String(upiQr.intentUrl)) ? (
              <Stack spacing={1}>
                <Typography variant="body2" sx={{ fontFamily: 'monospace', wordBreak: 'break-all' }}>
                  {String(upiQr.intentUrl)}
                </Typography>
                {upiQr.qrPngBase64 || upiQr.qr_png_base64 ? (
                  <Box
                    component="img"
                    alt="UPI QR"
                    src={`data:image/png;base64,${upiQr.qrPngBase64 || upiQr.qr_png_base64}`}
                    sx={{ width: 180, height: 180, border: 1, borderColor: 'divider' }}
                  />
                ) : null}
                <Typography variant="caption" color="text.secondary">
                  Amount locked: {String(upiQr.amount ?? upiQr.amountLocked ?? inv.balance)}
                </Typography>
              </Stack>
            ) : null}
          </Paper>
          <Paper sx={{ p: 2, flex: 1 }}>
            <Typography variant="h6" sx={{ mb: 1 }}>
              Payment link
            </Typography>
            {payLinkMsg ? (
              <Alert severity={payLinkMsg.toLowerCase().includes('created') || payLinkMsg.toLowerCase().includes('shared') ? 'success' : 'error'} sx={{ mb: 1 }}>
                {payLinkMsg}
              </Alert>
            ) : null}
            <Button
              variant="contained"
              size="small"
              disabled={createLinkMutation.isPending}
              onClick={() => createLinkMutation.mutate()}
              sx={{ mb: 1.5 }}
            >
              Create payment link
            </Button>
            <Stack spacing={1.5}>
              {(paymentLinks.data ?? []).map((link) => (
                <Box key={link.id} sx={{ border: 1, borderColor: 'divider', borderRadius: 1, p: 1.5 }}>
                  <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                    <Chip size="small" label={link.status} color={link.status === 'PAID' ? 'success' : 'default'} />
                    <Typography variant="body2">{formatMoney(link.amount)}</Typography>
                    {(() => {
                      const href =
                        safePaymentHref(String(link.providerShortUrl || ''))
                        || safePaymentHref(link.publicPath || `/pay/${link.token}`);
                      return href ? (
                        <Button size="small" href={href} target="_blank" rel="noreferrer">
                          Open
                        </Button>
                      ) : null;
                    })()}
                    {link.status !== 'CANCELLED' && link.status !== 'PAID' && link.status !== 'EXPIRED' ? (
                      <Button
                        size="small"
                        color="error"
                        disabled={cancelLinkMutation.isPending}
                        onClick={() => cancelLinkMutation.mutate(link.id)}
                      >
                        Cancel
                      </Button>
                    ) : null}
                  </Stack>
                  {link.status === 'CREATED' || link.status === 'SENT' ? (
                    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ mt: 1 }}>
                      <TextField
                        size="small"
                        label={t('common.whatsapp')}
                        value={linkSharePhone}
                        onChange={(e) => setLinkSharePhone(e.target.value)}
                      />
                      <Button
                        size="small"
                        variant="outlined"
                        disabled={!linkSharePhone.trim() || shareLinkMutation.isPending}
                        onClick={() =>
                          shareLinkMutation.mutate({
                            id: link.id,
                            channel: 'WHATSAPP',
                            recipient: linkSharePhone,
                          })
                        }
                      >
                        {t('common.whatsapp')}
                      </Button>
                      <TextField
                        size="small"
                        label="Email"
                        value={linkShareEmail}
                        onChange={(e) => setLinkShareEmail(e.target.value)}
                      />
                      <Button
                        size="small"
                        variant="outlined"
                        disabled={!linkShareEmail.trim() || shareLinkMutation.isPending}
                        onClick={() =>
                          shareLinkMutation.mutate({
                            id: link.id,
                            channel: 'EMAIL',
                            recipient: linkShareEmail,
                          })
                        }
                      >
                        Send email
                      </Button>
                    </Stack>
                  ) : null}
                </Box>
              ))}
              {!paymentLinks.data?.length ? (
                <Typography variant="body2" color="text.secondary">
                  No links yet for this invoice.
                </Typography>
              ) : null}
            </Stack>
          </Paper>
        </Stack>
      ) : null}

      <Paper sx={{ overflow: 'auto' }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>#</TableCell>
              <TableCell>{t('nav.products')}</TableCell>
              <TableCell>HSN</TableCell>
              <TableCell align="right">{t('billing.qty')}</TableCell>
              {showTax ? <TableCell align="right">MRP</TableCell> : null}
              <TableCell align="right">{t('billing.price')}</TableCell>
              {showTax ? <TableCell align="right">{t('billing.tax')}</TableCell> : null}
              <TableCell align="right">{t('common.total')}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {(inv.items ?? []).map((item, idx) => {
              const lineTax =
                toNumber(item.cgst) + toNumber(item.sgst) + toNumber(item.igst);
              return (
                <TableRow key={item.id ?? `${item.product}-${item.quantity}`}>
                  <TableCell>{idx + 1}</TableCell>
                  <TableCell>
                    {item.productName ?? item.description ?? item.product}
                    {item.appliedPriceListName ? (
                      <Typography component="span" variant="caption" color="text.secondary">
                        {` · List: ${item.appliedPriceListName}`}
                      </Typography>
                    ) : null}
                    {item.unitName ? (
                      <Typography component="span" variant="caption" color="text.secondary">
                        {` · ${item.unitName}`}
                      </Typography>
                    ) : null}
                  </TableCell>
                  <TableCell>{item.hsnCode || '—'}</TableCell>
                  <TableCell align="right">{toNumber(item.quantity)}</TableCell>
                  {showTax ? (
                    <TableCell align="right">{formatMoney(item.mrp ?? 0)}</TableCell>
                  ) : null}
                  <TableCell align="right">{formatMoney(item.unitPrice)}</TableCell>
                  {showTax ? (
                    <TableCell align="right">
                      {formatMoney(lineTax)}
                      <Typography variant="caption" display="block" color="text.secondary">
                        ({toNumber(item.gstRate)}%)
                      </Typography>
                    </TableCell>
                  ) : null}
                  <TableCell align="right">{formatMoney(item.lineTotal)}</TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </Paper>

      {showEinvoicePanel ? (
        <>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" sx={{ mb: 1.5 }}>
              Transport (e-Way)
            </Typography>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ mb: 1.5 }}>
              <TextField
                label="Vehicle no"
                size="small"
                value={vehicleNumber}
                onChange={(e) => setVehicleNumber(e.target.value)}
                fullWidth
              />
              <TextField
                label="Transporter name"
                size="small"
                value={transporterName}
                onChange={(e) => setTransporterName(e.target.value)}
                fullWidth
              />
              <TextField
                label="Transporter ID"
                size="small"
                value={transporterId}
                onChange={(e) => setTransporterId(e.target.value)}
                fullWidth
              />
              <TextField
                label="Distance (km)"
                size="small"
                value={transportDistanceKm}
                onChange={(e) => setTransportDistanceKm(e.target.value)}
                fullWidth
              />
            </Stack>
            <Button
              variant="outlined"
              size="small"
              disabled={transportMutation.isPending}
              onClick={() => transportMutation.mutate()}
            >
              Save transport
            </Button>
          </Paper>
          <EinvoiceEwayPanel
            invoice={inv}
            onError={setError}
            onMessage={setMessage}
            transport={transportForPanel}
          />
        </>
      ) : null}

      {canAct && isOwner && inv.status === 'COMPLETED' ? (
        <Paper sx={{ p: 2 }}>
          <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
            <Typography variant="h6">{t('einvoice.filingIdentity')}</Typography>
            <Button variant="outlined" size="small" onClick={() => setAmendOpen(true)}>
              {t('einvoice.amendFilingIdentity')}
            </Button>
          </Stack>
          <Stack spacing={0.5}>
            <Typography variant="body2">
              Filing party GSTIN: {inv.filingPartyGstin?.trim() || '—'}
            </Typography>
            <Typography variant="body2">
              Place of supply: {inv.filingPlaceOfSupply?.trim() || '—'}
            </Typography>
          </Stack>
        </Paper>
      ) : null}

      {canAct ? (
        <Paper sx={{ p: 2 }}>
          <Typography variant="h6" sx={{ mb: 2 }}>
            {t('common.share')}
          </Typography>
          {inv.whatsappSendStatus && inv.whatsappSendStatus !== 'NONE' ? (
            <Chip
              size="small"
              color={
                inv.whatsappSendStatus === 'SENT'
                  ? 'success'
                  : inv.whatsappSendStatus === 'FAILED'
                    ? 'error'
                    : 'default'
              }
              label={
                inv.whatsappSendStatus === 'SENT'
                  ? t('common.whatsappStatusSent')
                  : inv.whatsappSendStatus === 'FAILED'
                    ? t('common.whatsappStatusFailed')
                    : t('common.whatsappStatusFallback')
              }
              sx={{ mb: 1 }}
            />
          ) : null}
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            {whatsappButtonHint}
          </Typography>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <TextField
              label={t('common.whatsapp')}
              value={sharePhone}
              onChange={(e) => setSharePhone(e.target.value)}
              placeholder="9198XXXXXXXX"
              helperText={
                isRuntimeFlagEnabled('ENABLE_WHATSAPP_CLOUD')
                  ? undefined
                  : t('common.whatsappLinkHint')
              }
              error={Boolean(sharePhone) && !/^\d{10,15}$/.test(sharePhone.replace(/\D/g, ''))}
            />
            <Button
              variant="outlined"
              disabled={
                !/^\d{10,15}$/.test(sharePhone.replace(/\D/g, '')) || shareMutation.isPending
              }
              onClick={() =>
                shareMutation.mutate({ channel: 'WHATSAPP', recipient: sharePhone })
              }
            >
              {t('common.whatsappSendInvoice')}
            </Button>
            <TextField
              label={t('common.email')}
              value={shareEmail}
              onChange={(e) => setShareEmail(e.target.value)}
              error={Boolean(shareEmail) && !/^\S+@\S+\.\S+$/.test(shareEmail)}
            />
            <Button
              variant="outlined"
              disabled={!/^\S+@\S+\.\S+$/.test(shareEmail) || shareMutation.isPending}
              onClick={() => shareMutation.mutate({ channel: 'EMAIL', recipient: shareEmail })}
            >
              {t('common.email')}
            </Button>
          </Stack>
          {shareLink && isAllowedShareUrl(shareLink) ? (
            <Typography variant="body2" sx={{ mt: 1 }}>
              {/* BUG-519: a popup-blocked window.open left users with no way
                  to recover the link — it's now always shown as clickable. */}
              <a href={shareLink} target="_blank" rel="noopener noreferrer">
                {shareLink}
              </a>
            </Typography>
          ) : null}
        </Paper>
      ) : null}

      <Dialog open={amendOpen} onClose={() => setAmendOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{t('einvoice.amendFilingIdentity')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Filing party GSTIN"
              value={amendGstin}
              onChange={(e) => setAmendGstin(e.target.value)}
              helperText={`Current: ${inv.filingPartyGstin?.trim() || '—'}`}
            />
            <TextField
              label="Place of supply (state code)"
              value={amendPos}
              onChange={(e) => setAmendPos(e.target.value)}
              helperText={`Current: ${inv.filingPlaceOfSupply?.trim() || '—'}`}
            />
            <TextField
              label="Reason"
              required
              multiline
              minRows={2}
              value={amendReason}
              onChange={(e) => setAmendReason(e.target.value)}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAmendOpen(false)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={!amendReason.trim() || amendMutation.isPending}
            onClick={() => amendMutation.mutate()}
          >
            Save amendment
          </Button>
        </DialogActions>
      </Dialog>
      {showAudit ? (
        <Paper sx={{ p: 2 }}>
          <Typography variant="h6" fontWeight={600} gutterBottom>
            {t('billing.auditTrail')}
          </Typography>
          {auditQuery.isLoading ? (
            <Typography color="text.secondary">{t('common.loading')}</Typography>
          ) : (auditQuery.data ?? []).length === 0 ? (
            <Typography color="text.secondary">{t('billing.auditEmpty')}</Typography>
          ) : (
            <Stack spacing={1.5}>
              {(auditQuery.data ?? []).map((ev) => {
                const before = (ev.metadata?.before ?? {}) as Record<string, unknown>;
                const after = (ev.metadata?.after ?? {}) as Record<string, unknown>;
                const moneyKeys = ['grand_total', 'grandTotal', 'cgst_total', 'cgstTotal', 'sgst_total', 'sgstTotal', 'igst_total', 'igstTotal'];
                const diffs = moneyKeys.filter((k) => before[k] != null || after[k] != null);
                return (
                  <Box key={ev.id}>
                    <Typography variant="body2">
                      {ev.userName || ev.userEmail || t('common.unknownUser')} · {ev.action} · {new Date(ev.createdAt).toLocaleString()}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {ev.description}
                    </Typography>
                    {diffs.length ? (
                      <Typography variant="caption" display="block">
                        {diffs.map((k) => `${k}: ${String(before[k] ?? '—')} → ${String(after[k] ?? '—')}`).join(' · ')}
                      </Typography>
                    ) : null}
                  </Box>
                );
              })}
            </Stack>
          )}
        </Paper>
      ) : null}
    </Stack>
  );
}
