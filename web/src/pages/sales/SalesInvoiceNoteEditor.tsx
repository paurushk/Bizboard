import { useEffect, useMemo, useState } from 'react';
import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import {
  cancelSalesCreditNote,
  cancelSalesDebitNote,
  completeSalesCreditNote,
  completeSalesDebitNote,
  createSalesCreditNote,
  createSalesDebitNote,
  downloadSalesDocumentPdf,
  getCompany,
  getSalesCreditNote,
  getSalesCreditNoteAdjustableSummary,
  getSalesDebitNote,
  getSalesInvoice,
  listCustomers,
  listSalesInvoices,
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
import { PdfStatusPoller } from '@/components/PdfStatusPoller';
import { StatusChip } from '@/components/StatusChip';
import { t } from '@/i18n';
import type { NoteReason, SalesCreditNote, SalesDebitNote, SalesInvoice } from '@/types/domain';
import { calculateInvoiceTotals, calculateLineTax, isIntraState } from '@/utils/tax';
import { documentStatusTone, statusLabelKey } from '@/utils/status';
import { formatMoney } from '@/utils/money';

type NoteKind = 'credit' | 'debit';

export function SalesInvoiceNoteEditor({ kind }: { kind: NoteKind }) {
  const isCredit = kind === 'credit';
  const listPath = isCredit ? '/sales/credit-notes' : '/sales/debit-notes';
  const queryKey = isCredit ? 'sales-credit-notes' : 'sales-debit-notes';

  const { id: editIdParam } = useParams();
  const editId = editIdParam ? Number(editIdParam) : null;
  const isEdit = Number.isFinite(editId) && (editId as number) > 0;
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { message, error, clearFeedback, flashError, setMessage } = useBillingSaveFeedback();

  const [loaded, setLoaded] = useState(false);
  const [editingStatus, setEditingStatus] = useState<string | null>(null);
  const [invoice, setInvoice] = useState<SalesInvoice | null>(null);
  const [noteDate, setNoteDate] = useState(todayIso());
  const [reason, setReason] = useState<NoteReason>('CORRECTION_OF_INVOICE');
  const [reasonDetail, setReasonDetail] = useState('');
  const [notes, setNotes] = useState('');
  const [lines, setLines] = useState<InvoiceSourceLine[]>([]);
  const [pool, setPool] = useState<InvoiceSourceLine[]>([]);

  const company = useQuery({ queryKey: ['company'], queryFn: getCompany });
  const customers = useQuery({ queryKey: ['customers'], queryFn: () => listCustomers() });
  const invoices = useQuery({
    queryKey: ['completed-sales'],
    queryFn: () => listSalesInvoices({ status: 'COMPLETED' }),
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

  const readOnly = editingStatus != null && editingStatus !== 'DRAFT';

  useEffect(() => {
    setLoaded(false);
    clearFeedback();
  }, [editId, clearFeedback]);

  useEffect(() => {
    if (!existing.data || loaded) return;
    const doc = existing.data;
    setEditingStatus(doc.status);
    setNoteDate(doc.noteDate);
    setReason(doc.reason);
    setReasonDetail(doc.reasonDetail ?? '');
    setNotes(doc.notes ?? '');
    void getSalesInvoice(doc.salesInvoice).then((inv) => {
      setInvoice(inv);
      setLines(noteItemsToSourceLines(doc.items, inv.items));
      setPool(invoiceItemsToSourceLines(inv.items));
    });
    setLoaded(true);
  }, [existing.data, loaded]);

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
    setLines([]);
  };

  const partyState = invoice?.customer
    ? customers.data?.find((c) => c.id === invoice.customer)?.gstin
      || customers.data?.find((c) => c.id === invoice.customer)?.state
    : undefined;

  const intraState = isIntraState(
    company.data?.gstin || company.data?.state,
    partyState,
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

  const totals = useMemo(
    () => calculateInvoiceTotals(lineTaxes.map((l) => ({ ...l, intraState })), { applyRoundOff: true }),
    [lineTaxes, intraState],
  );

  const canSave = Boolean(invoice) && activeSourceLines(lines).length > 0;
  const primarySave = primarySaveAction({ isEdit, editingStatus });

  const buildPayload = () => ({
    customer: invoice!.customer,
    salesInvoice: invoice!.id,
    noteDate,
    reason,
    reasonDetail: reason === 'OTHERS' ? reasonDetail : '',
    notes,
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

  const saveMutation = useMutation({
    mutationFn: async (mode: 'draft' | 'complete') => {
      if (!invoice) throw new Error(t('phase1.selectInvoice'));
      const payload = buildPayload();
      let doc: SalesCreditNote | SalesDebitNote;
      if (isEdit && editId) {
        doc = isCredit
          ? await updateSalesCreditNote(editId, payload)
          : await updateSalesDebitNote(editId, payload);
      } else {
        doc = isCredit
          ? await createSalesCreditNote(payload)
          : await createSalesDebitNote(payload);
      }
      if (mode === 'complete' && doc.status === 'DRAFT') {
        doc = isCredit
          ? await completeSalesCreditNote(doc.id)
          : await completeSalesDebitNote(doc.id);
      }
      return doc;
    },
    onSuccess: (doc) => {
      setMessage(t('phase1.saved'));
      void qc.invalidateQueries({ queryKey: [queryKey] });
      if (!isEdit) {
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
      void qc.invalidateQueries({ queryKey: [queryKey] });
      void navigate(listPath);
    },
    onError: (err) => flashError(getErrorMessage(err)),
  });

  if (isEdit && existing.isLoading) return <LoadingState />;
  if (isEdit && existing.isError) {
    return (
      <ErrorState message={getErrorMessage(existing.error)} onRetry={() => void existing.refetch()} />
    );
  }

  const infoBanner =
    isCredit && summary.data && invoice ? (
      <Alert severity="info">
        {t('phase1.invoiceOutstanding')}: {formatMoney(summary.data.outstanding)} /{' '}
        {formatMoney(summary.data.grandTotal)}
      </Alert>
    ) : null;

  return (
    <DocumentEditorShell
      title={t(isEdit ? (isCredit ? 'phase1.editCreditNote' : 'phase1.editDebitNote') : (isCredit ? 'phase1.newCreditNote' : 'phase1.newDebitNote'))}
      primarySave={primarySave}
      canSave={canSave}
      canComplete={canSave}
      isEdit={isEdit}
      backTo={listPath}
      message={message}
      error={error}
      infoBanner={infoBanner}
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
          {readOnly && editingStatus === 'COMPLETED' ? (
            <Button color="warning" size="small" disabled={cancelMutation.isPending} onClick={() => cancelMutation.mutate()}>
              {t('phase1.cancelDocument')}
            </Button>
          ) : editingStatus && editingStatus !== 'DRAFT' ? (
            <StatusChip tone={documentStatusTone(editingStatus)} labelKey={statusLabelKey(editingStatus)} />
          ) : null}
        </>
      }
    >
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
            sx={{ minWidth: 180 }}
          />
          <NoteReasonSelect value={reason} onChange={setReason} disabled={readOnly} />
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
        <InvoiceSourceLineTable
          lines={lines}
          onChange={setLines}
          intraState={intraState}
          readOnly={readOnly}
          availableToAdd={pool}
        />

        <SimpleTotalsPanel totals={totals} />
      </Stack>
    </DocumentEditorShell>
  );
}
