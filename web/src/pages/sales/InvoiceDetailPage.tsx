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
import Menu from '@mui/material/Menu';
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
import { Link as RouterLink, useLocation, useParams, useSearchParams } from 'react-router-dom';
import { getErrorCode, getErrorMessage } from '@/api/client';
import { PageTitle } from '@/contextHelp';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { invalidateInvoiceSideEffects } from '@/pages/sales/invalidateInvoiceSideEffects';
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
  getInvoiceHsnSummary,
  getInvoiceProfitReport,
  getSalesInvoice,
  getUpiQr,
  listAllocationsPage,
  listPaymentLinksPage,
  listPaymentPromises,
  createPaymentPromise,
  resolvePaymentPromise,
  listSalesReturns,
  sharePaymentLink,
  unallocatePayment,
  updateSalesInvoice,
} from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { EinvoiceEwayPanel } from '@/components/EinvoiceEwayPanel';
import { InvoicePostedActionBar } from '@/components/InvoicePostedActionBar';
import { ProfitDetailsDialog } from '@/components/ProfitDetailsDialog';
import { RecordInvoicePaymentDialog } from '@/components/RecordInvoicePaymentDialog';
import { ShareInvoiceDialog, type ShareChannel } from '@/components/ShareInvoiceDialog';
import { primaryPostedAction } from '@/cognitive/loadHelpers';
import { safePaymentHref } from '@/utils/safeUrl';
import { DetailSkeleton, EmptyState, ErrorState } from '@/components/PageState';
import { PdfStatusPoller } from '@/components/PdfStatusPoller';
import { SourceQuotationsPanel } from '@/components/SourceQuotationsPanel';
import { StatusChip } from '@/components/StatusChip';
import { isRuntimeFlagEnabled } from '@/config/featureFlags';
import { t, useLocale } from '@/i18n';
import { printBlob, triggerBlobDownload } from '@/utils/blob';
import { completeWithConfirms } from '@/utils/completeWithConfirms';
import { todayIso } from '@/components/billing/lineHelpers';
import { formatMoney, toNumber } from '@/utils/money';
import {
  canCancelDocuments,
  canCreatePayments,
  canCreateSales,
  canManagePaymentPromises,
  canOverrideGstGuard,
  canViewFinancialReports,
} from '@/utils/permissions';
import { isAllowedPaymentUrl, isAllowedShareUrl, openShareUrl } from '@/utils/safeUrl';
import { documentStatusTone, invoiceDisplayStatus, statusLabelKey } from '@/utils/status';
import { canEditInvoiceLines, hasLiveIrn } from '@/utils/einvoiceLock';

function defaultPromiseDate(): string {
  const d = new Date();
  d.setDate(d.getDate() + 3);
  return todayIso(d);
}

export function InvoiceDetailPage() {
  useLocale();
  const { user } = useAuth();
  const { id } = useParams();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const invoiceId = Number(id);
  const invoiceIdValid = Number.isFinite(invoiceId) && invoiceId > 0;
  const qc = useQueryClient();
  const [shareOpen, setShareOpen] = useState(false);
  const [shareChannel, setShareChannel] = useState<ShareChannel>('WHATSAPP');
  const [profitOpen, setProfitOpen] = useState(false);
  const [payOpen, setPayOpen] = useState(false);
  const [moreAnchor, setMoreAnchor] = useState<HTMLElement | null>(null);
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
  const [gstGuardIssues, setGstGuardIssues] = useState<{ code: string; message: string }[] | null>(
    null,
  );
  const [gstGuardWarnings, setGstGuardWarnings] = useState<
    { code: string; message: string }[] | null
  >(null);
  const [gstGuardOverrideReason, setGstGuardOverrideReason] = useState('');
  const belowCostReason = useRef('');
  const [promiseOpen, setPromiseOpen] = useState(false);
  const [promiseDate, setPromiseDate] = useState(() => defaultPromiseDate());
  const [promiseNote, setPromiseNote] = useState('');
  const [promiseAmount, setPromiseAmount] = useState('');
  const cancelBtnRef = useRef<HTMLLIElement>(null);
  const moreBtnRef = useRef<HTMLButtonElement>(null);
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
  const hsnQuery = useQuery({
    queryKey: ['sales-invoice-hsn', invoiceId],
    queryFn: () => getInvoiceHsnSummary(invoiceId),
    enabled: invoiceIdValid,
  });
  const profitQuery = useQuery({
    queryKey: ['sales-invoice-profit', invoiceId, query.data?.invoiceDate],
    queryFn: () =>
      getInvoiceProfitReport({
        date_from: query.data!.invoiceDate,
        date_to: query.data!.invoiceDate,
      }),
    enabled: invoiceIdValid && showAudit && Boolean(query.data?.invoiceDate),
  });

  // Copy the loaded invoice into the editable transport and filing fields each time it refreshes.
  const [seenInvoice, setSeenInvoice] = useState<typeof query.data>(undefined);
  if (query.data && query.data !== seenInvoice) {
    setSeenInvoice(query.data);
    setVehicleNumber(query.data.vehicleNumber ?? '');
    setTransporterName(query.data.transporterName ?? '');
    setTransporterId(query.data.transporterId ?? '');
    setTransportDistanceKm(String(query.data.transportDistanceKm ?? ''));
    setAmendGstin(query.data.filingPartyGstin ?? '');
    setAmendPos(query.data.filingPlaceOfSupply ?? '');
  }

  useEffect(() => {
    if (!helpCancel || query.data?.status !== 'COMPLETED') return;
    if (moreBtnRef.current) setMoreAnchor(moreBtnRef.current);
  }, [helpCancel, query.data?.status]);

  useEffect(() => {
    if (!helpCancel || !moreAnchor) return;
    cancelBtnRef.current?.focus();
    cancelBtnRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, [helpCancel, moreAnchor]);

  const completeMutation = useMutation({
    // F2-035: completeWithConfirms loops over known confirm codes in any
    // order — the hand-nested try/catch here only recovered
    // place_of_supply_unresolved -> GSTIN_TOTAL_CHANGED in that exact order.
    mutationFn: (overrideReason?: string) =>
      completeWithConfirms((extra) =>
        completeSalesInvoice(invoiceId, {
          ...extra,
          gstGuardOverrideReason: overrideReason,
          belowCostOverrideReason: belowCostReason.current || undefined,
        }),
      ),
    onSuccess: (data) => {
      const warns = (data?.warnings ?? []).filter(Boolean).join(' ');
      setMessage(warns ? `${t('billing.invoiceCompleted')} ${warns}` : t('billing.invoiceCompleted'));
      belowCostReason.current = '';
      setGstGuardIssues(null);
      setGstGuardOverrideReason('');
      setGstGuardWarnings(data?.gstGuardWarnings?.length ? data.gstGuardWarnings : null);
      invalidateInvoiceSideEffects(qc, invoiceId);
    },
    onError: (err) => {
      if (getErrorCode(err) === 'below_cost' && user?.role === 'OWNER') {
        // An owner may sell under cost with a reason. The reason is kept on the bill's audit trail.
        const reason = window.prompt(t('billing.belowCostPrompt'), '');
        if (reason?.trim()) {
          belowCostReason.current = reason.trim();
          completeMutation.mutate(undefined);
          return;
        }
      }
      if (getErrorCode(err) === 'gst_guard_blocked') {
        const data = (err as { response?: { data?: Record<string, unknown> } })?.response?.data;
        const nested = data?.error as { details?: { blocking?: unknown } } | undefined;
        const blocking = Array.isArray(nested?.details?.blocking) ? nested.details.blocking : [];
        setGstGuardIssues(blocking as { code: string; message: string }[]);
        return;
      }
      captureError(err);
    },
  });

  const cancelMutation = useMutation({
    mutationFn: (reason: string) => cancelSalesInvoice(invoiceId, { reason }),
    onSuccess: (result) => {
      if (result.outcome === 'pending') {
        const pendingLabel = query.data?.number?.trim() || (query.data ? `Draft #${query.data.id}` : '');
        setMessage(t('history.cancelPending', { label: pendingLabel }));
      } else {
        setMessage(t('billing.invoiceCancelled'));
      }
      setCancelOpen(false);
      setCancelReason('');
      invalidateInvoiceSideEffects(qc, invoiceId);
    },
    onError: (err) => captureError(err),
  });

  const [cancelOpen, setCancelOpen] = useState(false);
  const [cancelReason, setCancelReason] = useState('');
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

  const invoiceReturns = useQuery({
    queryKey: ['invoice-sales-returns', invoiceId],
    queryFn: () => listSalesReturns({ sales_invoice: String(invoiceId) }),
    enabled:
      Number.isFinite(invoiceId) &&
      (query.data?.status === 'RETURNED' || query.data?.returnState === 'PARTIAL'),
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

  const canPromise = canManagePaymentPromises(user);
  const paymentPromises = useQuery({
    queryKey: ['payment-promises', invoiceId],
    // F2-050: no customer/invoice-scoped backend filter is confirmed to
    // exist yet, so we fetch open promises and filter to this invoice
    // client-side.
    queryFn: () => listPaymentPromises({ invoice: invoiceId }),
    enabled: invoiceIdValid && canPromise,
  });
  const promiseList = Array.isArray(paymentPromises.data) ? paymentPromises.data : [];
  const invoicePromise = promiseList.find(
    (p) => p.invoice === invoiceId && !p.resolved,
  );

  const createPromiseMutation = useMutation({
    mutationFn: () =>
      createPaymentPromise({
        customer: query.data!.customer,
        invoice: invoiceId,
        promisedDate: promiseDate,
        promisedAmount: promiseAmount.trim(),
        note: promiseNote.trim() || undefined,
      }),
    onSuccess: () => {
      setMessage(t('billing.paymentPromiseCreated'));
      setPromiseOpen(false);
      setPromiseNote('');
      setPromiseAmount('');
      void qc.invalidateQueries({ queryKey: ['payment-promises', invoiceId] });
    },
    onError: (err) => captureError(err),
  });

  const resolvePromiseMutation = useMutation({
    mutationFn: (promiseId: number) => resolvePaymentPromise(promiseId),
    onSuccess: () => {
      setMessage(t('billing.paymentPromiseResolved'));
      void qc.invalidateQueries({ queryKey: ['payment-promises', invoiceId] });
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

  const whatsappButtonHint = query.data?.whatsappOffer && !query.data.whatsappOffer.optIn
    ? t('common.whatsappOptInOffHint')
    : isRuntimeFlagEnabled('ENABLE_WHATSAPP_CLOUD')
      ? t('common.whatsappSend')
      : t('common.whatsappShare');

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
    async (copy: 'ORIGINAL' | 'DUPLICATE' | 'TRIPLICATE') => {
      try {
        const blob = await downloadInvoicePdf(invoiceId, { copy });
        const base = query.data?.number ?? `invoice-${invoiceId}`;
        triggerBlobDownload(blob, `${base}_${copy.toLowerCase()}.pdf`);
      } catch (err) {
        setError(getErrorMessage(err));
        setErrorSource(err);
      }
    },
    [invoiceId, query.data],
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
          <PageTitle>
            {inv.number?.trim() ? inv.number : `Draft #${inv.id}`}
          </PageTitle>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 0.5, flexWrap: 'wrap' }}>
            <StatusChip
              tone={documentStatusTone(invoiceDisplayStatus(inv))}
              labelKey={statusLabelKey(invoiceDisplayStatus(inv))}
            />
            {inv.status === 'CANCELLED' && inv.cancelReason ? (
              <Typography variant="body2" color="text.secondary">
                {t('invoiceDetail.cancelReason', { reason: inv.cancelReason })}
              </Typography>
            ) : null}
            {inv.returnState === 'PARTIAL' ? (
              <StatusChip tone="warning" labelKey="status.PARTIALLY_RETURNED" />
            ) : null}
            {inv.cancelApprovalPending ? <Chip size="small" label={t('history.cancelPendingChip')} /> : null}
            <Chip size="small" label={inv.invoiceType} variant="outlined" />
            <Typography variant="body2" color="text.secondary">
              {inv.invoiceDate}
            </Typography>
          </Stack>
          <Typography sx={{ mt: 1 }}>{inv.customerName}</Typography>
          <Box sx={{ mt: 1 }}>
            <SourceQuotationsPanel sources={inv.sourceQuotations} differ={inv.sourceQuotationsDiffer} />
          </Box>
        </Box>
        <Stack direction="row" spacing={1}>
          {showAudit ? (
            <Button variant="outlined" onClick={() => setProfitOpen(true)}>
              {t('invoiceDetail.profitDetails')}
            </Button>
          ) : null}
          <Button component={RouterLink} to="/sales/history">
            {t('common.back')}
          </Button>
        </Stack>
      </Stack>

      {message ? (
        <Alert severity="success" role="status" aria-live="polite">
          {message}
        </Alert>
      ) : null}
      {error ? (
        <HelpErrorAlert message={error} error={errorSource} invoiceId={invoiceId} />
      ) : null}

      {gstGuardIssues && gstGuardIssues.length > 0 ? (
        <Alert severity="error" sx={{ mb: 1 }}>
          <Typography fontWeight={600}>{t('billing.gstGuardBlockingTitle')}</Typography>
          <Box component="ul" sx={{ m: '4px 0 8px', pl: 2.5 }}>
            {gstGuardIssues.map((issue) => (
              <li key={issue.code}>{issue.message}</li>
            ))}
          </Box>
          {canOverrideGstGuard(user) ? (
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems="stretch">
              <TextField
                size="small"
                fullWidth
                label={t('billing.gstGuardOverrideReasonLabel')}
                value={gstGuardOverrideReason}
                onChange={(e) => setGstGuardOverrideReason(e.target.value)}
              />
              <Button
                variant="contained"
                color="warning"
                disabled={!gstGuardOverrideReason.trim() || completeMutation.isPending}
                onClick={() => completeMutation.mutate(gstGuardOverrideReason.trim())}
              >
                {t('billing.gstGuardOverrideButton')}
              </Button>
            </Stack>
          ) : (
            <Typography variant="body2" color="text.secondary">
              {t('billing.gstGuardOverridePermissionNote')}
            </Typography>
          )}
        </Alert>
      ) : null}
      {gstGuardWarnings && gstGuardWarnings.length > 0 ? (
        <Alert severity="warning" sx={{ mb: 1 }}>
          <Typography fontWeight={600}>{t('billing.gstGuardWarningTitle')}</Typography>
          <Box component="ul" sx={{ m: '4px 0 0', pl: 2.5 }}>
            {gstGuardWarnings.map((warning) => (
              <li key={warning.code}>{warning.message}</li>
            ))}
          </Box>
        </Alert>
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
          {inv.status === 'COMPLETED' || inv.status === 'RETURNED' ? (
            <InvoicePostedActionBar
              invoice={inv}
              customerGstin={customerQuery.data?.gstin}
              onShareWhatsApp={() => {
                setShareChannel('WHATSAPP');
                setShareOpen(true);
              }}
              onShareEmail={() => {
                setShareChannel('EMAIL');
                setShareOpen(true);
              }}
              onRecordPayment={() => setPayOpen(true)}
              onMessage={setMessage}
              onError={captureError}
            />
          ) : null}
          <Button ref={moreBtnRef} variant="outlined" onClick={(e) => setMoreAnchor(e.currentTarget)}>{t('cog.moreActions')}</Button>
          {inv.status === 'DRAFT' && canCreateSales(user) ? (
            <Button
              variant="contained"
              disabled={completeMutation.isPending}
              onClick={() => completeMutation.mutate(undefined)}
            >
              {t('common.complete')}
            </Button>
          ) : null}
          {inv.status === 'COMPLETED' && hasLiveIrn(inv) ? (
            // Shown, not tucked away: the reason Edit is off is the point of this button.
            <Button
              variant="outlined"
              disabled
              aria-label={t('common.edit')}
              title={t('einvoice.editDisabledLiveIrn')}
            >
              {t('common.edit')}
            </Button>
          ) : null}
          <Menu anchorEl={moreAnchor} open={Boolean(moreAnchor)} onClose={() => setMoreAnchor(null)}>
            {canEditInvoiceLines(inv) ? (
              <MenuItem component={RouterLink} to={`/sales/history/${inv.id}/edit`} onClick={() => setMoreAnchor(null)}>{t('common.edit')}</MenuItem>
            ) : null}
            {inv.status === 'DRAFT' && canCreateSales(user) ? (
              <MenuItem onClick={() => { setMoreAnchor(null); completeMutation.mutate(undefined); }}>{t('common.complete')}</MenuItem>
            ) : null}
            {inv.status === 'COMPLETED' && canCancelDocuments(user) ? (
              <MenuItem
                id="invoice-cancel"
                ref={cancelBtnRef}
                onClick={() => {
                  setMoreAnchor(null);
                  setCancelReason('');
                  setCancelOpen(true);
                }}
              >{t('common.cancel')}</MenuItem>
            ) : null}
            {canAct ? (
              <MenuItem component={RouterLink} to={`/sales/credit-notes/new?fromInvoice=${inv.id}`} onClick={() => setMoreAnchor(null)}>{t('cog.returnGoods')}</MenuItem>
            ) : null}
            {canAct ? <MenuItem onClick={() => { setMoreAnchor(null); void downloadCopy('ORIGINAL'); }}>{t('billing.downloadOriginal')}</MenuItem> : null}
            {canAct ? <MenuItem onClick={() => { setMoreAnchor(null); void downloadCopy('DUPLICATE'); }}>{t('billing.downloadDuplicate')}</MenuItem> : null}
            {canAct ? <MenuItem onClick={() => { setMoreAnchor(null); void downloadCopy('TRIPLICATE'); }}>{t('billing.downloadTriplicate')}</MenuItem> : null}
            {canAct ? <MenuItem onClick={() => { setMoreAnchor(null); void handlePrint(); }}>{t('billing.print')}</MenuItem> : null}
            {canAct ? <MenuItem onClick={() => { setMoreAnchor(null); void handleThermalPrint(80); }}>{t('sweep2.printReceipt80')}</MenuItem> : null}
            {canAct ? <MenuItem onClick={() => { setMoreAnchor(null); void handleThermalPrint(58); }}>{t('sweep2.printReceipt58')}</MenuItem> : null}
            {primaryPostedAction({ status: inv.status, balance: toNumber(inv.balance), canPay: canCreatePayments(user) }) !== 'share' ? (
              <MenuItem onClick={() => { setMoreAnchor(null); setShareOpen(true); }}>{t('common.share')}</MenuItem>
            ) : null}
            {primaryPostedAction({ status: inv.status, balance: toNumber(inv.balance), canPay: canCreatePayments(user) }) !== 'pay' && canCreatePayments(user) && toNumber(inv.balance) > 0.009 ? (
              <MenuItem onClick={() => { setMoreAnchor(null); setPayOpen(true); }}>{t('history.recordPayment')}</MenuItem>
            ) : null}
          </Menu>
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
              <Typography>{t('invoiceDetail.taxable')}</Typography>
              <Typography>{formatMoney(inv.taxableTotal)}</Typography>
            </Stack>
            {showTax ? (
              <>
                <Stack direction="row" justifyContent="space-between">
                  <Typography>{t('invoiceDetail.cgst')}</Typography>
                  <Typography>{formatMoney(inv.cgstTotal)}</Typography>
                </Stack>
                <Stack direction="row" justifyContent="space-between">
                  <Typography>{t('invoiceDetail.sgst')}</Typography>
                  <Typography>{formatMoney(inv.sgstTotal)}</Typography>
                </Stack>
                <Stack direction="row" justifyContent="space-between">
                  <Typography>{t('invoiceDetail.igst')}</Typography>
                  <Typography>{formatMoney(inv.igstTotal)}</Typography>
                </Stack>
              </>
            ) : null}
          </Stack>
        </Paper>
      </Stack>

      {hsnQuery.data?.rows?.length ? (
        <Paper sx={{ p: 2 }}>
          <Typography variant="subtitle2" color="text.secondary">{t('history.hsnSummary')}</Typography>
          <Divider sx={{ my: 1 }} />
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>HSN</TableCell>
                <TableCell align="right">{t('billing.qty')}</TableCell>
                <TableCell align="right">{t('billing.taxableAmount')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {hsnQuery.data.rows.map((row, idx) => (
                <TableRow key={`${row.hsn}-${idx}`}>
                  <TableCell>{String(row.hsn ?? '—')}</TableCell>
                  <TableCell align="right">{String(row.quantity ?? row.qty ?? '')}</TableCell>
                  <TableCell align="right">{formatMoney(toNumber((row.taxableValue ?? row.taxable_value) as string | number))}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}

      {showAudit && profitQuery.data ? (
        <Paper sx={{ p: 2 }}>
          <Typography variant="subtitle2" color="text.secondary">{t('reports.invoiceProfit')}</Typography>
          <Divider sx={{ my: 1 }} />
          {(() => {
            const row = (profitQuery.data.rows ?? []).find(
              (r) => Number((r as { invoiceId?: number; invoice_id?: number }).invoiceId ?? (r as { invoice_id?: number }).invoice_id) === invoiceId,
            ) as { grossMargin?: string; gross_margin?: string; marginPercent?: string; cogsTotal?: string } | undefined;
            if (!row) {
              return <Typography variant="body2" color="text.secondary">—</Typography>;
            }
            return (
              <Stack spacing={0.5}>
                <Typography variant="body2">{t('reports.cogs')}: {formatMoney(toNumber(row.cogsTotal))}</Typography>
                <Typography variant="body2">{t('reports.grossMargin')}: {formatMoney(toNumber(row.grossMargin ?? row.gross_margin))}</Typography>
              </Stack>
            );
          })()}
        </Paper>
      ) : null}

      {canAct ? (
        <Paper sx={{ p: 2 }}>
          <Typography variant="subtitle2" color="text.secondary">
            {t('sweep2.allocations')}
          </Typography>
          <Divider sx={{ my: 1 }} />
          {activeAllocations.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              {t('sweep2.noActiveAllocations')}
            </Typography>
          ) : (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>{t('invoiceDetail.receipt')}</TableCell>
                  <TableCell align="right">{t('invoiceDetail.amount')}</TableCell>
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
                          {t('sweep2.unallocate')}
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

      {(invoiceReturns.data ?? []).length > 0 ? (
        <Paper sx={{ p: 2 }}>
          <Typography variant="subtitle2" color="text.secondary">
            {t('billing.relatedReturns')}
          </Typography>
          <Divider sx={{ my: 1 }} />
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('common.number')}</TableCell>
                <TableCell>{t('common.date')}</TableCell>
                <TableCell>{t('common.status')}</TableCell>
                <TableCell align="right">{t('common.total')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(invoiceReturns.data ?? []).map((ret) => (
                <TableRow key={ret.id}>
                  <TableCell>
                    <Typography
                      component={RouterLink}
                      to="/sales/returns"
                      sx={{ color: 'primary.main', textDecoration: 'none' }}
                    >
                      {ret.number?.trim() ? ret.number : `#${ret.id}`}
                    </Typography>
                  </TableCell>
                  <TableCell>{ret.returnDate}</TableCell>
                  <TableCell>
                    <StatusChip
                      tone={documentStatusTone(ret.status)}
                      labelKey={statusLabelKey(ret.status)}
                    />
                  </TableCell>
                  <TableCell align="right">{formatMoney(ret.grandTotal)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}

      {canAct && toNumber(inv.balance) > 0 ? (
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
          <Paper sx={{ p: 2, flex: 1 }}>
            <Typography variant="h6" sx={{ mb: 1 }}>
              UPI collect
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
              Amount-locked QR for outstanding {formatMoney(inv.balance)}.
            </Typography>
            {upiError ? <HelpErrorAlert message={upiError} sx={{ mb: 1 }} /> : null}
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 1.5 }}>
              <Button
                variant="contained"
                size="small"
                disabled={upiMutation.isPending}
                onClick={() => upiMutation.mutate()}
              >
                {t('sweep2.generateUpiQr')}
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
                  {t('sweep2.copyIntentLink')}
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
              {t('sweep2.paymentLink')}
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
              {t('sweep2.createPaymentLink')}
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
                          {t('sweep2.open')}
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
                        {t('sweep2.cancel')}
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
                        {isRuntimeFlagEnabled('ENABLE_WHATSAPP_CLOUD')
                          ? t('common.whatsappSend')
                          : t('common.whatsappShare')}
                      </Button>
                      <TextField
                        size="small"
                        label={t('invoiceDetail.email')}
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
                        {t('sweep2.sendEmail')}
                      </Button>
                    </Stack>
                  ) : null}
                </Box>
              ))}
              {!paymentLinks.data?.length ? (
                <Typography variant="body2" color="text.secondary">
                  {t('sweep2.noLinksYet')}
                </Typography>
              ) : null}
            </Stack>
          </Paper>
        </Stack>
      ) : null}

      {canPromise && (invoicePromise || toNumber(inv.balance) > 0) ? (
        <Paper sx={{ p: 2 }}>
          <Typography variant="h6" sx={{ mb: 1 }}>
            {t('billing.paymentPromiseTitle')}
          </Typography>
          {invoicePromise ? (
            <Stack spacing={1} alignItems="flex-start">
              <Typography>
                {t('billing.paymentPromiseExisting', { date: invoicePromise.promisedDate })}
              </Typography>
              {invoicePromise.note ? (
                <Typography variant="body2" color="text.secondary">
                  {invoicePromise.note}
                </Typography>
              ) : null}
              <Button
                size="small"
                variant="outlined"
                disabled={resolvePromiseMutation.isPending}
                onClick={() => resolvePromiseMutation.mutate(invoicePromise.id)}
              >
                {t('billing.paymentPromiseResolve')}
              </Button>
            </Stack>
          ) : (
            <Button
              variant="outlined"
              size="small"
              onClick={() => {
                setPromiseDate(defaultPromiseDate());
                setPromiseNote('');
                setPromiseAmount(String(toNumber(inv.balance) > 0 ? toNumber(inv.balance) : ''));
                setPromiseOpen(true);
              }}
            >
              {t('billing.paymentPromiseLog')}
            </Button>
          )}
        </Paper>
      ) : null}

      <Dialog open={promiseOpen} onClose={() => setPromiseOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{t('billing.paymentPromiseLog')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              type="date"
              label={t('billing.paymentPromiseDateLabel')}
              value={promiseDate}
              onChange={(e) => setPromiseDate(e.target.value)}
              InputLabelProps={{ shrink: true }}
              fullWidth
            />
            <TextField
              type="number"
              label={t('osPlan.promiseAmount')}
              value={promiseAmount}
              onChange={(e) => setPromiseAmount(e.target.value)}
              inputProps={{ min: 0, step: '0.01' }}
              required
              fullWidth
            />
            <TextField
              label={t('billing.paymentPromiseNoteLabel')}
              value={promiseNote}
              onChange={(e) => setPromiseNote(e.target.value)}
              multiline
              minRows={2}
              fullWidth
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPromiseOpen(false)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={
              !promiseDate.trim() || !(Number(promiseAmount) > 0) || createPromiseMutation.isPending
            }
            onClick={() => createPromiseMutation.mutate()}
          >
            {t('billing.paymentPromiseSave')}
          </Button>
        </DialogActions>
      </Dialog>

      <Paper tabIndex={0} role="region" aria-label={t('common.scrollableTable')} sx={{ overflow: 'auto' }}>
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
              {t('sweep2.transportEway')}
            </Typography>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ mb: 1.5 }}>
              <TextField
                label={t('invoiceDetail.vehicleNo')}
                size="small"
                value={vehicleNumber}
                onChange={(e) => setVehicleNumber(e.target.value)}
                fullWidth
              />
              <TextField
                label={t('invoiceDetail.transporterName')}
                size="small"
                value={transporterName}
                onChange={(e) => setTransporterName(e.target.value)}
                fullWidth
              />
              <TextField
                label={t('invoiceDetail.transporterId')}
                size="small"
                value={transporterId}
                onChange={(e) => setTransporterId(e.target.value)}
                fullWidth
              />
              <TextField
                label={t('invoiceDetail.distanceKm')}
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
              {t('sweep2.saveTransport')}
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
          <Typography variant="body2" color="text.secondary">
            {t('common.publicLinkStaffWarning')}
          </Typography>
          {shareLink && isAllowedShareUrl(shareLink) ? (
            <Typography variant="body2" sx={{ mt: 1 }}>
              <a href={shareLink} target="_blank" rel="noopener noreferrer">
                {shareLink}
              </a>
            </Typography>
          ) : null}
        </Paper>
      ) : null}

      <Dialog
        open={cancelOpen}
        onClose={() => {
          setCancelOpen(false);
          setCancelReason('');
          moreBtnRef.current?.focus();
        }}
        aria-labelledby="detail-cancel-title"
        aria-describedby="detail-cancel-body"
      >
        <DialogTitle id="detail-cancel-title">
          {t('history.confirmCancelTitle', { label: inv.number?.trim() || `Draft #${inv.id}` })}
        </DialogTitle>
        <DialogContent>
          <Typography id="detail-cancel-body" variant="body2" sx={{ mb: 2 }}>
            {t('history.confirmCancelBody')}
          </Typography>
          <TextField
            autoFocus
            fullWidth
            required
            label={t('history.cancelReason')}
            value={cancelReason}
            onChange={(event) => setCancelReason(event.target.value.slice(0, 500))}
            inputProps={{ maxLength: 500 }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => {
            setCancelOpen(false);
            setCancelReason('');
            moreBtnRef.current?.focus();
          }}
          >{t('common.close')}</Button>
          <Button
            color="error"
            variant="contained"
            disabled={!cancelReason.trim() || cancelMutation.isPending}
            onClick={() => cancelMutation.mutate(cancelReason.trim())}
          >
            {t('history.confirmCancelInvoice')}
          </Button>
        </DialogActions>
      </Dialog>
      <RecordInvoicePaymentDialog
        invoice={inv}
        open={payOpen}
        onClose={() => setPayOpen(false)}
        onSuccess={() => {
          setPayOpen(false);
          // A payment changes the allocations table, the lists, the customer's balance and the
          // dashboard, not only this invoice.
          for (const key of ['sales-invoice', 'invoice-allocations', 'sales-invoices', 'sales-invoice-payment-stats', 'customers', 'receipts', 'dashboard']) {
            void qc.invalidateQueries({ queryKey: key === 'sales-invoice' || key === 'invoice-allocations' ? [key, invoiceId] : [key] });
          }
        }}
      />
      <ProfitDetailsDialog
        invoiceId={invoiceIdValid ? invoiceId : null}
        open={profitOpen}
        onClose={() => setProfitOpen(false)}
      />
      <ShareInvoiceDialog
        open={shareOpen}
        invoiceId={invoiceIdValid ? invoiceId : null}
        initialChannel={shareChannel}
        defaultPhone={inv.whatsappOffer?.phone || customerQuery.data?.phone || ''}
        defaultEmail={customerQuery.data?.email || ''}
        onClose={() => setShareOpen(false)}
        onSuccess={(msg, res) => {
          setMessage(msg);
          setError(null);
          setErrorSource(null);
          if (res.shareLink) setShareLink(res.shareLink);
          void qc.invalidateQueries({ queryKey: ['sales-invoice', invoiceId] });
        }}
        onError={(msg) => {
          setError(msg);
          setErrorSource(null);
        }}
      />

      <Dialog open={amendOpen} onClose={() => setAmendOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{t('einvoice.amendFilingIdentity')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label={t('invoiceDetail.filingGstin')}
              value={amendGstin}
              onChange={(e) => setAmendGstin(e.target.value)}
              helperText={`Current: ${inv.filingPartyGstin?.trim() || '—'}`}
            />
            <TextField
              label={t('invoiceDetail.placeOfSupply')}
              value={amendPos}
              onChange={(e) => setAmendPos(e.target.value)}
              helperText={`Current: ${inv.filingPlaceOfSupply?.trim() || '—'}`}
            />
            <TextField
              label={t('invoiceDetail.reason')}
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
            {t('sweep2.saveAmendment')}
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
