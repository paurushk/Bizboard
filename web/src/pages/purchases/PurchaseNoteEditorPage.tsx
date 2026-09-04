import { useEffect, useMemo, useRef, useState } from 'react';
import Autocomplete from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
import IconButton from '@mui/material/IconButton';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import DeleteIcon from '@mui/icons-material/Delete';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import {
  cancelPurchaseCreditNote,
  cancelPurchaseDebitNote,
  completePurchaseCreditNote,
  completePurchaseDebitNote,
  createPurchaseCreditNote,
  createPurchaseDebitNote,
  getCompany,
  getPurchase,
  getPurchaseCreditNote,
  getPurchaseDebitNote,
  listPurchases,
  listSuppliers,
  updatePurchaseCreditNote,
  updatePurchaseDebitNote,
} from '@/api/resources';
import {
  DocumentEditorShell,
  NoteReasonSelect,
  NumericField,
  SimpleTotalsPanel,
  makeLine,
  primarySaveAction,
  recomputeLine,
  todayIso,
  useBillingSaveFeedback,
  type DraftLine,
} from '@/components/billing';
import { ErrorState, LoadingState } from '@/components/PageState';
import { UnsavedChangesGuard } from '@/components/UnsavedChangesGuard';
import { StatusChip } from '@/components/StatusChip';
import { useProductCfFilters } from '@/hooks/useProductCfFilters';
import { useProductSearch } from '@/hooks/useProductSearch';
import { t } from '@/i18n';
import { usePreviewTotals } from '@/hooks/usePreviewTotals';
import { useAuth } from '@/auth/AuthContext';
import { canCancelDocuments, canCreatePurchases } from '@/utils/permissions';
import type { NoteReason, Product, PurchaseCreditNote, PurchaseDebitNote, PurchaseInvoice, Supplier } from '@/types/domain';
import { calculateInvoiceTotals, calculateLineTax, isIntraState } from '@/utils/tax';
import { documentStatusTone, statusLabelKey } from '@/utils/status';
import { toNumber } from '@/utils/money';

type NoteKind = 'credit' | 'debit';

export function PurchaseNoteEditorPage({ kind }: { kind: NoteKind }) {
  const isCredit = kind === 'credit';
  const listPath = isCredit ? '/purchases/credit-notes' : '/purchases/debit-notes';
  const queryKey = isCredit ? 'purchase-credit-notes' : 'purchase-debit-notes';

  const { user } = useAuth();
  const canWrite = canCreatePurchases(user);
  const canCancel = canCancelDocuments(user);
  const { id: editIdParam } = useParams();
  const editId = editIdParam ? Number(editIdParam) : null;
  const isEdit = Number.isFinite(editId) && (editId as number) > 0;
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { message, error, clearFeedback, flashError, setMessage } = useBillingSaveFeedback();

  const [loaded, setLoaded] = useState(false);
  // F2-041: suppress UnsavedChangesGuard for the programmatic navigate() after
  // a deliberate save/cancel — those aren't "discarding" anything.
  const skipLeaveGuard = useRef(false);
  const [editingStatus, setEditingStatus] = useState<string | null>(null);
  const [supplierId, setSupplierId] = useState<number | ''>('');
  const [purchaseInvoiceId, setPurchaseInvoiceId] = useState<number | ''>('');
  const [supplierNoteNumber, setSupplierNoteNumber] = useState('');
  const [noteDate, setNoteDate] = useState(todayIso());
  const [reason, setReason] = useState<NoteReason>('CORRECTION_OF_INVOICE');
  const [reasonDetail, setReasonDetail] = useState('');
  const [notes, setNotes] = useState('');
  const [lines, setLines] = useState<DraftLine[]>([]);
  const [pendingProduct, setPendingProduct] = useState<Product | null>(null);
  const [pendingQty, setPendingQty] = useState('1');

  const company = useQuery({ queryKey: ['company'], queryFn: getCompany });
  const suppliers = useQuery({ queryKey: ['suppliers'], queryFn: listSuppliers });
  const purchases = useQuery({ queryKey: ['purchases', 'completed'], queryFn: () => listPurchases({ status: 'COMPLETED' }) });
  const cf = useProductCfFilters();
  const productSearch = useProductSearch({ activeOnly: true, selected: pendingProduct, cf: cf.cfFilters });
  const existing = useQuery({
    queryKey: [queryKey, editId],
    queryFn: () => (isCredit ? getPurchaseCreditNote(editId as number) : getPurchaseDebitNote(editId as number)),
    enabled: isEdit,
  });

  const readOnly = editingStatus != null && editingStatus !== 'DRAFT';
  const selectedSupplier = suppliers.data?.find((s) => s.id === Number(supplierId));
  const intraState = isIntraState(
    company.data?.gstin || company.data?.state,
    selectedSupplier?.gstin || selectedSupplier?.state,
  );

  useEffect(() => {
    setLoaded(false);
    clearFeedback();
  }, [editId, clearFeedback]);

  useEffect(() => {
    if (!existing.data || loaded) return;
    const doc = existing.data;
    setEditingStatus(doc.status);
    setSupplierId(doc.supplier);
    setPurchaseInvoiceId(doc.purchaseInvoice ?? '');
    setSupplierNoteNumber(doc.supplierNoteNumber ?? '');
    setNoteDate(doc.noteDate);
    setReason(doc.reason);
    setReasonDetail(doc.reasonDetail ?? '');
    setNotes(doc.notes ?? '');
    setLines(
      (doc.items ?? []).map((item, idx) => {
        const qty = toNumber(item.quantity);
        const unitPrice = toNumber(item.unitPrice);
        const tax = calculateLineTax({
          quantity: qty,
          unitPrice,
          gstRate: toNumber(item.gstRate),
          cessRate: toNumber(item.cessRate),
          intraState,
        });
        return {
          key: `edit-${item.id ?? idx}`,
          lineId: item.id,
          product: item.product,
          productName: item.productName ?? '',
          description: '',
          sku: '',
          hsnCode: '',
          unitName: item.unitName ?? 'PCS',
          sourceItemId: item.sourceItem ?? item.id,
          batchNo: '',
          expDate: '',
          mfgDate: '',
          mrp: 0,
          quantity: qty,
          maxQty: qty,
          unitPrice,
          gstRate: toNumber(item.gstRate),
          cessRate: toNumber(item.cessRate),
          ...tax,
          discountAmount: 0,
        };
      }),
    );
    setLoaded(true);
    // F2-040: intentionally NOT keyed on intraState — see the effect below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [existing.data, loaded]);

  // F2-040: suppliers.data (and so intraState) may not have loaded yet at
  // hydration time, leaving every line at zero tax; also covers switching the
  // supplier after lines already exist, which otherwise leaves them stale.
  useEffect(() => {
    if (!loaded) return;
    setLines((prev) => prev.map((line) => ({ ...recomputeLine(line, intraState), discountAmount: 0 })));
  }, [intraState, loaded]);

  const onPurchasePick = async (pur: PurchaseInvoice | null) => {
    setPurchaseInvoiceId(pur?.id ?? '');
    if (!pur) return;
    setSupplierId(pur.supplier);
    const full = pur.items?.length ? pur : await getPurchase(pur.id);
    setLines(
      (full.items ?? []).map((item, idx) => {
        const qty = toNumber(item.quantity);
        const unitPrice = toNumber(item.unitPrice);
        const tax = calculateLineTax({
          quantity: qty,
          unitPrice,
          gstRate: toNumber(item.gstRate),
          cessRate: toNumber(item.cessRate),
          intraState,
        });
        return {
          key: `pur-${idx}`,
          product: item.product,
          productName: item.productName ?? '',
          description: '',
          sku: '',
          hsnCode: '',
          unitName: item.unitName ?? 'PCS',
          sourceItemId: item.id,
          batchNo: '',
          expDate: '',
          mfgDate: '',
          mrp: 0,
          quantity: qty,
          maxQty: qty,
          unitPrice,
          gstRate: toNumber(item.gstRate),
          cessRate: toNumber(item.cessRate),
          ...tax,
          discountAmount: 0,
        };
      }),
    );
  };

  const lineTaxes = useMemo(
    () =>
      lines.map((l) =>
        calculateLineTax({
          quantity: l.quantity,
          unitPrice: l.unitPrice,
          gstRate: l.gstRate,
          cessRate: l.cessRate ?? 0,
          intraState,
        }),
      ),
    [lines, intraState],
  );
  const totals = useMemo(
    () => calculateInvoiceTotals(lineTaxes.map((l) => ({ ...l, intraState })), { applyRoundOff: true }),
    [lineTaxes, intraState],
  );

  // F2-012: at least one line must carry a positive quantity, and it must be
  // within the source purchase quantity.
  const effectiveLines = lines.filter((l) => Number(l.quantity) > 0);
  const anyOverCap = lines.some(
    (l) => l.maxQty != null && Number(l.quantity) > l.maxQty + 1e-9,
  );
  const canSave =
    Boolean(supplierId) && effectiveLines.length > 0 && !anyOverCap && canWrite;
  const primarySave = primarySaveAction({ isEdit, editingStatus });

  const addLine = () => {
    if (!pendingProduct) return;
    const qty = Math.max(1, Math.floor(Number(pendingQty)) || 1);
    setLines((prev) => [...prev, makeLine(pendingProduct, intraState, qty, 'purchasePrice')]);
    setPendingProduct(null);
    setPendingQty('1');
  };

  const buildPayload = () => ({
    supplier: Number(supplierId),
    purchaseInvoice: purchaseInvoiceId ? Number(purchaseInvoiceId) : null,
    supplierNoteNumber,
    noteDate,
    reason,
    reasonDetail: reason === 'OTHERS' ? reasonDetail : '',
    notes,
    // F2-012: never send zero-qty lines.
    items: lines
      .filter((l) => Number(l.quantity) > 0)
      .map((l) => ({
        ...(l.lineId != null ? { id: l.lineId } : {}),
        product: l.product,
        quantity: l.quantity,
        unitPrice: l.unitPrice,
        gstRate: l.gstRate,
        cessRate: l.cessRate ?? 0,
        sourceItem: l.sourceItemId ?? null,
      })),
  });

  const previewOnline = typeof navigator === 'undefined' || navigator.onLine;
  const preview = usePreviewTotals(
    'purchase',
    previewOnline && supplierId && lines.length > 0
      ? {
          supplier: Number(supplierId),
          items: lines.map((l) => ({
            product: l.product,
            quantity: l.quantity,
            unitPrice: l.unitPrice,
            gstRate: l.gstRate,
            cessRate: l.cessRate ?? 0,
          })),
        }
      : null,
  );

  const saveMutation = useMutation({
    mutationFn: async (mode: 'draft' | 'complete') => {
      const payload = buildPayload();
      let doc: PurchaseCreditNote | PurchaseDebitNote;
      if (isEdit && editId) {
        doc = isCredit ? await updatePurchaseCreditNote(editId, payload) : await updatePurchaseDebitNote(editId, payload);
      } else {
        doc = isCredit ? await createPurchaseCreditNote(payload) : await createPurchaseDebitNote(payload);
      }
      if (mode === 'complete' && doc.status === 'DRAFT') {
        doc = isCredit ? await completePurchaseCreditNote(doc.id) : await completePurchaseDebitNote(doc.id);
      }
      return doc;
    },
    onSuccess: (doc) => {
      setMessage(t('phase1.saved'));
      void qc.invalidateQueries({ queryKey: [queryKey] });
      if (!isEdit) {
        skipLeaveGuard.current = true;
        void navigate(`${listPath}/${doc.id}`, { replace: true });
      } else {
        setEditingStatus(doc.status);
      }
    },
    onError: (err) => flashError(getErrorMessage(err)),
  });

  const cancelMutation = useMutation({
    mutationFn: () => (isCredit ? cancelPurchaseCreditNote(editId as number) : cancelPurchaseDebitNote(editId as number)),
    onSuccess: () => {
      skipLeaveGuard.current = true;
      void navigate(listPath);
    },
    onError: (err) => flashError(getErrorMessage(err)),
  });

  if (isEdit && existing.isLoading) return <LoadingState />;
  if (isEdit && existing.isError) {
    return <ErrorState message={getErrorMessage(existing.error)} error={existing.error} onRetry={() => void existing.refetch()} />;
  }

  const completedPurchases = (purchases.data ?? []).filter((p) => p.status === 'COMPLETED');

  return (
    <DocumentEditorShell
      title={t(isEdit ? (isCredit ? 'phase1.editPurchaseCreditNote' : 'phase1.editPurchaseDebitNote') : (isCredit ? 'phase1.newPurchaseCreditNote' : 'phase1.newPurchaseDebitNote'))}
      primarySave={primarySave}
      canSave={canSave}
      canComplete={canSave && (!previewOnline || preview.ready)}
      isEdit={isEdit}
      backTo={listPath}
      message={message}
      error={error || preview.error}
      saving={saveMutation.isPending}
      hideSaveAndNew
      showDraftButton={!readOnly}
      onPrimarySave={() => saveMutation.mutate(primarySave.mode === 'complete' ? 'complete' : 'draft')}
      onDraft={() => saveMutation.mutate('draft')}
      extraActions={
        readOnly && editingStatus === 'COMPLETED' && canCancel ? (
          <Button color="warning" size="small" disabled={cancelMutation.isPending} onClick={() => cancelMutation.mutate()}>
            {t('phase1.cancelDocument')}
          </Button>
        ) : editingStatus && editingStatus !== 'DRAFT' ? (
          <StatusChip tone={documentStatusTone(editingStatus)} labelKey={statusLabelKey(editingStatus)} />
        ) : null
      }
    >
      <UnsavedChangesGuard when={!skipLeaveGuard.current && (effectiveLines.length > 0 || Boolean(supplierId))} />
      <Stack spacing={2}>
        <Autocomplete
          options={suppliers.data ?? []}
          getOptionLabel={(o: Supplier) => o.name}
          value={suppliers.data?.find((s) => s.id === Number(supplierId)) ?? null}
          onChange={(_, v) => setSupplierId(v?.id ?? '')}
          disabled={readOnly}
          renderInput={(params) => <TextField {...params} label={t('billing.supplier')} required />}
        />
        {!isEdit ? (
          <Autocomplete
            options={completedPurchases}
            getOptionLabel={(o) => `${o.number ?? o.id} · ${o.supplierName ?? ''}`}
            value={completedPurchases.find((p) => p.id === Number(purchaseInvoiceId)) ?? null}
            onChange={(_, v) => void onPurchasePick(v)}
            disabled={readOnly}
            renderInput={(params) => <TextField {...params} label={t('phase1.optionalPurchaseInvoice')} />}
          />
        ) : null}
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
          <TextField type="date" label={t('common.date')} value={noteDate} onChange={(e) => setNoteDate(e.target.value)} disabled={readOnly} InputLabelProps={{ shrink: true }} />
          <TextField label={t('phase1.supplierNoteNumber')} value={supplierNoteNumber} onChange={(e) => setSupplierNoteNumber(e.target.value)} disabled={readOnly} />
          <NoteReasonSelect value={reason} onChange={setReason} disabled={readOnly} />
        </Stack>
        {reason === 'OTHERS' ? (
          <TextField label={t('phase1.reasonDetail')} value={reasonDetail} onChange={(e) => setReasonDetail(e.target.value)} disabled={readOnly} fullWidth />
        ) : null}
        <TextField label={t('billing.addNotes')} value={notes} onChange={(e) => setNotes(e.target.value)} disabled={readOnly} multiline minRows={2} fullWidth />

        <Typography variant="subtitle1">{t('billing.lines')}</Typography>
        <Paper sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('nav.products')}</TableCell>
                <TableCell align="right">{t('billing.qty')}</TableCell>
                <TableCell align="right">{t('billing.priceShort')}</TableCell>
                {!readOnly ? <TableCell /> : null}
              </TableRow>
            </TableHead>
            <TableBody>
              {lines.map((l) => (
                <TableRow key={l.key}>
                  <TableCell>{l.productName}</TableCell>
                  <TableCell align="right">
                    {!readOnly ? (
                      <NumericField
                        size="small"
                        value={l.quantity}
                        min={0}
                        onValueChange={(v: number) =>
                          setLines((prev) =>
                            prev.map((x) =>
                              x.key === l.key
                                ? {
                                    ...x,
                                    // F2-012: clamp to (0, source quantity].
                                    quantity: Math.min(
                                      Math.max(0, v),
                                      x.maxQty ?? Number.POSITIVE_INFINITY,
                                    ),
                                  }
                                : x,
                            ),
                          )
                        }
                        helperText={l.maxQty != null ? `max ${l.maxQty}` : undefined}
                        sx={{ width: 100 }}
                      />
                    ) : (
                      l.quantity
                    )}
                  </TableCell>
                  <TableCell align="right">
                    {!readOnly ? (
                      <NumericField
                        size="small"
                        value={l.unitPrice}
                        onValueChange={(v: number) =>
                          setLines((prev) =>
                            prev.map((x) => (x.key === l.key ? { ...x, unitPrice: v } : x)),
                          )
                        }
                        sx={{ width: 120 }}
                      />
                    ) : (
                      l.unitPrice
                    )}
                  </TableCell>
                  {!readOnly ? (
                    <TableCell align="right">
                      <IconButton size="small" onClick={() => setLines((prev) => prev.filter((x) => x.key !== l.key))}>
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </TableCell>
                  ) : null}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
        {!readOnly ? (
          <Stack spacing={1}>
            {cf.filterBar}
          <Stack direction="row" spacing={1} alignItems="center">
            <Autocomplete
              sx={{ flex: 1 }}
              options={productSearch.options}
              loading={productSearch.isFetching}
              filterOptions={(opts) => opts}
              inputValue={productSearch.productQuery}
              onInputChange={(_, v, reason) => {
                if (reason === 'input' || reason === 'clear') productSearch.setProductQuery(v);
              }}
              getOptionLabel={(o) => `${o.name} · ${o.sku}`}
              value={pendingProduct}
              onChange={(_, v) => setPendingProduct(v)}
              renderInput={(params) => (
                <TextField
                  {...params}
                  label={t('nav.products')}
                  helperText={productSearch.helperText}
                />
              )}
            />
            <TextField type="number" label={t('billing.qty')} value={pendingQty} onChange={(e) => setPendingQty(e.target.value)} sx={{ width: 100 }} />
            <Button variant="outlined" disabled={!pendingProduct} onClick={addLine}>{t('common.add')}</Button>
          </Stack>
          </Stack>
        ) : null}
        <SimpleTotalsPanel totals={preview.totals ?? totals} />
      </Stack>
    </DocumentEditorShell>
  );
}
