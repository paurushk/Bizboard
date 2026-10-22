import { useEffect, useMemo, useRef, useState } from 'react';
import { UnsavedChangesGuard } from '@/components/UnsavedChangesGuard';
import { returnDialogDirty } from '@/pages/moneyFormDirty';
import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import CircularProgress from '@mui/material/CircularProgress';
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
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink, useSearchParams } from 'react-router-dom';
import { getErrorMessage, userGestureIdempotencyKey } from '@/api/client';
import { confirmAction } from '@/utils/confirmBridge';
import {
  cancelPurchaseReturn,
  completePurchaseReturn,
  createPurchaseReturn,
  deletePurchaseReturn,
  getPurchase,
  getPurchaseReturn,
  getPurchaseReturnableLines,
  listProducts,
  listPurchaseReturnsPage,
  listPurchasesPage,
  previewPurchaseReturnTotals,
  updatePurchaseReturn,
} from '@/api/resources';
import {
  InvoiceReturnLineTable,
  activeSourceLines,
  formatSerialNumbersText,
  hasSerialPickList,
  invoiceItemsToSourceLines,
  sourceLineReturnPayload,
  todayIso,
  useDebouncedValue,
  type InvoiceSourceLine,
} from '@/components/billing';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { StatusChip } from '@/components/StatusChip';
import { PageTitle } from '@/contextHelp';
import { t } from '@/i18n';
import type { PurchaseInvoice, PurchaseReturn } from '@/types/domain';
import { formatMoney, toNumber } from '@/utils/money';
import { canCancelDocuments, canCreatePurchases } from '@/utils/permissions';
import { useAuth } from '@/auth/AuthContext';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { documentStatusTone, statusLabelKey } from '@/utils/status';
import { returnCompleteDisabledReason, serialCountMatchesQty } from '@/completeGates/completeBlockers';

const PAGE_SIZE = 50;

type StatusFilter = 'ALL' | 'DRAFT' | 'COMPLETED' | 'CANCELLED';

export function PurchaseReturnsPage() {
  const { user } = useAuth();
  const { writesBlocked } = useSubscriptionGate();
  const canWrite = canCreatePurchases(user) && !writesBlocked;
  const canCancelReturn = canCancelDocuments(user) && !writesBlocked;
  const qc = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('ALL');
  const [searchTerm, setSearchTerm] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const debouncedSearch = useDebouncedValue(searchTerm, 250);
  const dateRangeInvalid = Boolean(dateFrom && dateTo && dateFrom > dateTo);
  const filtersActive =
    statusFilter !== 'ALL' || Boolean(searchTerm.trim()) || Boolean(dateFrom) || Boolean(dateTo);

  const query = useQuery({
    queryKey: ['purchase-returns', page, statusFilter, debouncedSearch.trim(), dateFrom, dateTo],
    enabled: !dateRangeInvalid,
    queryFn: () =>
      listPurchaseReturnsPage({
        page,
        pageSize: PAGE_SIZE,
        ...(statusFilter !== 'ALL' ? { status: statusFilter } : {}),
        ...(debouncedSearch.trim() ? { q: debouncedSearch.trim() } : {}),
        ...(dateFrom ? { date_from: dateFrom } : {}),
        ...(dateTo ? { date_to: dateTo } : {}),
      }),
  });
  const [purchaseSearch, setPurchaseSearch] = useState('');
  const debouncedPurchaseSearch = useDebouncedValue(purchaseSearch, 250);
  const purchases = useQuery({
    queryKey: ['purchases', debouncedPurchaseSearch],
    queryFn: async () => {
      const res = await listPurchasesPage({
        q: debouncedPurchaseSearch.trim() || undefined,
        pageSize: PAGE_SIZE,
      });
      return res.results;
    },
  });

  const returns = query.data?.results ?? [];

  const [open, setOpen] = useState(false);
  const [purchase, setPurchase] = useState<PurchaseInvoice | null>(null);
  const [loadingLines, setLoadingLines] = useState(false);
  const [lines, setLines] = useState<InvoiceSourceLine[]>([]);
  const [returnDate, setReturnDate] = useState<string>(() => todayIso());
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [draftId, setDraftId] = useState<number | null>(null);
  const [isExistingDraft, setIsExistingDraft] = useState(false);
  const [gestureKey, setGestureKey] = useState<string | null>(null);
  // Every purchase/draft load takes a ticket; a slower, older response is dropped.
  const loadSeq = useRef(0);

  const [detailReturn, setDetailReturn] = useState<PurchaseReturn | null>(null);

  // Show the return as it is on the server now, not the (possibly stale) list row.
  const detailQuery = useQuery({
    queryKey: ['purchase-return-detail', detailReturn?.id],
    queryFn: () => getPurchaseReturn(detailReturn!.id),
    enabled: Boolean(detailReturn),
    staleTime: 0,
    retry: false,
  });
  const detail = detailQuery.data ?? detailReturn;
  const [confirmCancelReturn, setConfirmCancelReturn] = useState<PurchaseReturn | null>(null);
  const [confirmDeleteDraft, setConfirmDeleteDraft] = useState<PurchaseReturn | null>(null);
  const [discardPrompt, setDiscardPrompt] = useState(false);

  const returnDirty = returnDialogDirty(open, Boolean(purchase), reason);

  const products = useQuery({
    queryKey: ['products'],
    queryFn: () => listProducts(),
    staleTime: 60_000,
  });

  const invalidateAfterReturnLifecycle = () => {
    for (const key of [
      'purchase-returns',
      'purchase-credit-notes',
      'purchases',
      'purchase',
      'products',
      'stock-balance',
      'stock',
      'suppliers',
      'dashboard',
    ]) {
      void qc.invalidateQueries({ queryKey: [key] });
    }
  };

  const loadPurchaseLines = async (
    pur: PurchaseInvoice,
  ): Promise<{ full: PurchaseInvoice; sourceLines: InvoiceSourceLine[] }> => {
    const full = pur.items?.length ? pur : await getPurchase(pur.id);
    const catalog = products.data?.length ? products.data : await listProducts();
    const byId = new Map(catalog.map((p) => [p.id, p]));
    // The server owns the headroom (completed returns, standalone credit notes, unit
    // conversion) and which serials already went back. If it cannot be loaded we say
    // so rather than guess.
    const returnable = await getPurchaseReturnableLines(full.id);
    return {
      full,
      sourceLines: invoiceItemsToSourceLines(full.items, undefined, byId, undefined, returnable),
    };
  };

  const resetDialog = () => {
    loadSeq.current += 1;
    setPurchase(null);
    setLoadingLines(false);
    setLines([]);
    setReturnDate(todayIso());
    setReason('');
    setDraftId(null);
    setIsExistingDraft(false);
    setGestureKey(null);
    setError(null);
  };

  const requestClose = () => {
    if (returnDirty) setDiscardPrompt(true);
    else {
      setOpen(false);
      resetDialog();
    }
  };

  const onPurchasePick = async (pur: PurchaseInvoice | null) => {
    const seq = ++loadSeq.current;
    // Switching bills after an implicit draft (left by a failed Complete) must not
    // patch the new bill's lines onto the old bill's draft.
    if (draftId !== null && !isExistingDraft && pur?.id !== purchase?.id) {
      const staleDraftId = draftId;
      setDraftId(null);
      setGestureKey(null);
      void deletePurchaseReturn(staleDraftId).catch(() => {});
    }
    setPurchase(pur);
    if (!pur) {
      setLines([]);
      setLoadingLines(false);
      return;
    }
    setLoadingLines(true);
    setLines([]);
    try {
      const { full, sourceLines } = await loadPurchaseLines(pur);
      if (seq !== loadSeq.current) return;
      setPurchase(full);
      setLines(sourceLines);
    } catch (err) {
      if (seq === loadSeq.current) setError(getErrorMessage(err));
    } finally {
      if (seq === loadSeq.current) setLoadingLines(false);
    }
  };

  const onResumeDraft = async (row: PurchaseReturn) => {
    const seq = ++loadSeq.current;
    setError(null);
    setMessage(null);
    setDraftId(row.id);
    setIsExistingDraft(true);
    setGestureKey(null);
    setReturnDate(row.returnDate || todayIso());
    setReason(row.reason ?? '');
    setPurchase(null);
    setLines([]);
    setOpen(true);
    setLoadingLines(true);
    try {
      const draft = await getPurchaseReturn(row.id);
      const pur = await getPurchase(draft.purchaseInvoice);
      const { full, sourceLines } = await loadPurchaseLines(pur);
      if (seq !== loadSeq.current) return;
      setPurchase(full);
      setReturnDate(draft.returnDate || todayIso());
      setReason(draft.reason ?? '');
      const hydrated = sourceLines.map((src) => {
        const match = (draft.items ?? []).find((it) => it.product === src.product);
        if (!match) return src;
        let serials = match.serialNumbers ?? [];
        if (hasSerialPickList(src)) {
          serials = serials.filter((sn) => src.soldSerialNumbers!.includes(sn));
        }
        const quantity = hasSerialPickList(src) ? serials.length : toNumber(match.quantity);
        return {
          ...src,
          included: quantity > 0,
          quantity: Math.min(quantity, src.maxQty),
          condition: match.condition ?? 'SELLABLE',
          serialNumbersText: formatSerialNumbersText(serials),
        };
      });
      setLines(hydrated);
    } catch (err) {
      if (seq === loadSeq.current) setError(getErrorMessage(err));
    } finally {
      if (seq === loadSeq.current) setLoadingLines(false);
    }
  };

  // An inbound ?create=1 or ?purchase=<id> (the bill a lot came in on, from Expiry alerts) opens the
  // dialog; the effect below then strips the params and picks that bill.
  if ((searchParams.get('create') === '1' || searchParams.get('purchase')) && !open) setOpen(true);

  useEffect(() => {
    const wantsCreate = searchParams.get('create') === '1';
    const purchaseRaw = searchParams.get('purchase');
    if (!wantsCreate && !purchaseRaw) return;
    const next = new URLSearchParams(searchParams);
    next.delete('create');
    next.delete('purchase');
    setSearchParams(next, { replace: true });
    const id = Number(purchaseRaw);
    if (!Number.isFinite(id) || id <= 0) return;
    void getPurchase(id)
      .then((bill) => onPurchasePick(bill))
      .catch((err) => setError(getErrorMessage(err)));
    // Prefill once from the inbound query string; onPurchasePick is recreated each render and only
    // reads dialog state that is empty when the dialog was just opened.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams, setSearchParams]);

  const activeLines = useMemo(() => activeSourceLines(lines), [lines]);
  const missingSerialLine = useMemo(
    () => activeLines.find((l) => l.trackSerial && !serialCountMatchesQty(l.serialNumbersText, l.quantity)),
    [activeLines],
  );
  const returnDateBeforePurchase = Boolean(
    purchase?.invoiceDate && returnDate && returnDate < purchase.invoiceDate,
  );

  const itemsPayload = () =>
    activeLines.map((l) => sourceLineReturnPayload(l, { includeBatch: true, includeSourceItem: false }));

  // Exact credit-note totals from the server (it runs the real build and rolls it back),
  // debounced while the operator edits.
  const previewItems = useMemo(
    () =>
      missingSerialLine
        ? []
        : activeLines.map((l) => sourceLineReturnPayload(l, { includeBatch: true, includeSourceItem: false })),
    [activeLines, missingSerialLine],
  );
  const previewKey = JSON.stringify({ p: purchase?.id ?? null, d: returnDate, items: previewItems });
  const debouncedPreviewKey = useDebouncedValue(previewKey, 300);
  const preview = useQuery({
    queryKey: ['purchase-return-preview', debouncedPreviewKey],
    enabled:
      open &&
      Boolean(purchase) &&
      previewItems.length > 0 &&
      !returnDateBeforePurchase &&
      debouncedPreviewKey === previewKey,
    retry: false,
    staleTime: 0,
    queryFn: () =>
      previewPurchaseReturnTotals({
        supplier: purchase!.supplier,
        purchaseInvoice: purchase!.id,
        returnDate: returnDate || todayIso(),
        items: previewItems,
      }),
  });
  const previewData = preview.data;
  const previewGst = previewData
    ? previewData.cgstTotal + previewData.sgstTotal + previewData.igstTotal + previewData.cessTotal
    : 0;

  const saveDraftMutation = useMutation({
    mutationFn: async () => {
      if (!purchase) throw new Error(t('phase1.selectPurchaseInvoice'));
      if (activeLines.length === 0) throw new Error(t('phase1.selectInvoiceLines'));
      const key = gestureKey ?? userGestureIdempotencyKey();
      if (!gestureKey) setGestureKey(key);
      const items = itemsPayload();
      if (!draftId) {
        return createPurchaseReturn(
          {
            supplier: purchase.supplier,
            purchaseInvoice: purchase.id,
            returnDate: returnDate || todayIso(),
            reason,
            items,
          },
          { idempotencyKey: key },
        );
      }
      return updatePurchaseReturn(draftId, { returnDate: returnDate || todayIso(), reason, items });
    },
    onSuccess: () => {
      setOpen(false);
      setMessage(t('phase1.purchaseReturnDraftSaved'));
      resetDialog();
      invalidateAfterReturnLifecycle();
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const createMutation = useMutation({
    mutationFn: async () => {
      if (!purchase) throw new Error(t('phase1.selectPurchaseInvoice'));
      if (activeLines.length === 0) throw new Error(t('phase1.selectInvoiceLines'));
      const key = gestureKey ?? userGestureIdempotencyKey();
      if (!gestureKey) setGestureKey(key);
      const items = itemsPayload();
      let id = draftId;
      let completeKey = `${key}-complete`;
      if (!id) {
        const draft = await createPurchaseReturn(
          {
            supplier: purchase.supplier,
            purchaseInvoice: purchase.id,
            returnDate: returnDate || todayIso(),
            reason,
            items,
          },
          { idempotencyKey: key },
        );
        id = draft.id;
        setDraftId(id);
      } else {
        await updatePurchaseReturn(id, { returnDate: returnDate || todayIso(), reason, items });
        completeKey = `${userGestureIdempotencyKey()}-complete`;
      }
      return completePurchaseReturn(id, { idempotencyKey: completeKey });
    },
    onMutate: () => setError(null),
    onSuccess: () => {
      setOpen(false);
      setMessage(t('phase1.purchaseReturnCompleted'));
      resetDialog();
      invalidateAfterReturnLifecycle();
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const completeDraftMutation = useMutation({
    mutationFn: async (id: number) =>
      completePurchaseReturn(id, { idempotencyKey: `${userGestureIdempotencyKey()}-complete` }),
    onSuccess: () => {
      setMessage(t('phase1.purchaseReturnCompleted'));
      setError(null);
      invalidateAfterReturnLifecycle();
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const deleteDraftMutation = useMutation({
    mutationFn: async (id: number) => deletePurchaseReturn(id),
    onSuccess: () => {
      setConfirmDeleteDraft(null);
      setMessage(t('phase1.purchaseReturnDeleted'));
      setError(null);
      void qc.invalidateQueries({ queryKey: ['purchase-returns'] });
    },
    onError: (err) => {
      setConfirmDeleteDraft(null);
      setError(getErrorMessage(err));
    },
  });

  const cancelReturnMutation = useMutation({
    mutationFn: async (ret: PurchaseReturn) => cancelPurchaseReturn(ret.id),
    onSuccess: () => {
      setConfirmCancelReturn(null);
      setMessage(t('phase1.purchaseReturnCancelled'));
      setError(null);
      invalidateAfterReturnLifecycle();
    },
    onError: (err) => {
      setConfirmCancelReturn(null);
      setError(getErrorMessage(err));
    },
  });

  const completed = (purchases.data ?? []).filter((p) => p.status === 'COMPLETED');

  const openNewReturn = () => {
    resetDialog();
    setOpen(true);
  };

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <PageTitle>{t('nav.purchaseReturns')}</PageTitle>
        {canWrite ? (
          <Button variant="contained" onClick={openNewReturn}>
            {t('phase1.newPurchaseReturn')}
          </Button>
        ) : null}
      </Stack>

      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={1.5}
        alignItems={{ sm: 'center' }}
        flexWrap="wrap"
        useFlexGap
      >
        <TextField
          size="small"
          label={t('common.search')}
          value={searchTerm}
          onChange={(e) => {
            setSearchTerm(e.target.value);
            setPage(1);
          }}
          sx={{ minWidth: 240 }}
        />
        <TextField
          select
          size="small"
          label={t('common.status')}
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value as StatusFilter);
            setPage(1);
          }}
          sx={{ minWidth: 160 }}
        >
          <MenuItem value="ALL">{t('common.all')}</MenuItem>
          <MenuItem value="COMPLETED">{t('status.COMPLETED')}</MenuItem>
          <MenuItem value="DRAFT">{t('status.DRAFT')}</MenuItem>
          <MenuItem value="CANCELLED">{t('status.CANCELLED')}</MenuItem>
        </TextField>
        <TextField
          size="small"
          type="date"
          label={t('phase1.filterFrom')}
          value={dateFrom}
          onChange={(e) => {
            setDateFrom(e.target.value);
            setPage(1);
          }}
          InputLabelProps={{ shrink: true }}
          error={dateRangeInvalid}
        />
        <TextField
          size="small"
          type="date"
          label={t('phase1.filterTo')}
          value={dateTo}
          onChange={(e) => {
            setDateTo(e.target.value);
            setPage(1);
          }}
          InputLabelProps={{ shrink: true }}
          error={dateRangeInvalid}
        />
        {filtersActive ? (
          <Button
            size="small"
            onClick={() => {
              setStatusFilter('ALL');
              setSearchTerm('');
              setDateFrom('');
              setDateTo('');
              setPage(1);
            }}
          >
            {t('phase1.clearFilters')}
          </Button>
        ) : null}
      </Stack>
      {dateRangeInvalid ? <Alert severity="warning">{t('phase1.dateRangeInvalid')}</Alert> : null}

      {message ? <Alert severity="success" onClose={() => setMessage(null)}>{message}</Alert> : null}
      {error && !open ? <HelpErrorAlert message={error} /> : null}
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {returns.length === 0 && query.isSuccess ? (
        <EmptyState
          description={t('empty.purchaseReturns')}
          action={
            canWrite ? (
              <Button variant="contained" onClick={openNewReturn}>
                {t('phase1.newPurchaseReturn')}
              </Button>
            ) : null
          }
        />
      ) : null}
      {returns.length > 0 ? (
        <Paper tabIndex={0} role="region" aria-label={t('common.scrollableTable')} sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('common.number')}</TableCell>
                <TableCell>{t('common.date')}</TableCell>
                <TableCell>{t('phase1.sourcePurchase')}</TableCell>
                <TableCell>{t('phase1.linkedCreditNote')}</TableCell>
                <TableCell>{t('billing.supplier')}</TableCell>
                <TableCell>{t('common.reason')}</TableCell>
                <TableCell>{t('common.status')}</TableCell>
                <TableCell align="right">{t('common.total')}</TableCell>
                <TableCell align="right">{t('common.actions')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {returns.map((r) => (
                <TableRow key={r.id} hover>
                  <TableCell>
                    <Button
                      size="small"
                      variant="text"
                      sx={{ minWidth: 0, p: 0, textTransform: 'none', fontWeight: 600 }}
                      onClick={() => setDetailReturn(r)}
                    >
                      {r.number || `#${r.id}`}
                    </Button>
                  </TableCell>
                  <TableCell>{r.returnDate}</TableCell>
                  <TableCell>
                    {r.purchaseInvoice ? (
                      <Button
                        component={RouterLink}
                        to={`/purchases/history/${r.purchaseInvoice}`}
                        size="small"
                        variant="text"
                        sx={{ minWidth: 0, p: 0, textTransform: 'none' }}
                      >
                        {r.purchaseInvoiceNumber || `#${r.purchaseInvoice}`}
                      </Button>
                    ) : (
                      '—'
                    )}
                  </TableCell>
                  <TableCell>
                    {r.creditNoteId ? (
                      <Button
                        component={RouterLink}
                        to={`/purchases/credit-notes/${r.creditNoteId}`}
                        size="small"
                        variant="text"
                        sx={{ minWidth: 0, p: 0, textTransform: 'none' }}
                      >
                        {r.creditNoteNumber || `#${r.creditNoteId}`}
                      </Button>
                    ) : (
                      '—'
                    )}
                  </TableCell>
                  <TableCell>{r.supplierName}</TableCell>
                  <TableCell>{r.reason || '—'}</TableCell>
                  <TableCell>
                    <StatusChip tone={documentStatusTone(r.status)} labelKey={statusLabelKey(r.status)} />
                  </TableCell>
                  <TableCell align="right">{formatMoney(r.grandTotal)}</TableCell>
                  <TableCell align="right">
                    <Stack direction="row" spacing={0.5} justifyContent="flex-end">
                      <Button size="small" onClick={() => setDetailReturn(r)}>
                        {t('common.view')}
                      </Button>
                      {r.status === 'DRAFT' && canWrite ? (
                        <Button size="small" onClick={() => void onResumeDraft(r)}>
                          {t('common.edit')}
                        </Button>
                      ) : null}
                      {r.status === 'DRAFT' && canWrite ? (
                        <Button
                          size="small"
                          disabled={completeDraftMutation.isPending}
                          onClick={() => {
                            void confirmAction(t('purchaseReview.returnConfirmComplete')).then((ok) => {
                              if (ok) completeDraftMutation.mutate(r.id);
                            });
                          }}
                        >
                          {t('common.complete')}
                        </Button>
                      ) : null}
                      {r.status === 'DRAFT' && canWrite ? (
                        <Button
                          size="small"
                          color="error"
                          disabled={deleteDraftMutation.isPending}
                          onClick={() => setConfirmDeleteDraft(r)}
                        >
                          {t('common.delete')}
                        </Button>
                      ) : null}
                      {r.status === 'COMPLETED' && canCancelReturn ? (
                        <Button
                          size="small"
                          color="error"
                          disabled={cancelReturnMutation.isPending}
                          onClick={() => setConfirmCancelReturn(r)}
                        >
                          {t('phase1.cancelReturn')}
                        </Button>
                      ) : null}
                    </Stack>
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
        when={returnDirty}
        prompt={discardPrompt}
        onStay={() => setDiscardPrompt(false)}
        onLeave={() => {
          if (draftId !== null && !isExistingDraft) {
            void deletePurchaseReturn(draftId)
              .then(() => qc.invalidateQueries({ queryKey: ['purchase-returns'] }))
              .catch(() => {});
          }
          setDiscardPrompt(false);
          setOpen(false);
          resetDialog();
        }}
      />
      <Dialog open={open && canWrite} onClose={requestClose} fullWidth maxWidth="md">
        <DialogTitle>
          {isExistingDraft ? t('phase1.editPurchaseReturnDraft') : t('phase1.newPurchaseReturn')}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {error ? <HelpErrorAlert message={error} /> : null}
            <Alert severity="info">{t('phase1.autoPurchaseCreditNoteNotice')}</Alert>
            {returnDateBeforePurchase ? (
              <Alert severity="error">{t('phase1.returnDateBeforeInvoice')}</Alert>
            ) : null}
            {!loadingLines && purchase && lines.length > 0 && activeLines.length === 0 ? (
              <Alert severity="warning">{t('phase1.selectItemToReturn')}</Alert>
            ) : null}
            {missingSerialLine ? (
              <Alert severity="warning">
                {t('billing.completeDisabledMissingSerial', { name: missingSerialLine.productName })}
              </Alert>
            ) : null}
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <Autocomplete
                sx={{ flex: 1 }}
                options={completed}
                getOptionLabel={(o) => `${o.number ?? o.id} · ${o.supplierName ?? ''}`}
                value={purchase}
                disabled={isExistingDraft}
                inputValue={purchaseSearch}
                onInputChange={(_, v) => setPurchaseSearch(v)}
                onChange={(_, v) => void onPurchasePick(v)}
                loading={purchases.isLoading}
                filterOptions={(x) => x}
                renderInput={(params) => (
                  <TextField
                    {...params}
                    label={t('phase1.originalPurchase')}
                    placeholder={t('phase1.searchPurchaseOrSupplier')}
                  />
                )}
              />
              <TextField
                type="date"
                label={t('common.date')}
                value={returnDate}
                onChange={(e) => setReturnDate(e.target.value)}
                InputLabelProps={{ shrink: true }}
                inputProps={{ min: purchase?.invoiceDate || undefined, max: todayIso() }}
                sx={{ minWidth: 170 }}
              />
            </Stack>
            {loadingLines ? (
              <Box sx={{ display: 'flex', justifyContent: 'center', py: 3 }} data-testid="return-lines-loading">
                <CircularProgress size={28} aria-label={t('common.loading')} />
              </Box>
            ) : lines.length > 0 ? (
              <>
                <InvoiceReturnLineTable lines={lines} onChange={setLines} showLot />
                {activeLines.length > 0 ? (
                  <Paper variant="outlined" sx={{ p: 1.5, bgcolor: 'action.hover' }} data-testid="return-preview">
                    {preview.isError ? (
                      <Typography variant="body2" color="warning.main">
                        {t('phase1.returnPreviewUnavailable', { message: getErrorMessage(preview.error) })}
                      </Typography>
                    ) : previewData ? (
                      <Stack spacing={0.5}>
                        <Stack
                          direction={{ xs: 'column', sm: 'row' }}
                          justifyContent="space-between"
                          alignItems={{ sm: 'center' }}
                          spacing={1}
                        >
                          <Typography variant="body2" color="text.secondary">
                            {t('phase1.returnLinesUnits', { lines: previewData.lineCount, units: previewData.units })}
                          </Typography>
                          <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" useFlexGap>
                            <Typography variant="body2">
                              {t('phase1.returnTaxable')}: <strong>{formatMoney(previewData.taxableTotal)}</strong>
                            </Typography>
                            <Typography variant="body2">
                              {t('phase1.returnGst')}: <strong>{formatMoney(previewGst)}</strong>
                            </Typography>
                            {previewData.invoiceDiscount > 0 ? (
                              <Typography variant="body2">
                                {t('phase1.returnDiscountShare')}: <strong>{formatMoney(previewData.invoiceDiscount)}</strong>
                              </Typography>
                            ) : null}
                            {previewData.additionalCharges > 0 ? (
                              <Typography variant="body2">
                                {t('phase1.returnChargesShare')}: <strong>{formatMoney(previewData.additionalCharges)}</strong>
                              </Typography>
                            ) : null}
                            <Typography variant="subtitle2">
                              {t('phase1.returnCreditNoteTotal')}: <strong>{formatMoney(previewData.grandTotal)}</strong>
                            </Typography>
                          </Stack>
                        </Stack>
                        <Typography variant="caption" color="text.secondary">
                          {t('phase1.returnPreviewNote')}
                        </Typography>
                        <Typography variant="body2">
                          {t('phase1.returnWhatHappens', {
                            supplier: purchase?.supplierName ?? '',
                            amount: formatMoney(previewData.grandTotal),
                          })}
                        </Typography>
                      </Stack>
                    ) : (
                      <Typography variant="body2" color="text.secondary">
                        {t('phase1.returnPreviewLoading')}
                      </Typography>
                    )}
                  </Paper>
                ) : null}
              </>
            ) : null}
            <TextField label={t('common.reason')} value={reason} onChange={(e) => setReason(e.target.value)} />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={requestClose}>{t('common.cancel')}</Button>
          <Button
            variant="outlined"
            disabled={
              !purchase ||
              activeLines.length === 0 ||
              returnDateBeforePurchase ||
              Boolean(missingSerialLine) ||
              saveDraftMutation.isPending ||
              createMutation.isPending
            }
            onClick={() => saveDraftMutation.mutate()}
          >
            {t('common.save')}
          </Button>
          <Tooltip
            title={
              returnCompleteDisabledReason({
                writesBlocked,
                pending: createMutation.isPending,
                missingSource: !purchase,
                returnDateBeforeInvoice: returnDateBeforePurchase,
                noLines: Boolean(purchase) && activeLines.length === 0,
                missingSerialName: missingSerialLine?.productName,
              }) ?? ''
            }
          >
            <span>
              <Button
                variant="contained"
                disabled={
                  !purchase ||
                  activeLines.length === 0 ||
                  returnDateBeforePurchase ||
                  Boolean(missingSerialLine) ||
                  createMutation.isPending ||
                  saveDraftMutation.isPending
                }
                onClick={() => createMutation.mutate()}
              >
                {t('common.complete')}
              </Button>
            </span>
          </Tooltip>
        </DialogActions>
      </Dialog>

      {/* Purchase Return Detail Dialog */}
      <Dialog open={Boolean(detailReturn)} onClose={() => setDetailReturn(null)} fullWidth maxWidth="md">
        <DialogTitle>
          {detail?.number || `#${detail?.id ?? ''}`} — {t('nav.purchaseReturns')}
        </DialogTitle>
        <DialogContent>
          {detail ? (
            <Stack spacing={2} sx={{ mt: 1 }}>
              <Stack direction="row" spacing={2} flexWrap="wrap" alignItems="center" useFlexGap>
                <StatusChip
                  tone={documentStatusTone(detail.status)}
                  labelKey={statusLabelKey(detail.status)}
                />
                <Typography variant="body2">
                  <strong>{t('common.date')}:</strong> {detail.returnDate}
                </Typography>
                <Typography variant="body2">
                  <strong>{t('billing.supplier')}:</strong> {detail.supplierName}
                </Typography>
                <Typography variant="body2">
                  <strong>{t('phase1.sourcePurchase')}:</strong>{' '}
                  <RouterLink to={`/purchases/history/${detail.purchaseInvoice}`}>
                    {detail.purchaseInvoiceNumber || `#${detail.purchaseInvoice}`}
                  </RouterLink>
                </Typography>
                {detail.creditNoteId ? (
                  <Typography variant="body2">
                    <strong>{t('phase1.linkedCreditNote')}:</strong>{' '}
                    <RouterLink to={`/purchases/credit-notes/${detail.creditNoteId}`}>
                      {detail.creditNoteNumber || `#${detail.creditNoteId}`}
                    </RouterLink>
                  </Typography>
                ) : null}
              </Stack>
              {detail.reason ? (
                <Typography variant="body2" color="text.secondary">
                  <strong>{t('common.reason')}:</strong> {detail.reason}
                </Typography>
              ) : null}
              <Divider />
              <Paper variant="outlined" sx={{ overflow: 'auto' }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>{t('nav.products')}</TableCell>
                      <TableCell>{t('sweep2.condition')}</TableCell>
                      <TableCell>{t('erp.serialNumbers')}</TableCell>
                      <TableCell align="right">{t('billing.qty')}</TableCell>
                      <TableCell align="right">{t('billing.priceShort')}</TableCell>
                      <TableCell align="right">{t('phase1.detailDiscountPct')}</TableCell>
                      <TableCell align="right">{t('phase1.detailGstPct')}</TableCell>
                      <TableCell align="right">{t('common.total')}</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {(detail.items ?? []).map((it, idx) => (
                      <TableRow key={it.id ?? idx}>
                        <TableCell>{it.productName ?? `#${it.product}`}</TableCell>
                        <TableCell>
                          <Chip
                            size="small"
                            label={it.condition === 'DAMAGED' ? t('sweep2.damaged') : t('sweep2.sellable')}
                            color={it.condition === 'DAMAGED' ? 'warning' : 'success'}
                            variant="outlined"
                          />
                        </TableCell>
                        <TableCell>{(it.serialNumbers ?? []).join(', ') || '—'}</TableCell>
                        <TableCell align="right">{it.quantity}</TableCell>
                        <TableCell align="right">{formatMoney(it.unitPrice)}</TableCell>
                        <TableCell align="right">{toNumber(it.discountPercent)}</TableCell>
                        <TableCell align="right">{toNumber(it.gstRate)}</TableCell>
                        <TableCell align="right">
                          {formatMoney(it.lineTotal ?? Number(it.quantity) * Number(it.unitPrice))}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Paper>
              <Stack spacing={0.5} alignItems="flex-end" data-testid="return-detail-totals">
                <Typography variant="body2">
                  {t('phase1.detailTaxable')}: <strong>{formatMoney(detail.taxableTotal)}</strong>
                </Typography>
                {toNumber(detail.cgstTotal) > 0 ? (
                  <Typography variant="body2">
                    CGST: <strong>{formatMoney(detail.cgstTotal)}</strong>
                  </Typography>
                ) : null}
                {toNumber(detail.sgstTotal) > 0 ? (
                  <Typography variant="body2">
                    SGST: <strong>{formatMoney(detail.sgstTotal)}</strong>
                  </Typography>
                ) : null}
                {toNumber(detail.igstTotal) > 0 ? (
                  <Typography variant="body2">
                    IGST: <strong>{formatMoney(detail.igstTotal)}</strong>
                  </Typography>
                ) : null}
                {toNumber(detail.cessTotal) > 0 ? (
                  <Typography variant="body2">
                    {t('phase1.detailCess')}: <strong>{formatMoney(detail.cessTotal ?? 0)}</strong>
                  </Typography>
                ) : null}
                {toNumber(detail.roundOff) !== 0 ? (
                  <Typography variant="body2">
                    {t('phase1.detailRoundOff')}: <strong>{formatMoney(detail.roundOff)}</strong>
                  </Typography>
                ) : null}
                <Typography variant="subtitle1">
                  {t('common.total')}: <strong>{formatMoney(detail.grandTotal)}</strong>
                </Typography>
              </Stack>
            </Stack>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDetailReturn(null)}>{t('common.close')}</Button>
        </DialogActions>
      </Dialog>

      {/* Confirm Cancel Completed Return Dialog */}
      <Dialog
        open={Boolean(confirmCancelReturn)}
        onClose={() => setConfirmCancelReturn(null)}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle>{t('phase1.cancelDocument')}</DialogTitle>
        <DialogContent>
          <Typography variant="body2">{t('phase1.cancelPurchaseReturnConfirm')}</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmCancelReturn(null)}>{t('common.close')}</Button>
          <Button
            variant="contained"
            color="error"
            disabled={cancelReturnMutation.isPending}
            onClick={() => {
              if (confirmCancelReturn) cancelReturnMutation.mutate(confirmCancelReturn);
            }}
          >
            {t('phase1.cancelReturn')}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Confirm Delete Draft Return Dialog */}
      <Dialog
        open={Boolean(confirmDeleteDraft)}
        onClose={() => setConfirmDeleteDraft(null)}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle>{t('common.delete')}</DialogTitle>
        <DialogContent>
          <Typography variant="body2">{t('phase1.deletePurchaseReturnDraftConfirm')}</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmDeleteDraft(null)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            color="error"
            disabled={deleteDraftMutation.isPending}
            onClick={() => {
              if (confirmDeleteDraft) deleteDraftMutation.mutate(confirmDeleteDraft.id);
            }}
          >
            {t('common.delete')}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
