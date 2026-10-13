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
import {
  cancelSalesReturn,
  completeSalesReturn,
  createSalesReturn,
  deleteSalesReturn,
  getInvoiceReturnableLines,
  getSalesInvoice,
  getSalesReturn,
  listProducts,
  listSalesInvoicesPage,
  listSalesReturnsPage,
  previewSalesReturnTotals,
  updateSalesReturn,
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
import type { ReturnableLine, SalesInvoice, SalesReturn } from '@/types/domain';
import { formatMoney, toNumber } from '@/utils/money';
import { canCancelDocuments, canCreateSales, canOverrideGstGuard } from '@/utils/permissions';
import { useAuth } from '@/auth/AuthContext';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { documentStatusTone, statusLabelKey } from '@/utils/status';
import { returnCompleteDisabledReason, serialCountMatchesQty } from '@/completeGates/completeBlockers';
import { invalidateInvoiceSideEffects } from '@/pages/sales/invalidateInvoiceSideEffects';
import { gstGuardIssuesFromError, type GstGuardIssue } from '@/pages/sales/gstGuardErrors';
import { creditExceedsBalance } from '@/pages/sales/returnHelpers';

const PAGE_SIZE = 50;

type StatusFilter = 'ALL' | 'DRAFT' | 'COMPLETED' | 'CANCELLED';

/** One-tap reasons. "Defective" also marks the lines being returned as Damaged. */
const REASON_PRESETS = [
  { key: 'defective', labelKey: 'phase1.reasonPresetDefective', damaged: true },
  { key: 'wrong-item', labelKey: 'phase1.reasonPresetWrongItem', damaged: false },
  { key: 'changed-mind', labelKey: 'phase1.reasonPresetChangedMind', damaged: false },
  { key: 'quality', labelKey: 'phase1.reasonPresetQuality', damaged: false },
] as const;

export function SalesReturnsPage() {
  const { user } = useAuth();
  const { writesBlocked } = useSubscriptionGate();
  const canWrite = canCreateSales(user) && !writesBlocked;
  const canCompleteReturn = canCancelDocuments(user) && !writesBlocked;
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
    queryKey: ['sales-returns', page, statusFilter, debouncedSearch.trim(), dateFrom, dateTo],
    enabled: !dateRangeInvalid,
    queryFn: () =>
      listSalesReturnsPage({
        page,
        pageSize: PAGE_SIZE,
        ...(statusFilter !== 'ALL' ? { status: statusFilter } : {}),
        ...(debouncedSearch.trim() ? { q: debouncedSearch.trim() } : {}),
        ...(dateFrom ? { date_from: dateFrom } : {}),
        ...(dateTo ? { date_to: dateTo } : {}),
      }),
  });

  const [invoiceSearch, setInvoiceSearch] = useState('');
  const debouncedInvoiceSearch = useDebouncedValue(invoiceSearch, 250);
  const invoices = useQuery({
    queryKey: ['completed-sales', debouncedInvoiceSearch],
    queryFn: async () => {
      const res = await listSalesInvoicesPage({
        status: 'COMPLETED',
        q: debouncedInvoiceSearch.trim() || undefined,
        pageSize: PAGE_SIZE,
      });
      return res.results;
    },
  });

  // Search, status and date filters all run on the server so they see every page.
  const returns = query.data?.results ?? [];

  const [open, setOpen] = useState(false);
  const [invoice, setInvoice] = useState<SalesInvoice | null>(null);
  const [loadingInvoiceLines, setLoadingInvoiceLines] = useState(false);
  const [lines, setLines] = useState<InvoiceSourceLine[]>([]);
  const [returnDate, setReturnDate] = useState<string>(() => todayIso());
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [draftId, setDraftId] = useState<number | null>(null);
  const [isExistingDraft, setIsExistingDraft] = useState(false);
  const [gestureKey, setGestureKey] = useState<string | null>(null);
  // Every invoice/draft load takes a ticket; a slower, older response is dropped.
  const loadSeq = useRef(0);
  const [gstGuardIssues, setGstGuardIssues] = useState<GstGuardIssue[] | null>(null);
  const [gstGuardOverrideReason, setGstGuardOverrideReason] = useState('');

  const [detailReturn, setDetailReturn] = useState<SalesReturn | null>(null);
  const [confirmCancelReturn, setConfirmCancelReturn] = useState<SalesReturn | null>(null);
  const [confirmDeleteDraft, setConfirmDeleteDraft] = useState<SalesReturn | null>(null);
  const [rowGuard, setRowGuard] = useState<{
    id: number;
    invoiceId: number | null;
    issues: GstGuardIssue[];
  } | null>(null);
  const [rowGuardReason, setRowGuardReason] = useState('');

  const products = useQuery({
    queryKey: ['products'],
    queryFn: () => listProducts(),
    staleTime: 60_000,
  });

  const invalidateAfterReturnLifecycle = (invoiceId?: number | null) => {
    invalidateInvoiceSideEffects(qc, invoiceId ?? undefined);
    void qc.invalidateQueries({ queryKey: ['sales-returns'] });
    void qc.invalidateQueries({ queryKey: ['completed-sales'] });
    void qc.invalidateQueries({ queryKey: ['sales-credit-notes'] });
    void qc.invalidateQueries({ queryKey: ['products'] });
    void qc.invalidateQueries({ queryKey: ['stock-balance'] });
    void qc.invalidateQueries({ queryKey: ['stock'] });
    void qc.invalidateQueries({ queryKey: ['customers'] });
  };

  const loadInvoiceSourceLines = async (
    inv: SalesInvoice,
  ): Promise<{ full: SalesInvoice; sourceLines: InvoiceSourceLine[] }> => {
    const full = inv.items?.length ? inv : await getSalesInvoice(inv.id);
    const catalog = products.data?.length ? products.data : await listProducts();
    const byId = new Map(catalog.map((p) => [p.id, p]));

    // The server owns the headroom (completed returns + standalone credit notes)
    // and which serials already came back. If it cannot be loaded we say so rather
    // than guess: a client-side estimate would ignore standalone credit notes.
    const returnable: ReturnableLine[] = await getInvoiceReturnableLines(full.id);
    return {
      full,
      sourceLines: invoiceItemsToSourceLines(full.items, undefined, byId, undefined, returnable),
    };
  };

  const onInvoicePick = async (inv: SalesInvoice | null) => {
    const seq = ++loadSeq.current;
    // Switching invoices after an implicit draft (left behind by a failed Complete)
    // must not patch the new invoice's lines onto the old invoice's draft.
    if (draftId !== null && !isExistingDraft && inv?.id !== invoice?.id) {
      const staleDraftId = draftId;
      setDraftId(null);
      setGestureKey(null);
      void deleteSalesReturn(staleDraftId).catch(() => {});
    }
    setInvoice(inv);
    setGstGuardIssues(null);
    if (!inv) {
      setLines([]);
      setLoadingInvoiceLines(false);
      return;
    }
    setLoadingInvoiceLines(true);
    setLines([]);
    try {
      const { full, sourceLines } = await loadInvoiceSourceLines(inv);
      if (seq !== loadSeq.current) return;
      setInvoice(full);
      setLines(sourceLines);
    } catch (err) {
      if (seq === loadSeq.current) setError(getErrorMessage(err));
    } finally {
      if (seq === loadSeq.current) setLoadingInvoiceLines(false);
    }
  };

  const onResumeDraft = async (row: SalesReturn) => {
    const seq = ++loadSeq.current;
    setError(null);
    setMessage(null);
    setDraftId(row.id);
    setIsExistingDraft(true);
    setGestureKey(null);
    setGstGuardIssues(null);
    setReturnDate(row.returnDate || todayIso());
    setReason(row.reason ?? '');
    setInvoice(null);
    setLines([]);
    setOpen(true);
    setLoadingInvoiceLines(true);
    try {
      // The list row may be stale; hydrate from the draft as saved on the server.
      const draft = await getSalesReturn(row.id);
      const inv = await getSalesInvoice(draft.salesInvoice);
      const { full, sourceLines } = await loadInvoiceSourceLines(inv);
      if (seq !== loadSeq.current) return;
      setInvoice(full);
      setReturnDate(draft.returnDate || todayIso());
      setReason(draft.reason ?? '');
      const hydrated = sourceLines.map((src) => {
        const match = (draft.items ?? []).find((it) =>
          it.sourceItem != null ? it.sourceItem === src.sourceItemId : it.product === src.product,
        );
        if (!match) return src;
        let serials = match.serialNumbers ?? [];
        if (hasSerialPickList(src)) {
          // Keep only serials that can still be returned.
          serials = serials.filter((sn) => src.soldSerialNumbers!.includes(sn));
        }
        const quantity = src.trackSerial && hasSerialPickList(src) ? serials.length : toNumber(match.quantity);
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
      if (seq === loadSeq.current) setLoadingInvoiceLines(false);
    }
  };

  // An inbound ?create=1 or ?invoice= opens the dialog; the effect below then strips the params.
  if ((searchParams.get('create') === '1' || searchParams.get('invoice')) && !open) setOpen(true);

  useEffect(() => {
    const wantsCreate = searchParams.get('create') === '1';
    const invoiceIdRaw = searchParams.get('invoice');
    if (!wantsCreate && !invoiceIdRaw) return;
    const next = new URLSearchParams(searchParams);
    next.delete('create');
    next.delete('invoice');
    setSearchParams(next, { replace: true });
    const id = Number(invoiceIdRaw);
    if (!Number.isFinite(id) || id <= 0) return;
    void getSalesInvoice(id)
      .then((inv) => onInvoicePick(inv))
      .catch((err) => setError(getErrorMessage(err)));
    // Prefill once from the inbound query string; onInvoicePick is recreated each render
    // and only reads dialog state that is empty when the dialog was just opened.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams, setSearchParams]);

  const resetDialog = () => {
    loadSeq.current += 1;
    setInvoice(null);
    setLoadingInvoiceLines(false);
    setLines([]);
    setReturnDate(todayIso());
    setReason('');
    setDraftId(null);
    setIsExistingDraft(false);
    setGestureKey(null);
    setError(null);
    setGstGuardIssues(null);
    setGstGuardOverrideReason('');
  };

  const [discardPrompt, setDiscardPrompt] = useState(false);
  const returnDirty = returnDialogDirty(open, Boolean(invoice), reason);
  const requestClose = () => {
    if (returnDirty) setDiscardPrompt(true);
    else {
      setOpen(false);
      resetDialog();
    }
  };

  const returnDateBeforeInvoice = Boolean(
    invoice?.invoiceDate && returnDate && returnDate < invoice.invoiceDate,
  );

  const activeLines = useMemo(() => activeSourceLines(lines), [lines]);

  const missingSerialLine = useMemo(
    () =>
      activeLines.find((l) => l.trackSerial && !serialCountMatchesQty(l.serialNumbersText, l.quantity)),
    [activeLines],
  );

  // SRF-11: exact credit-note totals come from the server (it runs the real
  // build inside a rolled-back savepoint), debounced while the operator edits.
  const previewItems = useMemo(
    () => (missingSerialLine ? [] : activeLines.map((l) => sourceLineReturnPayload(l))),
    [activeLines, missingSerialLine],
  );
  const previewKey = JSON.stringify({ inv: invoice?.id ?? null, date: returnDate, items: previewItems });
  const debouncedPreviewKey = useDebouncedValue(previewKey, 300);
  const preview = useQuery({
    queryKey: ['sales-return-preview', debouncedPreviewKey],
    enabled:
      open &&
      Boolean(invoice) &&
      previewItems.length > 0 &&
      !returnDateBeforeInvoice &&
      debouncedPreviewKey === previewKey,
    retry: false,
    staleTime: 0,
    queryFn: () =>
      previewSalesReturnTotals({
        customer: invoice!.customer,
        salesInvoice: invoice!.id,
        returnDate: returnDate || todayIso(),
        items: previewItems,
      }),
  });

  const saveDraftMutation = useMutation({
    mutationFn: async () => {
      if (!invoice) throw new Error(t('phase1.selectInvoice'));
      if (activeLines.length === 0) throw new Error(t('phase1.selectInvoiceLines'));
      const key = gestureKey ?? userGestureIdempotencyKey();
      if (!gestureKey) setGestureKey(key);
      const items = activeLines.map((l) => sourceLineReturnPayload(l));
      if (!draftId) {
        return createSalesReturn(
          {
            customer: invoice.customer,
            salesInvoice: invoice.id,
            returnDate: returnDate || todayIso(),
            reason,
            items,
          },
          { idempotencyKey: key },
        );
      }
      return updateSalesReturn(draftId, {
        returnDate: returnDate || todayIso(),
        reason,
        items,
      });
    },
    onSuccess: () => {
      const invId = invoice?.id;
      setOpen(false);
      setMessage(t('phase1.salesReturnDraftSaved'));
      resetDialog();
      invalidateAfterReturnLifecycle(invId);
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const createMutation = useMutation({
    mutationFn: async (overrideReason?: string) => {
      if (!invoice) throw new Error(t('phase1.selectInvoice'));
      if (activeLines.length === 0) throw new Error(t('phase1.selectInvoiceLines'));
      // Create the draft first; if Complete is refused the dialog stays open so
      // lines can be corrected, and a retry after an update uses a fresh complete key.
      const key = gestureKey ?? userGestureIdempotencyKey();
      if (!gestureKey) setGestureKey(key);
      const items = activeLines.map((l) => sourceLineReturnPayload(l));
      let id = draftId;
      let completeKey = `${key}-complete`;
      if (!id) {
        const draft = await createSalesReturn(
          {
            customer: invoice.customer,
            salesInvoice: invoice.id,
            returnDate: returnDate || todayIso(),
            reason,
            items,
          },
          { idempotencyKey: key },
        );
        id = draft.id;
        setDraftId(id);
      } else {
        await updateSalesReturn(id, {
          returnDate: returnDate || todayIso(),
          reason,
          items,
        });
        completeKey = `${userGestureIdempotencyKey()}-complete`;
      }
      return completeSalesReturn(id, {
        idempotencyKey: completeKey,
        ...(overrideReason ? { gstGuardOverrideReason: overrideReason } : {}),
      });
    },
    onMutate: () => {
      setError(null);
      setGstGuardIssues(null);
    },
    onSuccess: () => {
      const invId = invoice?.id;
      setOpen(false);
      setMessage(t('phase1.salesReturnCompleted'));
      resetDialog();
      invalidateAfterReturnLifecycle(invId);
    },
    onError: (err) => {
      const guardIssues = gstGuardIssuesFromError(err);
      if (guardIssues) {
        setGstGuardIssues(guardIssues);
        return;
      }
      setError(getErrorMessage(err));
    },
  });

  const completeDraftMutation = useMutation({
    mutationFn: async ({
      id,
      overrideReason,
    }: {
      id: number;
      invoiceId: number | null;
      overrideReason?: string;
    }) =>
      completeSalesReturn(id, {
        idempotencyKey: `${userGestureIdempotencyKey()}-complete`,
        ...(overrideReason ? { gstGuardOverrideReason: overrideReason } : {}),
      }),
    onSuccess: (_, vars) => {
      setRowGuard(null);
      setRowGuardReason('');
      setMessage(t('phase1.salesReturnCompleted'));
      setError(null);
      invalidateAfterReturnLifecycle(vars.invoiceId);
    },
    onError: (err, vars) => {
      const guardIssues = gstGuardIssuesFromError(err);
      if (guardIssues) {
        setRowGuard({ id: vars.id, invoiceId: vars.invoiceId, issues: guardIssues });
        return;
      }
      setRowGuard(null);
      setError(getErrorMessage(err));
    },
  });

  const deleteDraftMutation = useMutation({
    mutationFn: async (id: number) => deleteSalesReturn(id),
    onSuccess: () => {
      setConfirmDeleteDraft(null);
      setMessage(t('phase1.salesReturnDeleted'));
      setError(null);
      void qc.invalidateQueries({ queryKey: ['sales-returns'] });
    },
    onError: (err) => {
      setConfirmDeleteDraft(null);
      setError(getErrorMessage(err));
    },
  });

  const cancelReturnMutation = useMutation({
    mutationFn: async (ret: SalesReturn) => cancelSalesReturn(ret.id),
    onSuccess: (_, ret) => {
      setConfirmCancelReturn(null);
      setMessage(t('phase1.salesReturnCancelled'));
      setError(null);
      invalidateAfterReturnLifecycle(ret.salesInvoice);
    },
    onError: (err) => {
      setConfirmCancelReturn(null);
      setError(getErrorMessage(err));
    },
  });

  const applyReasonPreset = (preset: (typeof REASON_PRESETS)[number]) => {
    setReason(t(preset.labelKey));
    if (preset.damaged) {
      setLines((current) =>
        current.map((l) => (l.included ? { ...l, condition: 'DAMAGED' as const } : l)),
      );
    }
  };

  const openNewReturn = () => {
    resetDialog();
    setOpen(true);
  };

  const previewData = preview.data;
  const creditBecomesAdvance = creditExceedsBalance(invoice, previewData?.grandTotal);
  const previewGst = previewData
    ? previewData.cgstTotal + previewData.sgstTotal + previewData.igstTotal + previewData.cessTotal
    : 0;

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1}>
        <PageTitle>{t('nav.salesReturns')}</PageTitle>
        {canWrite ? (
          <Button variant="contained" onClick={openNewReturn}>
            {t('phase1.newSalesReturn')}
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
          description={t('empty.salesReturns')}
          action={
            canWrite ? (
              <Button variant="contained" onClick={openNewReturn}>
                {t('phase1.newSalesReturn')}
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
                <TableCell>{t('phase1.sourceInvoice')}</TableCell>
                <TableCell>{t('phase1.linkedCreditNote')}</TableCell>
                <TableCell>{t('billing.customer')}</TableCell>
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
                    {r.salesInvoice ? (
                      <Button
                        component={RouterLink}
                        to={`/sales/invoices/${r.salesInvoice}`}
                        size="small"
                        variant="text"
                        sx={{ minWidth: 0, p: 0, textTransform: 'none' }}
                      >
                        {r.salesInvoiceNumber || `#${r.salesInvoice}`}
                      </Button>
                    ) : (
                      '—'
                    )}
                  </TableCell>
                  <TableCell>
                    {r.creditNoteId ? (
                      <Button
                        component={RouterLink}
                        to={`/sales/credit-notes/${r.creditNoteId}`}
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
                  <TableCell>{r.customerName}</TableCell>
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
                      {r.status === 'DRAFT' && canCompleteReturn ? (
                        <Button
                          size="small"
                          color="primary"
                          disabled={completeDraftMutation.isPending}
                          onClick={() =>
                            completeDraftMutation.mutate({ id: r.id, invoiceId: r.salesInvoice ?? null })
                          }
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
                      {r.status === 'COMPLETED' && canCompleteReturn ? (
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
            void deleteSalesReturn(draftId)
              .then(() => qc.invalidateQueries({ queryKey: ['sales-returns'] }))
              .catch(() => {});
          }
          setDiscardPrompt(false);
          setOpen(false);
          resetDialog();
        }}
      />
      <Dialog open={open && canWrite} onClose={requestClose} fullWidth maxWidth="md">
        <DialogTitle>
          {isExistingDraft ? t('phase1.editSalesReturnDraft') : t('phase1.newSalesReturn')}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {/* Mutation errors surface inside the modal; a page-level Alert behind the Dialog is invisible. */}
            {error ? <HelpErrorAlert message={error} /> : null}
            {gstGuardIssues && gstGuardIssues.length > 0 ? (
              <Alert severity="error">
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
                      disabled={!gstGuardOverrideReason.trim() || createMutation.isPending}
                      onClick={() => createMutation.mutate(gstGuardOverrideReason.trim())}
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
            {!canCompleteReturn ? (
              <Alert severity="info">
                {t('phase1.salesReturnCompleteOwnerOnly')} {t('phase1.staffDraftNotice')}
              </Alert>
            ) : (
              <Alert severity="info">{t('phase1.autoCreditNoteNotice')}</Alert>
            )}
            {creditBecomesAdvance ? <Alert severity="warning">{t('phase1.paidInvoiceReturnNotice')}</Alert> : null}
            {returnDateBeforeInvoice ? (
              <Alert severity="error">{t('phase1.returnDateBeforeInvoice')}</Alert>
            ) : null}
            {!loadingInvoiceLines && invoice && lines.length > 0 && activeLines.length === 0 ? (
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
                options={invoices.data ?? []}
                getOptionLabel={(o) => `${o.number ?? o.id} · ${o.customerName ?? ''}`}
                value={invoice}
                disabled={isExistingDraft}
                inputValue={invoiceSearch}
                onInputChange={(_, v) => setInvoiceSearch(v)}
                onChange={(_, v) => void onInvoicePick(v)}
                loading={invoices.isLoading}
                filterOptions={(x) => x}
                renderInput={(params) => (
                  <TextField
                    {...params}
                    label={t('phase1.originalInvoice')}
                    placeholder={t('phase1.searchInvoiceOrCustomer')}
                  />
                )}
              />
              <TextField
                type="date"
                label={t('common.date')}
                value={returnDate}
                onChange={(e) => setReturnDate(e.target.value)}
                InputLabelProps={{ shrink: true }}
                inputProps={{
                  min: invoice?.invoiceDate || undefined,
                  max: todayIso(),
                }}
                sx={{ minWidth: 170 }}
              />
            </Stack>
            {loadingInvoiceLines ? (
              <Box sx={{ display: 'flex', justifyContent: 'center', py: 3 }} data-testid="return-lines-loading">
                <CircularProgress size={28} />
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
                            {t('phase1.returnLinesUnits', {
                              lines: previewData.lineCount,
                              units: previewData.units,
                            })}
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
                                {t('phase1.returnDiscountShare')}:{' '}
                                <strong>{formatMoney(previewData.invoiceDiscount)}</strong>
                              </Typography>
                            ) : null}
                            {previewData.additionalCharges > 0 ? (
                              <Typography variant="body2">
                                {t('phase1.returnChargesShare')}:{' '}
                                <strong>{formatMoney(previewData.additionalCharges)}</strong>
                              </Typography>
                            ) : null}
                            {previewData.tcsAmount > 0 ? (
                              <Typography variant="body2">
                                {t('phase1.returnTcsShare')}: <strong>{formatMoney(previewData.tcsAmount)}</strong>
                              </Typography>
                            ) : null}
                            <Typography variant="subtitle2">
                              {t('phase1.returnCreditNoteTotal')}:{' '}
                              <strong>{formatMoney(previewData.grandTotal)}</strong>
                            </Typography>
                          </Stack>
                        </Stack>
                        <Typography variant="caption" color="text.secondary">
                          {t('phase1.returnPreviewNote')}
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
            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
              <Typography variant="caption" color="text.secondary">
                {t('phase1.reasonPresetsLabel')}
              </Typography>
              {REASON_PRESETS.map((preset) => (
                <Tooltip
                  key={preset.key}
                  title={preset.damaged ? t('phase1.reasonPresetDefectiveHint') : ''}
                >
                  <Chip
                    size="small"
                    label={t(preset.labelKey)}
                    variant={reason === t(preset.labelKey) ? 'filled' : 'outlined'}
                    color={reason === t(preset.labelKey) ? 'primary' : 'default'}
                    onClick={() => applyReasonPreset(preset)}
                  />
                </Tooltip>
              ))}
            </Stack>
            <TextField label={t('common.reason')} value={reason} onChange={(e) => setReason(e.target.value)} />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={requestClose}>{t('common.cancel')}</Button>
          {canWrite ? (
            <Button
              variant="outlined"
              disabled={
                !invoice ||
                activeLines.length === 0 ||
                returnDateBeforeInvoice ||
                Boolean(missingSerialLine) ||
                saveDraftMutation.isPending ||
                createMutation.isPending
              }
              onClick={() => saveDraftMutation.mutate()}
            >
              {t('common.save')}
            </Button>
          ) : null}
          <Tooltip
            title={
              returnCompleteDisabledReason({
                writesBlocked,
                permissionDenied: !canCompleteReturn,
                pending: createMutation.isPending,
                missingSource: !invoice,
                returnDateBeforeInvoice,
                noLines: Boolean(invoice) && activeLines.length === 0,
                missingSerialName: missingSerialLine?.productName,
              }) ?? ''
            }
          >
            <span>
              <Button
                variant="contained"
                disabled={
                  !canCompleteReturn ||
                  !invoice ||
                  returnDateBeforeInvoice ||
                  activeLines.length === 0 ||
                  Boolean(missingSerialLine) ||
                  createMutation.isPending ||
                  saveDraftMutation.isPending
                }
                onClick={() => createMutation.mutate(undefined)}
              >
                {t('common.complete')}
              </Button>
            </span>
          </Tooltip>
        </DialogActions>
      </Dialog>

      {/* Sales Return Detail Dialog */}
      <Dialog open={Boolean(detailReturn)} onClose={() => setDetailReturn(null)} fullWidth maxWidth="md">
        <DialogTitle>
          {detailReturn?.number || `#${detailReturn?.id ?? ''}`} — {t('nav.salesReturns')}
        </DialogTitle>
        <DialogContent>
          {detailReturn ? (
            <Stack spacing={2} sx={{ mt: 1 }}>
              <Stack direction="row" spacing={2} flexWrap="wrap" alignItems="center" useFlexGap>
                <StatusChip
                  tone={documentStatusTone(detailReturn.status)}
                  labelKey={statusLabelKey(detailReturn.status)}
                />
                <Typography variant="body2">
                  <strong>{t('common.date')}:</strong> {detailReturn.returnDate}
                </Typography>
                <Typography variant="body2">
                  <strong>{t('billing.customer')}:</strong> {detailReturn.customerName}
                </Typography>
                <Typography variant="body2">
                  <strong>{t('phase1.sourceInvoice')}:</strong>{' '}
                  <RouterLink to={`/sales/invoices/${detailReturn.salesInvoice}`}>
                    {detailReturn.salesInvoiceNumber || `#${detailReturn.salesInvoice}`}
                  </RouterLink>
                </Typography>
                {detailReturn.creditNoteId ? (
                  <Typography variant="body2">
                    <strong>{t('phase1.linkedCreditNote')}:</strong>{' '}
                    <RouterLink to={`/sales/credit-notes/${detailReturn.creditNoteId}`}>
                      {detailReturn.creditNoteNumber || `#${detailReturn.creditNoteId}`}
                    </RouterLink>
                  </Typography>
                ) : null}
              </Stack>
              {detailReturn.reason ? (
                <Typography variant="body2" color="text.secondary">
                  <strong>{t('common.reason')}:</strong> {detailReturn.reason}
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
                    {(detailReturn.items ?? []).map((it, idx) => (
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
                  {t('phase1.detailTaxable')}: <strong>{formatMoney(detailReturn.taxableTotal)}</strong>
                </Typography>
                {toNumber(detailReturn.cgstTotal) > 0 ? (
                  <Typography variant="body2">
                    CGST: <strong>{formatMoney(detailReturn.cgstTotal)}</strong>
                  </Typography>
                ) : null}
                {toNumber(detailReturn.sgstTotal) > 0 ? (
                  <Typography variant="body2">
                    SGST: <strong>{formatMoney(detailReturn.sgstTotal)}</strong>
                  </Typography>
                ) : null}
                {toNumber(detailReturn.igstTotal) > 0 ? (
                  <Typography variant="body2">
                    IGST: <strong>{formatMoney(detailReturn.igstTotal)}</strong>
                  </Typography>
                ) : null}
                {toNumber(detailReturn.cessTotal) > 0 ? (
                  <Typography variant="body2">
                    Cess: <strong>{formatMoney(detailReturn.cessTotal ?? 0)}</strong>
                  </Typography>
                ) : null}
                {toNumber(detailReturn.roundOff) !== 0 ? (
                  <Typography variant="body2">
                    {t('phase1.detailRoundOff')}: <strong>{formatMoney(detailReturn.roundOff)}</strong>
                  </Typography>
                ) : null}
                <Typography variant="subtitle1">
                  {t('common.total')}: <strong>{formatMoney(detailReturn.grandTotal)}</strong>
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
          <Typography variant="body2">{t('phase1.cancelSalesReturnConfirm')}</Typography>
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
          <Typography variant="body2">{t('phase1.deleteSalesReturnDraftConfirm')}</Typography>
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

      {/* GST Guard blocked a draft Complete from the list */}
      <Dialog open={Boolean(rowGuard)} onClose={() => setRowGuard(null)} maxWidth="sm" fullWidth>
        <DialogTitle>{t('billing.gstGuardBlockingTitle')}</DialogTitle>
        <DialogContent>
          <Box component="ul" sx={{ m: '4px 0 8px', pl: 2.5 }}>
            {(rowGuard?.issues ?? []).map((issue) => (
              <li key={issue.code}>{issue.message}</li>
            ))}
          </Box>
          {canOverrideGstGuard(user) ? (
            <TextField
              size="small"
              fullWidth
              label={t('billing.gstGuardOverrideReasonLabel')}
              value={rowGuardReason}
              onChange={(e) => setRowGuardReason(e.target.value)}
            />
          ) : (
            <Typography variant="body2" color="text.secondary">
              {t('billing.gstGuardOverridePermissionNote')}
            </Typography>
          )}
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => {
              setRowGuard(null);
              setRowGuardReason('');
            }}
          >
            {t('common.close')}
          </Button>
          {canOverrideGstGuard(user) ? (
            <Button
              variant="contained"
              color="warning"
              disabled={!rowGuardReason.trim() || completeDraftMutation.isPending}
              onClick={() => {
                if (rowGuard) {
                  completeDraftMutation.mutate({
                    id: rowGuard.id,
                    invoiceId: rowGuard.invoiceId,
                    overrideReason: rowGuardReason.trim(),
                  });
                }
              }}
            >
              {t('billing.gstGuardOverrideButton')}
            </Button>
          ) : null}
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
