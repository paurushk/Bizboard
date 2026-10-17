import { useEffect, useMemo, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import FormControlLabel from '@mui/material/FormControlLabel';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { prefillReturnLines } from '@/cognitive/loadHelpers';
import { getErrorMessage } from '@/api/client';
import { completeWithConfirms } from '@/utils/completeWithConfirms';
import { useConfirmPrompt } from '@/hooks/useConfirmPrompt';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { invalidateNoteQueries } from '@/utils/noteQueries';
import {
  cancelSalesCreditNote,
  cancelSalesDebitNote,
  completeSalesCreditNote,
  completeSalesDebitNote,
  createSalesCreditNote,
  createSalesDebitNote,
  downloadSalesDocumentPdf,
  getCompany,
  getCustomer,
  getGstr9FilingDate,
  getSalesCreditNote,
  getSalesCreditNoteAdjustableSummary,
  getSalesDebitNote,
  getSalesInvoice,
  listSalesInvoicesPage,
  updateSalesCreditNote,
  updateSalesDebitNote,
} from '@/api/resources';
import {
  DocumentEditorShell,
  InvoiceSourceLineTable,
  NoteReasonSelect,
  SimpleTotalsPanel,
  activeSourceLines,
  invoiceItemsToSourceLines,
  noteItemsToSourceLines,
  primarySaveAction,
  printBlob,
  todayIso,
  useBillingSaveFeedback,
} from '@/components/billing';
import type { InvoiceSourceLine } from '@/components/billing';
import { NoteEinvoicePanel } from '@/components/NoteEinvoicePanel';
import { ErrorState, LoadingState } from '@/components/PageState';
import { UnsavedChangesGuard } from '@/components/UnsavedChangesGuard';
import { PdfStatusPoller } from '@/components/PdfStatusPoller';
import { StatusChip } from '@/components/StatusChip';
import { t } from '@/i18n';
import { usePreviewTotals } from '@/hooks/usePreviewTotals';
import {
  firstCompleteDisabledReason,
  previewAllowsComplete,
} from '@/completeGates/completeBlockers';
import { useAuth } from '@/auth/AuthContext';
import { canCancelDocuments, canIssueNotes, canOverrideGstGuard, isOwner } from '@/utils/permissions';
import type { NoteReason, SalesCreditNote, SalesDebitNote, SalesInvoice } from '@/types/domain';
import { calculateInvoiceTotals, calculateLineTax, isIntraState } from '@/utils/tax';
import { documentStatusTone, statusLabelKey } from '@/utils/status';
import { formatMoney } from '@/utils/money';

type NoteKind = 'credit' | 'debit';

export function SalesInvoiceNoteEditor({ kind }: { kind: NoteKind }) {
  const isCredit = kind === 'credit';
  const listPath = isCredit ? '/sales/credit-notes' : '/sales/debit-notes';
  const queryKey = isCredit ? 'sales-credit-notes' : 'sales-debit-notes';

  const { user } = useAuth();
  const canWrite = canIssueNotes(user);
  const confirmPrompt = useConfirmPrompt();
  const canCancel = canCancelDocuments(user);
  const { id: editIdParam } = useParams();
  const editId = editIdParam ? Number(editIdParam) : null;
  const isEdit = Number.isFinite(editId) && (editId as number) > 0;
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const fromInvoiceId = searchParams.get('fromInvoice');
  const qc = useQueryClient();
  const { message, error, clearFeedback, flashError, setMessage } = useBillingSaveFeedback();

  const [loaded, setLoaded] = useState(false);
  // F2-041: suppress UnsavedChangesGuard for the programmatic navigate() after
  // a deliberate save/cancel — those aren't "discarding" anything.
  const [skipLeaveGuard, setSkipLeaveGuard] = useState(false);
  const createdNoteId = useRef<number | null>(null);
  const [gstGuardOverrideReason, setGstGuardOverrideReason] = useState('');
  const [editingStatus, setEditingStatus] = useState<string | null>(null);
  const [invoice, setInvoice] = useState<SalesInvoice | null>(null);
  const [noteDate, setNoteDate] = useState(todayIso());
  const [reason, setReason] = useState<NoteReason>('CORRECTION_OF_INVOICE');
  const [reasonDetail, setReasonDetail] = useState('');
  const [notes, setNotes] = useState('');
  const [additionalCharges, setAdditionalCharges] = useState('');
  const [chargesHsn, setChargesHsn] = useState('');
  const [chargesGstRate, setChargesGstRate] = useState('');
  // DN-07: Owner-only override of the 100%-of-invoice cap on a debit note.
  const [allowExcessDebit, setAllowExcessDebit] = useState(false);
  const [excessDebitReason, setExcessDebitReason] = useState('');
  const [invoiceSearch, setInvoiceSearch] = useState('');
  const [lines, setLines] = useState<InvoiceSourceLine[]>([]);
  const [pool, setPool] = useState<InvoiceSourceLine[]>([]);

  const company = useQuery({ queryKey: ['company'], queryFn: getCompany });
  // F2-025: fetch just the note's customer by id instead of loading the
  // entire customer list to look up one GSTIN/state.
  const customerId = invoice?.customer;
  const customerQuery = useQuery({
    queryKey: ['customer', customerId],
    queryFn: () => getCustomer(customerId as number),
    enabled: !!customerId,
  });
  // CN-09 / DN-08: search on the server and fetch one small page, instead of
  // loading every completed invoice into the browser.
  const debouncedInvoiceSearch = useDebouncedValue(invoiceSearch.trim(), 300);
  const invoices = useQuery({
    queryKey: ['note-source-invoices', kind, debouncedInvoiceSearch],
    queryFn: async () => {
      const base = { page: 1, pageSize: 20, q: debouncedInvoiceSearch || undefined };
      const completed = await listSalesInvoicesPage({ ...base, status: 'COMPLETED' });
      if (isCredit) return completed.results;
      // Residual debit notes after a full return attach to RETURNED invoices
      // (P5-T2 / ARCH-03). The list API takes one status, so join both.
      const returned = await listSalesInvoicesPage({ ...base, status: 'RETURNED' });
      return [...returned.results, ...completed.results];
    },
    enabled: !isEdit,
  });
  const existing = useQuery({
    queryKey: [queryKey, editId],
    queryFn: () =>
      isCredit ? getSalesCreditNote(editId as number) : getSalesDebitNote(editId as number),
    enabled: isEdit,
  });
  const summary = useQuery({
    queryKey: ['adjustable-summary', invoice?.id],
    queryFn: () => getSalesCreditNoteAdjustableSummary(invoice!.id),
    enabled: isCredit && Boolean(invoice?.id),
  });

  // CN-07 / QOS-0127: s.34(2) - the credit note limit is the earlier of 30 Nov after the invoice's FY
  // (Apr-Mar) and the date that FY's annual return was filed; the server tells us the effective date.
  const invoiceFyStart = /^\d{4}-\d{2}-\d{2}$/.test(invoice?.invoiceDate ?? '')
    ? Number(invoice!.invoiceDate.slice(0, 4)) - (Number(invoice!.invoiceDate.slice(5, 7)) >= 4 ? 0 : 1)
    : null;
  const filingDate = useQuery({
    queryKey: ['gstr9-filing-date', invoiceFyStart],
    queryFn: () => getGstr9FilingDate(`${invoiceFyStart}-${String((invoiceFyStart! + 1) % 100).padStart(2, '0')}`),
    enabled: isCredit && invoiceFyStart != null,
    retry: false,
  });

  const readOnly = editingStatus != null && editingStatus !== 'DRAFT';

  const [seenEditId, setSeenEditId] = useState(editId);
  if (seenEditId !== editId) {
    setSeenEditId(editId);
    setLoaded(false);
    clearFeedback();
  }

  // Hydrate the form from the saved note once; the source invoice it needs is fetched in the
  // effect below, keyed on this one hydration so a background refetch cannot re-run it.
  const [hydratedDoc, setHydratedDoc] = useState<typeof existing.data>(undefined);
  if (existing.data && !loaded) {
    const doc = existing.data;
    setEditingStatus(doc.status);
    setNoteDate(doc.noteDate);
    setReason(doc.reason);
    setReasonDetail(doc.reasonDetail ?? '');
    setNotes(doc.notes ?? '');
    setAdditionalCharges(Number(doc.additionalCharges ?? 0) ? String(doc.additionalCharges) : '');
    setChargesHsn(doc.chargesHsn ?? '');
    setChargesGstRate(Number(doc.chargesGstRate ?? 0) ? String(doc.chargesGstRate) : '');
    setHydratedDoc(doc);
    setLoaded(true);
  }

  useEffect(() => {
    if (!hydratedDoc) return;
    let cancelled = false;
    void getSalesInvoice(hydratedDoc.salesInvoice).then((inv) => {
      if (cancelled) return;
      setInvoice(inv);
      setLines(noteItemsToSourceLines(hydratedDoc.items, inv.items));
      setPool(invoiceItemsToSourceLines(inv.items));
    });
    return () => {
      cancelled = true;
    };
  }, [hydratedDoc]);

  useEffect(() => {
    if (isEdit || !fromInvoiceId) return;
    const invoiceId = Number(fromInvoiceId);
    if (!Number.isFinite(invoiceId)) return;
    let cancelled = false;
    void getSalesInvoice(invoiceId).then((inv) => {
      if (cancelled) return;
      const src = invoiceItemsToSourceLines(inv.items);
      setInvoice(inv);
      setPool(src);
      setLines(prefillReturnLines(src));
    });
    return () => {
      cancelled = true;
    };
  }, [fromInvoiceId, isEdit]);

  const onInvoicePick = async (inv: SalesInvoice | null) => {
    setInvoice(inv);
    if (!inv) {
      setLines([]);
      setPool([]);
      return;
    }
    const full = inv.items?.length ? inv : await getSalesInvoice(inv.id);
    setInvoice(full);
    const src = invoiceItemsToSourceLines(full.items);
    setPool(src);
    setLines(prefillReturnLines(src));
  };

  const partyState = invoice?.customer
    ? customerQuery.data?.gstin || customerQuery.data?.state
    : undefined;

  // F2-024: was missing assumeLocalStateForBlankParty — NewInvoicePage passes
  // it, so a note on the same company/customer could show withheld GST here
  // while the source invoice actually charged it.
  const intraState = isIntraState(
    company.data?.gstin || company.data?.state,
    partyState,
    { assumeLocalStateForBlankParty: !!company.data?.assumeLocalStateForBlankParty },
  );

  const lineTaxes = useMemo(
    () =>
      activeSourceLines(lines).map((l) =>
        calculateLineTax({
          quantity: l.quantity,
          unitPrice: l.unitPrice,
          discountPercent: l.discountPercent,
          gstRate: l.gstRate,
          cessRate: l.cessRate,
          intraState,
        }),
      ),
    [lines, intraState],
  );

  const chargesAmount = Number(additionalCharges) || 0;
  const totals = useMemo(
    () =>
      calculateInvoiceTotals(lineTaxes.map((l) => ({ ...l, intraState })), {
        applyRoundOff: true,
        additionalCharges: chargesAmount,
        chargesHsn,
        chargesGstRate: Number(chargesGstRate) || 0,
      }),
    [lineTaxes, intraState, chargesAmount, chargesHsn, chargesGstRate],
  );

  const included = lines.filter((l) => l.included);
  const anyOverCap = included.some((l) => Number(l.quantity) > l.maxQty + 1e-9);
  const zeroQty = included.length > 0 && !included.some((l) => Number(l.quantity) > 0);
  const canSave = Boolean(invoice) && included.length > 0 && canWrite;
  const primarySave = primarySaveAction({ isEdit, editingStatus });

  const buildPayload = () => ({
    customer: invoice!.customer,
    salesInvoice: invoice!.id,
    noteDate,
    reason,
    reasonDetail: reason === 'OTHERS' ? reasonDetail : '',
    notes,
    additionalCharges: chargesAmount,
    chargesHsn: chargesAmount > 0 ? chargesHsn : '',
    chargesGstRate: chargesAmount > 0 ? Number(chargesGstRate) || 0 : 0,
    items: activeSourceLines(lines).map((l) => ({
      ...(l.lineId != null ? { id: l.lineId } : {}),
      product: l.product,
      quantity: l.quantity,
      unitPrice: l.unitPrice,
      discountPercent: l.discountPercent,
      gstRate: l.gstRate,
      cessRate: l.cessRate ?? 0,
      sourceItem: l.sourceItemId ?? null,
    })),
  });

  const previewOnline = typeof navigator === 'undefined' || navigator.onLine;
  const preview = usePreviewTotals(
    'sales',
    previewOnline && invoice && activeSourceLines(lines).length > 0
      ? {
          customer: invoice.customer,
          additionalCharges: chargesAmount,
          chargesHsn: chargesAmount > 0 ? chargesHsn : '',
          chargesGstRate: chargesAmount > 0 ? Number(chargesGstRate) || 0 : 0,
          items: activeSourceLines(lines).map((l) => ({
            product: l.product,
            quantity: l.quantity,
            unitPrice: l.unitPrice,
            discountPercent: l.discountPercent,
            gstRate: l.gstRate,
            cessRate: l.cessRate ?? 0,
          })),
        }
      : null,
  );

  const saveMutation = useMutation({
    mutationFn: async (mode: 'draft' | 'complete') => {
      if (!invoice) throw new Error(t('phase1.selectInvoice'));
      const payload = buildPayload();
      let doc: SalesCreditNote | SalesDebitNote;
      const existingId = (isEdit && editId) || createdNoteId.current;
      if (existingId) {
        doc = isCredit
          ? await updateSalesCreditNote(existingId, payload)
          : await updateSalesDebitNote(existingId, payload);
      } else {
        doc = isCredit
          ? await createSalesCreditNote(payload)
          : await createSalesDebitNote(payload);
        createdNoteId.current = doc.id;
      }
      if (mode === 'complete' && doc.status === 'DRAFT') {
        const extraOverride = gstGuardOverrideReason.trim()
          ? { gstGuardOverrideReason: gstGuardOverrideReason.trim() }
          : {};
        const excessOverride =
          !isCredit && allowExcessDebit && excessDebitReason.trim()
            ? { confirmExcessiveDebit: true, excessiveDebitReason: excessDebitReason.trim() }
            : {};
        doc = isCredit
          ? await completeWithConfirms(
              (extra) => completeSalesCreditNote(doc.id, { ...extra, ...extraOverride }),
              {},
              confirmPrompt.ask,
            )
          : await completeWithConfirms(
              (extra) => completeSalesDebitNote(doc.id, { ...extra, ...extraOverride, ...excessOverride }),
              {},
              confirmPrompt.ask,
            );
      }
      return doc;
    },
    onSuccess: (doc) => {
      setMessage(t('phase1.saved'));
      invalidateNoteQueries(qc, kind);
      if (!isEdit) {
        flushSync(() => setSkipLeaveGuard(true));
        void navigate(`${listPath}/${doc.id}`, { replace: true });
      } else {
        setEditingStatus(doc.status);
      }
    },
    onError: (err) => flashError(getErrorMessage(err)),
  });

  const cancelMutation = useMutation({
    mutationFn: () =>
      isCredit ? cancelSalesCreditNote(editId as number) : cancelSalesDebitNote(editId as number),
    onSuccess: () => {
      setMessage(t('phase1.cancelled'));
      invalidateNoteQueries(qc, kind);
      flushSync(() => setSkipLeaveGuard(true));
      void navigate(listPath);
    },
    onError: (err) => flashError(getErrorMessage(err)),
  });

  const previewFellBack = previewOnline && !preview.ready && preview.error != null;
  const previewPending = previewOnline && !preview.ready && preview.error == null;
  const completeDisabledReason = firstCompleteDisabledReason({
    canSave,
    overCap: anyOverCap,
    zeroQty,
    previewPending,
  });
  const canComplete =
    canSave &&
    !zeroQty &&
    !anyOverCap &&
    previewAllowsComplete(previewOnline, preview.ready, preview.error);

  if (isEdit && existing.isLoading) return <LoadingState />;
  if (isEdit && existing.isError) {
    return (
      <ErrorState message={getErrorMessage(existing.error)} error={existing.error} onRetry={() => void existing.refetch()} />
    );
  }

  const invoiceDate = invoice?.invoiceDate ?? '';
  let creditDeadline = '';
  if (isCredit && /^\d{4}-\d{2}-\d{2}$/.test(invoiceDate)) {
    const y = Number(invoiceDate.slice(0, 4));
    const m = Number(invoiceDate.slice(5, 7));
    creditDeadline = `${(m >= 4 ? y : y - 1) + 1}-11-30`;
    const serverDeadline = filingDate.data?.noteDeadline;
    if (serverDeadline && serverDeadline < creditDeadline) creditDeadline = serverDeadline;
  }
  const dateBeforeInvoice = Boolean(invoiceDate && noteDate && noteDate < invoiceDate);
  const datePastDeadline = Boolean(creditDeadline && noteDate > creditDeadline);
  const dateProblem = dateBeforeInvoice
    ? t('phase1.dateBeforeInvoice')
    : datePastDeadline
      ? t('phase1.datePastDeadline', { date: creditDeadline })
      : undefined;
  // CN-05: payments that will be moved to the customer's advance when the credit note completes.
  const noteTotalNow = Number(preview.totals?.grandTotal ?? totals.grandTotal) || 0;
  const peeledAmount =
    isCredit && summary.data && !readOnly
      ? Math.max(0, noteTotalNow - Number(summary.data.outstanding || 0))
      : 0;
  const peeledReceiptIds = Array.from(
    new Set(
      ((existing.data as SalesCreditNote | undefined)?.peeledReceiptAllocations ?? [])
        .map((slice) => Number(slice.receiptId ?? slice.receipt_id))
        .filter((id) => Number.isFinite(id) && id > 0),
    ),
  );
  const isAutoReturnNote = isCredit && Boolean((existing.data as SalesCreditNote | undefined)?.salesReturn);

  const infoBanner =
    isCredit && summary.data && invoice ? (
      <Alert severity="info">
        {t('phase1.invoiceOutstanding')}: {formatMoney(summary.data.outstanding)} /{' '}
        {formatMoney(summary.data.grandTotal)}
      </Alert>
    ) : null;

  return (
    <>
      {confirmPrompt.dialog}
    <DocumentEditorShell
      title={t(isEdit ? (isCredit ? 'phase1.editCreditNote' : 'phase1.editDebitNote') : (isCredit ? 'phase1.newCreditNote' : 'phase1.newDebitNote'))}
      primarySave={primarySave}
      canSave={canSave}
      canComplete={canComplete}
      primaryDisabledReason={completeDisabledReason}
      isEdit={isEdit}
      backTo={listPath}
      message={message}
      error={error || preview.error}
      warning={
        previewFellBack
          ? t('billing.previewUnavailableClientTotals')
          : // firstCompleteDisabledReason() already returns undefined
            // whenever canSave is false, so completeDisabledReason being
            // truthy already implies canSave -- no need to re-check it here.
            completeDisabledReason && !canComplete
            ? completeDisabledReason
            : null
      }
      infoBanner={
        <>
          {infoBanner}
          {invoice ? (
            <Alert severity="info" icon={false}>
              {t('phase1.sourceInvoice')}:{' '}
              <RouterLink to={`/sales/history/${invoice.id}`}>{invoice.number ?? invoice.id}</RouterLink>
              {' · '}
              {invoice.invoiceDate} · {invoice.customerName ?? ''} · {formatMoney(invoice.grandTotal)}
            </Alert>
          ) : null}
          {isCredit && !readOnly ? (
            <Alert severity="info">
              {t('phase1.noStockRestore')}{' '}
              <RouterLink to="/sales/returns">{t('phase1.goToSalesReturns')}</RouterLink>
            </Alert>
          ) : null}
          {peeledAmount > 0.005 ? (
            <Alert severity="warning">
              {t('phase1.peelNotice', { amount: formatMoney(peeledAmount) })}
            </Alert>
          ) : null}
          {!readOnly && canOverrideGstGuard(user) ? (
            <TextField
              size="small"
              label={t('billing.gstGuardOverrideReasonLabel')}
              value={gstGuardOverrideReason}
              onChange={(e) => setGstGuardOverrideReason(e.target.value)}
              sx={{ maxWidth: 420 }}
            />
          ) : null}
        </>
      }
      saving={saveMutation.isPending}
      hideSaveAndNew
      showDraftButton={!readOnly}
      onPrimarySave={() => saveMutation.mutate(primarySave.mode === 'complete' ? 'complete' : 'draft')}
      onDraft={() => saveMutation.mutate('draft')}
      extraActions={
        <>
          {readOnly && editingStatus === 'COMPLETED' && isEdit ? (
            <Button
              size="small"
              variant="outlined"
              onClick={() => {
                void downloadSalesDocumentPdf(isCredit ? 'credit-note' : 'debit-note', editId as number)
                  .then((blob) => printBlob(blob))
                  .catch((err) => flashError(getErrorMessage(err)));
              }}
            >
              {t('billing.print')}
            </Button>
          ) : null}
          {readOnly && editingStatus === 'COMPLETED' && isCredit
            ? peeledReceiptIds.length > 0
              ? peeledReceiptIds.map((receiptId) => (
                  <Button
                    key={receiptId}
                    size="small"
                    component={RouterLink}
                    to={`/sales/receipts?refund=${receiptId}`}
                  >
                    {t('phase1.refundAdvanceLink')}
                  </Button>
                ))
              : (
                  <Button size="small" component={RouterLink} to="/sales/receipts">
                    {t('phase1.refundAdvanceLink')}
                  </Button>
                )
            : null}
          {readOnly && editingStatus === 'COMPLETED' && isAutoReturnNote ? (
            <Button size="small" component={RouterLink} to="/sales/returns">
              {t('phase1.cancelViaReturn')}
            </Button>
          ) : readOnly && editingStatus === 'COMPLETED' && canCancel ? (
            <Button color="warning" size="small" disabled={cancelMutation.isPending} onClick={() => cancelMutation.mutate()}>
              {t('phase1.cancelDocument')}
            </Button>
          ) : editingStatus && editingStatus !== 'DRAFT' ? (
            <StatusChip tone={documentStatusTone(editingStatus)} labelKey={statusLabelKey(editingStatus)} />
          ) : null}
        </>
      }
    >
      <UnsavedChangesGuard
        when={!skipLeaveGuard && (Boolean(invoice) || activeSourceLines(lines).length > 0)}
      />
      <Stack spacing={2}>
        {editingStatus === 'COMPLETED' && isEdit ? (
          <PdfStatusPoller
            documentId={editId as number}
            docType={isCredit ? 'credit-note' : 'debit-note'}
            filenameBase={existing.data?.number ?? undefined}
          />
        ) : null}
        {editingStatus === 'COMPLETED' && isEdit && existing.data ? (
          <NoteEinvoicePanel
            kind={kind}
            note={existing.data}
            onError={flashError}
            onMessage={setMessage}
          />
        ) : null}
        {!isEdit ? (
          <Autocomplete
            options={invoices.data ?? []}
            getOptionLabel={(o) => `${o.number ?? o.id} · ${o.customerName ?? ''}`}
            value={invoice}
            onChange={(_, v) => void onInvoicePick(v)}
            onInputChange={(_, v, inputReason) => {
              if (inputReason === 'input') setInvoiceSearch(v);
            }}
            filterOptions={(o) => o}
            loading={invoices.isFetching}
            isOptionEqualToValue={(a, b) => a.id === b.id}
            disabled={readOnly}
            renderInput={(params) => (
              <TextField {...params} label={t('phase1.sourceInvoice')} required />
            )}
          />
        ) : (
          <Paper sx={{ p: 2 }}>
            <Typography variant="body2" color="text.secondary">
              {t('phase1.sourceInvoice')}
            </Typography>
            <Typography variant="subtitle1">
              {existing.data?.invoiceNumber ?? invoice?.number ?? invoice?.id}
            </Typography>
          </Paper>
        )}

        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
          <TextField
            type="date"
            label={t('common.date')}
            value={noteDate}
            onChange={(e) => setNoteDate(e.target.value)}
            disabled={readOnly}
            InputLabelProps={{ shrink: true }}
            inputProps={{
              ...(invoiceDate ? { min: invoiceDate } : {}),
              ...(creditDeadline ? { max: creditDeadline } : {}),
            }}
            error={!readOnly && Boolean(dateProblem)}
            helperText={!readOnly ? dateProblem : undefined}
            sx={{ minWidth: 180 }}
          />
          <NoteReasonSelect
            value={reason}
            onChange={setReason}
            disabled={readOnly || isAutoReturnNote}
            allowSalesReturn={isAutoReturnNote}
          />
        </Stack>

        {reason === 'OTHERS' ? (
          <TextField
            label={t('phase1.reasonDetail')}
            value={reasonDetail}
            onChange={(e) => setReasonDetail(e.target.value)}
            disabled={readOnly}
            fullWidth
          />
        ) : null}

        <TextField
          label={t('billing.addNotes')}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          disabled={readOnly}
          multiline
          minRows={2}
          fullWidth
        />

        <Typography variant="subtitle1">{t('billing.lines')}</Typography>
        {kind === 'credit' && !readOnly ? (
          <Button size="small" variant="outlined" onClick={() => setLines((prev) => prefillReturnLines(prev, true))}>
            {t('phase1.creditFullInvoice')}
          </Button>
        ) : null}
        <InvoiceSourceLineTable
          lines={lines}
          onChange={setLines}
          intraState={intraState}
          readOnly={readOnly}
          availableToAdd={pool}
          allowOverCap
          showHsn
        />

        {/* CN-04 / DN-05: freight, handling or interest that is not a product line. */}
        {!readOnly || chargesAmount > 0 ? (
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
            <TextField
              type="number"
              label={t('phase1.additionalCharges')}
              value={additionalCharges}
              onChange={(e) => setAdditionalCharges(e.target.value)}
              disabled={readOnly}
              inputProps={{ min: 0, step: 'any' }}
              InputLabelProps={{ shrink: true }}
              sx={{ minWidth: 180 }}
            />
            {chargesAmount > 0 ? (
              <>
                <TextField
                  label={t('phase1.chargesHsn')}
                  value={chargesHsn}
                  onChange={(e) => setChargesHsn(e.target.value)}
                  disabled={readOnly}
                  sx={{ minWidth: 160 }}
                />
                <TextField
                  select
                  label={t('phase1.chargesGstRate')}
                  value={chargesGstRate || '0'}
                  onChange={(e) => setChargesGstRate(e.target.value)}
                  disabled={readOnly}
                  sx={{ minWidth: 140 }}
                >
                  {['0', '5', '12', '18', '28'].map((r) => (
                    <MenuItem key={r} value={r}>
                      {r}%
                    </MenuItem>
                  ))}
                </TextField>
              </>
            ) : null}
          </Stack>
        ) : null}

        {!isCredit && !readOnly && user && isOwner(user.role) ? (
          <Stack spacing={1}>
            <FormControlLabel
              control={
                <Checkbox
                  checked={allowExcessDebit}
                  onChange={(e) => setAllowExcessDebit(e.target.checked)}
                />
              }
              label={t('phase1.allowExcessDebit')}
            />
            {allowExcessDebit ? (
              <TextField
                label={t('phase1.excessDebitReason')}
                value={excessDebitReason}
                onChange={(e) => setExcessDebitReason(e.target.value)}
                required
                fullWidth
              />
            ) : null}
          </Stack>
        ) : null}

        <SimpleTotalsPanel totals={preview.totals ?? totals} />
      </Stack>
    </DocumentEditorShell>
    </>
  );
}
