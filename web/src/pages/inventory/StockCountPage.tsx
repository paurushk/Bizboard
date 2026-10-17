import { useEffect, useMemo, useRef, useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import FormControlLabel from '@mui/material/FormControlLabel';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage, isNetworkError } from '@/api/client';
import { useAuth } from '@/auth/AuthContext';
import { enqueueDraft, listDrafts } from '@/offline/invoiceDraftCache';
import {
  requestStockFlush,
  resolveOfflineStockCountConflict,
  STOCK_COUNT_CONFLICT_EVENT,
  STOCK_FLUSHED_EVENT,
  type StockCountConflictDetail,
} from '@/pages/inventory/useStockOffline';
import {
  parseStockCountConflicts,
  parseStockCountLinesChanged,
  type LineResolution,
  type QtyConflict,
} from '@/pages/inventory/godownConflict';
import { StockConflictModal } from '@/pages/inventory/StockConflictModal';
import { AttemptKeys } from '@/pages/inventory/attemptKeys';
import {
  canPostReview,
  changedLines,
  countOneOn,
  effectiveCounted,
  effectiveSkipped,
  fillableLineCount,
  fillWithSystemQtyIds,
  hasUnsavedCounts,
  openLineCount,
  scanCandidates,
  summarizeReview,
  type CountLine,
} from '@/pages/inventory/countHelpers';
import * as api from '@/api/resources';
import { ErrorState, LoadingState } from '@/components/PageState';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { UnsavedChangesGuard } from '@/components/UnsavedChangesGuard';
import { useProductSearch } from '@/hooks/useProductSearch';
import type { Product } from '@/types/domain';
import { enumLabel } from '@/utils/enumLabels';
import { t, useLocale } from '@/i18n';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { formatMoney, toNumber } from '@/utils/money';
import { asRows, DataTable, PageShell, type Row } from '@/pages/phase/phaseShared';
import { useConfirmPrompt } from '@/hooks/useConfirmPrompt';

type Mode = 'count' | 'review';

/** How long after the last edit the counts are saved without being asked. */
export const AUTOSAVE_MS = 5000;

function linesOf(session: Row | null): CountLine[] {
  return ((session?.lines as CountLine[]) || []) as CountLine[];
}

export function StockCountPage() {
  useLocale();
  const { writesBlocked } = useSubscriptionGate();
  const { user } = useAuth();
  const qc = useQueryClient();
  const { ask, dialog } = useConfirmPrompt();
  const warehouses = useQuery({ queryKey: ['warehouses'], queryFn: api.listWarehouses });
  const counts = useQuery({ queryKey: ['stock-counts'], queryFn: api.listStockCounts });
  const [createOpen, setCreateOpen] = useState(false);
  const [warehouseId, setWarehouseId] = useState('');
  const [notes, setNotes] = useState('');
  const [blind, setBlind] = useState(false);
  const [active, setActive] = useState<Row | null>(null);
  const [mode, setMode] = useState<Mode>('count');
  const [review, setReview] = useState<Row | null>(null);
  const [rechecked, setRechecked] = useState<Record<string, boolean>>({});
  const [counted, setCounted] = useState<Record<string, string>>({});
  const [skipped, setSkipped] = useState<Record<string, boolean>>({});
  const [addProduct, setAddProduct] = useState<Product | null>(null);
  const [addBatch, setAddBatch] = useState('');
  const [addQty, setAddQty] = useState('');
  const [scan, setScan] = useState('');
  // Lines the counter confirmed with "count equals system" (kept apart from counted ones in the audit).
  const [filled, setFilled] = useState<Record<string, boolean>>({});
  // A scanned code that fits several lots of one item: the counter says which lot it was.
  const [lotChoice, setLotChoice] = useState<CountLine[] | null>(null);
  const [scanNote, setScanNote] = useState('');
  const addSearch = useProductSearch({ activeOnly: true, selected: addProduct });
  const addBatches = useQuery({
    queryKey: ['batches', addProduct?.id],
    queryFn: () => api.listBatches(Number(addProduct?.id)),
    enabled: Boolean(addProduct?.trackBatch),
  });
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [conflicts, setConflicts] = useState<QtyConflict[]>([]);
  const [offlineConflict, setOfflineConflict] = useState<StockCountConflictDetail | null>(null);
  const [lastSynced, setLastSynced] = useState<string | null>(null);
  // Counts saved on this device and not sent yet: read from the outbox, so they survive a reload.
  const queuedQuery = useQuery({
    queryKey: ['stock-count-outbox', user?.companyId, user?.id],
    queryFn: async () => {
      if (!user?.companyId || !user?.id) return [] as number[];
      const drafts = await listDrafts(user.companyId, user.id);
      return drafts
        .filter((d) => d.kind === 'stock_count')
        .map((d) => Number((d.payload as { sessionId?: number }).sessionId))
        .filter((id) => Number.isFinite(id));
    },
  });
  const queuedIds = new Set(queuedQuery.data ?? []);
  const pendingCount = queuedIds.size;
  const refetchQueued = queuedQuery.refetch;
  useEffect(() => {
    const onFlushed = () => {
      void refetchQueued();
      void qc.invalidateQueries({ queryKey: ['stock-counts'] });
    };
    window.addEventListener(STOCK_FLUSHED_EVENT, onFlushed);
    return () => window.removeEventListener(STOCK_FLUSHED_EVENT, onFlushed);
  }, [refetchQueued, qc]);
  const [posted, setPosted] = useState<{ text: string; warehouseId: number | null } | null>(null);
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null);
  const [autosaveFailed, setAutosaveFailed] = useState(false);
  // One key per attempt: kept while the outcome is unknown, dropped once the server answered.
  const attemptKeys = useRef(new AttemptKeys());

  const status = String(active?.status ?? '');
  const finished = status === 'POSTED' || status === 'CANCELLED';
  const lines = useMemo(() => linesOf(active), [active]);
  const unsaved = Boolean(active) && !finished && hasUnsavedCounts(lines, counted, skipped);
  const unsavedLines = changedLines(lines, counted, skipped, filled);
  const stillOpen = openLineCount(lines, counted, skipped);

  // CR-143: offline flush 409 → open the same conflict modal as online post.
  useEffect(() => {
    const onConflict = (event: Event) => {
      const detail = (event as CustomEvent<StockCountConflictDetail>).detail;
      if (!detail?.conflicts?.length) return;
      setOfflineConflict(detail);
      setConflicts(detail.conflicts);
    };
    window.addEventListener(STOCK_COUNT_CONFLICT_EVENT, onConflict);
    // The app shell sends queued counts. A conflict that arrived while this page was closed is
    // gone from view, so ask for another pass now that someone is listening.
    requestStockFlush();
    return () => window.removeEventListener(STOCK_COUNT_CONFLICT_EVENT, onConflict);
  }, []);

  const resetSession = () => {
    setActive(null);
    setMode('count');
    setReview(null);
    setRechecked({});
    setCounted({});
    setSkipped({});
    setFilled({});
    setLotChoice(null);
    setAddProduct(null);
    setAddBatch('');
    setAddQty('');
  };

  const closeSession = async () => {
    if (unsaved && !(await ask([t('inventory.confirmDiscardCounts')]))) return;
    resetSession();
  };

  const create = useMutation({
    mutationFn: () => api.createStockCount({ warehouse: Number(warehouseId), notes, blind }),
    onSuccess: (created) => {
      setCreateOpen(false);
      setNotes('');
      setBlind(false);
      resetSession();
      setActive(created as Row);
      void qc.invalidateQueries({ queryKey: ['stock-counts'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  // Only the lines changed on this screen are sent, each with the version it was loaded at: another
  // counter's lines are not overwritten, and a line they changed since is refused (INV-IDR-04).
  const saveBody = () => ({
    lines: unsavedLines.map((line) => {
      const typed = effectiveCounted(line, counted).trim();
      const key = String(line.id);
      return {
        id: line.id,
        countedQty: typed === '' ? null : typed,
        skipped: effectiveSkipped(line, skipped),
        version: line.version,
        ...(filled[key] !== undefined && filled[key] !== Boolean(line.filledFromSystem)
          ? { filledFromSystem: filled[key] }
          : {}),
      };
    }),
  });

  // 409: someone else saved these lines first. Take their values for those lines, keep ours for the rest.
  const takeTheirLines = async (err: unknown): Promise<boolean> => {
    const changedByOthers = parseStockCountLinesChanged(err);
    if (!changedByOthers || !active?.id) return false;
    const ids = new Set(changedByOthers.map((row) => String(row.lineId)));
    const drop = <T,>(cur: Record<string, T>) => Object.fromEntries(Object.entries(cur).filter(([key]) => !ids.has(key)));
    try {
      setActive((await api.getStockCount(Number(active.id))) as Row);
    } catch {
      // The message below still tells the counter to reload.
    }
    setCounted(drop);
    setSkipped(drop);
    setFilled(drop);
    setError(t('inventory.countLineChanged', { names: changedByOthers.map((row) => row.productName).join(', ') }));
    return true;
  };

  // What a save sent. After it lands only those entries are cleared, so a figure typed while the save
  // was in flight is not lost.
  type SaveSnapshot = {
    body: ReturnType<typeof saveBody>;
    counted: Record<string, string>;
    skipped: Record<string, boolean>;
    filled: Record<string, boolean>;
    silent?: boolean;
  };
  const snapshot = (silent = false): SaveSnapshot => ({
    body: saveBody(),
    counted: { ...counted },
    skipped: { ...skipped },
    filled: { ...filled },
    silent,
  });
  const clearSent = <T,>(current: Record<string, T>, sent: Record<string, T>) =>
    Object.fromEntries(Object.entries(current).filter(([key, value]) => !(key in sent) || sent[key] !== value));

  const saveLines = useMutation({
    mutationFn: async (snap: SaveSnapshot) => {
      if (!active?.id) return null;
      if (snap.body.lines.length === 0) return active;
      return api.updateStockCount(Number(active.id), snap.body);
    },
    onSuccess: (updated, snap) => {
      if (updated) {
        setActive(updated as Row);
        setCounted((current) => clearSent(current, snap.counted));
        setSkipped((current) => clearSent(current, snap.skipped));
        setFilled((current) => clearSent(current, snap.filled));
      }
      setLastSavedAt(new Date());
      setAutosaveFailed(false);
      void qc.invalidateQueries({ queryKey: ['stock-counts'] });
    },
    onError: async (err, snap) => {
      if (await takeTheirLines(err)) return;
      // A background save that fails (no signal on the shop floor) is not an error dialog; the status
      // line says the counts are not saved and the next edit or a press of Save tries again.
      if (snap.silent) setAutosaveFailed(true);
      else setError(getErrorMessage(err));
    },
  });

  const startReview = useMutation({
    mutationFn: async () => {
      const id = Number(active?.id);
      const saved = (unsavedLines.length ? await api.updateStockCount(id, saveBody()) : active) as Row;
      if (String(saved.status) !== 'COUNTED') throw new Error(t('inventory.countOpenLines', { count: String(stillOpen) }));
      const reviewed = (await api.reviewStockCount(id)) as Row;
      return { saved, reviewed };
    },
    onSuccess: ({ saved, reviewed }) => {
      setActive(saved);
      setReview(reviewed);
      setRechecked({});
      setCounted({});
      setSkipped({});
      setFilled({});
      setMode('review');
      setError('');
      void qc.invalidateQueries({ queryKey: ['stock-counts'] });
    },
    onError: async (err) => {
      if (!(await takeTheirLines(err))) setError(getErrorMessage(err));
    },
  });

  const addLine = useMutation({
    mutationFn: () =>
      api.addStockCountLine(Number(active?.id), {
        product: Number(addProduct?.id),
        batch: addBatch ? Number(addBatch) : undefined,
        countedQty: addQty,
      }),
    onSuccess: (updated) => {
      setActive(updated as Row);
      setAddProduct(null);
      setAddBatch('');
      setAddQty('');
      setError('');
      void qc.invalidateQueries({ queryKey: ['stock-counts'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  // Save by itself a few seconds after the last edit (INV-IDR-05).
  const savePending = saveLines.isPending || startReview.isPending;
  useEffect(() => {
    if (!active?.id || finished || mode !== 'count' || writesBlocked || savePending) return;
    if (changedLines(lines, counted, skipped, filled).length === 0) return;
    if (typeof navigator !== 'undefined' && !navigator.onLine) return;
    const timer = window.setTimeout(() => saveLines.mutate(snapshot(true)), AUTOSAVE_MS);
    return () => window.clearTimeout(timer);
    // The snapshot is read when the timer fires; the edits are the dependencies.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [counted, skipped, filled, active, finished, mode, writesBlocked, savePending]);

  const post = useMutation({
    mutationFn: async (resolutions?: Record<number, LineResolution>) => {
      const id = Number(active?.id);
      // The queued copy keeps a stable key (a replay of the same request is what is wanted there);
      // an online post gets one key per attempt.
      const queuedKey = `stock-count-${id}`;
      // The server refuses a large difference unless its line is named as rechecked.
      const recheckedLineIds = Object.entries(rechecked).filter(([, ticked]) => ticked).map(([lineId]) => Number(lineId));
      const queue = async () => {
        const companyId = user?.companyId;
        const userId = user?.id;
        if (!companyId || !userId) throw new Error(t('inventory.offlineNeedLogin'));
        await enqueueDraft(companyId, userId, {
          kind: 'stock_count',
          // Counts are saved before the review step, so there is nothing typed left to carry.
          payload: { sessionId: id, lines: counted, resolutions: resolutions ?? {}, recheckedLineIds },
          idempotencyKey: queuedKey,
        });
        return { offline: true as const };
      };
      if (typeof navigator !== 'undefined' && !navigator.onLine) {
        return queue();
      }
      try {
        return await api.postStockCount(
          id,
          resolutions ? { resolutions, recheckedLineIds } : { recheckedLineIds },
          { idempotencyKey: attemptKeys.current.get(`post-${id}`) },
        );
      } catch (err) {
        // R-046: CSRF/network reject must queue, not drop the count.
        if (isNetworkError(err)) return queue();
        throw err;
      }
    },
    onSuccess: (result) => {
      attemptKeys.current.settle(`post-${Number(active?.id)}`);
      setConflicts([]);
      if (result && typeof result === 'object' && 'offline' in result) {
        void queuedQuery.refetch();
        setError('');
        setNotice(t('inventory.queuedOffline'));
        resetSession();
        return;
      }
      if ((result as { status?: string } | null)?.status === 'PENDING') {
        // Not posted: the owner has to approve it first. The count stays open in the list.
        setError('');
        setNotice(t('inventory.countPendingApproval'));
        resetSession();
        void qc.invalidateQueries({ queryKey: ['stock-counts'] });
        return;
      }
      setLastSynced(new Date().toISOString());
      // Say what happened: how many lines moved stock and what that was worth, and what was left alone.
      const doneLines = linesOf(result as Row).filter((line) => !line.driftSkipped);
      const totals = summarizeReview(doneLines);
      const left = linesOf(result as Row).filter((line) => line.driftSkipped).length;
      const warehouseId = Number((result as Row | null)?.warehouse);
      setPosted({
        text:
          t('inventory.countPosted', {
            changed: String(totals.changed),
            gain: formatMoney(totals.gain),
            loss: formatMoney(totals.loss),
          }) + (left ? ` ${t('inventory.countPostedNotReconciled', { count: String(left) })}` : ''),
        warehouseId: Number.isFinite(warehouseId) && warehouseId > 0 ? warehouseId : null,
      });
      setNotice('');
      resetSession();
      void qc.invalidateQueries({ queryKey: ['stock-counts'] });
      void qc.invalidateQueries({ queryKey: ['stock'] });
      void qc.invalidateQueries({ queryKey: ['low-stock'] });
    },
    onError: (err) => {
      attemptKeys.current.settle(`post-${Number(active?.id)}`, err);
      const rows = parseStockCountConflicts(err);
      if (rows) {
        setConflicts(rows);
        return;
      }
      setError(getErrorMessage(err));
    },
  });

  const cancel = useMutation({
    mutationFn: () => api.cancelStockCount(Number(active?.id)),
    onSuccess: () => {
      resetSession();
      void qc.invalidateQueries({ queryKey: ['stock-counts'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const rows = asRows(counts.data);
  const reviewLines = useMemo(() => linesOf(review), [review]);
  const summary = useMemo(() => summarizeReview(reviewLines), [reviewLines]);
  const notReconciled = lines.filter((line) => line.driftSkipped).length;

  if (counts.isLoading) return <LoadingState />;
  if (counts.isError) {
    return <ErrorState message={getErrorMessage(counts.error)} error={counts.error} onRetry={() => void counts.refetch()} />;
  }

  const confirmPost = async () => {
    const message = t('inventory.confirmPostCountTotals', {
      changed: String(summary.changed),
      gain: formatMoney(summary.gain),
      loss: formatMoney(summary.loss),
    });
    if (!(await ask([message]))) return;
    post.mutate(undefined);
  };

  return (
    <PageShell
      title={t('inventory.stockCounts')}
      subtitle={t('inventory.stockCountsSubtitle')}
      actions={
        <Stack direction="row" spacing={1}>
          <Button variant="contained" onClick={() => setCreateOpen(true)} disabled={writesBlocked}>
            {t('sweep2.newCount')}
          </Button>
        </Stack>
      }
    >
      {error && !active ? (
        <HelpErrorAlert message={error} sx={{ mb: 2 }} onClose={() => setError('')} />
      ) : null}
      {notice ? (
        <Alert severity="info" sx={{ mb: 2 }} onClose={() => setNotice('')}>
          {notice}
        </Alert>
      ) : null}
      {posted ? (
        <Alert
          severity="success"
          sx={{ mb: 2 }}
          onClose={() => setPosted(null)}
          action={
            <Button
              color="inherit"
              size="small"
              component={RouterLink}
              to={posted.warehouseId ? `/inventory/ledger?warehouse=${posted.warehouseId}` : '/inventory/ledger'}
            >
              {t('inventory.countViewLedger')}
            </Button>
          }
        >
          {posted.text}
        </Alert>
      ) : null}
      <Alert severity="info" sx={{ mb: 2 }}>
        {t('inventory.lastSynced', {
          when: lastSynced ? new Date(lastSynced).toLocaleString() : t('inventory.neverSynced'),
          count: String(pendingCount),
        })}
        {' · '}
        {t('inventory.offlineTarget')}
      </Alert>
      <StockConflictModal
        key={conflicts.map((row) => row.lineId).join(',')}
        open={conflicts.length > 0}
        conflicts={conflicts}
        onCancel={() => {
          setConflicts([]);
          setOfflineConflict(null);
        }}
        onResolve={(resolutions) => {
          if (offlineConflict) {
            void resolveOfflineStockCountConflict({
              sessionId: offlineConflict.sessionId,
              resolutions,
              idempotencyKey: offlineConflict.idempotencyKey,
              companyId: offlineConflict.companyId,
              userId: offlineConflict.userId,
            })
              .then(() => {
                setConflicts([]);
                setOfflineConflict(null);
                void queuedQuery.refetch();
                void qc.invalidateQueries({ queryKey: ['stock-counts'] });
                void qc.invalidateQueries({ queryKey: ['stock'] });
              })
              .catch((err) => setError(getErrorMessage(err)));
            return;
          }
          post.mutate(resolutions);
        }}
      />
      <DataTable
        rows={rows}
        empty={t('items.noStockCounts')}
        columns={[
          { key: 'id', label: '#' },
          { key: 'warehouseName', label: t('items.godown') },
          { key: 'status', label: t('common.status'), status: true },
          { key: 'countedOn', label: t('items.countedOn') },
          { key: 'notes', label: t('common.notes') },
          {
            key: 'queued',
            label: '',
            render: (row) =>
              queuedIds.has(Number(row.id)) ? <Chip size="small" color="warning" label={t('inventory.countQueuedChip')} /> : null,
          },
        ]}
        actions={(row) => (
          <Button
            size="small"
            onClick={async () => {
              setError('');
              resetSession();
              // F3-040: list rows don't carry `.lines` — fetch the detail so
              // the dialog isn't empty until a saveLines round-trip.
              try {
                const full = await api.getStockCount(Number(row.id));
                setActive(full as Row);
              } catch (err) {
                setActive(row);
                setError(getErrorMessage(err));
              }
            }}
          >
            {String(row.status) === 'POSTED' ? t('items.view') : t('items.count')}
          </Button>
        )}
      />

      <Dialog open={createOpen} onClose={() => setCreateOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>{t('items.newStockCount')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField select label={t('items.godown')} value={warehouseId} onChange={(e) => setWarehouseId(e.target.value)}>
              {(warehouses.data ?? []).map((warehouse) => (
                <MenuItem key={warehouse.id} value={String(warehouse.id)}>
                  {warehouse.name}
                </MenuItem>
              ))}
            </TextField>
            <TextField label={t('common.notes')} value={notes} onChange={(e) => setNotes(e.target.value)} />
            <FormControlLabel
              control={<Checkbox checked={blind} onChange={(e) => setBlind(e.target.checked)} />}
              label={t('inventory.countBlind')}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateOpen(false)}>{t('common.cancel')}</Button>
          <Button variant="contained" disabled={!warehouseId || create.isPending} onClick={() => create.mutate()}>
            {t('items.startCount')}
          </Button>
        </DialogActions>
      </Dialog>

      <UnsavedChangesGuard when={unsaved} />
      <Dialog open={Boolean(active)} onClose={closeSession} fullWidth maxWidth="md">
        <DialogTitle>
          {t('items.countTitle', { name: String(active?.warehouseName || ''), status: enumLabel('countStatus', status) })}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={1.5} sx={{ mt: 1 }}>
            {error ? <HelpErrorAlert message={error} onClose={() => setError('')} /> : null}
            {!finished && mode === 'count' ? (
              <Typography variant="caption" color={autosaveFailed ? 'warning.main' : 'text.secondary'} className="no-print" role="status">
                {saveLines.isPending
                  ? t('inventory.countSaving')
                  : autosaveFailed
                    ? t('inventory.countAutosaveFailed')
                    : unsavedLines.length
                      ? t('inventory.countUnsaved')
                      : lastSavedAt
                        ? t('inventory.countSavedAt', { time: lastSavedAt.toLocaleTimeString() })
                        : ''}
              </Typography>
            ) : null}
            {status === 'POSTED' && notReconciled > 0 ? (
              <Alert severity="warning">{t('inventory.countNotReconciledNote', { count: String(notReconciled) })}</Alert>
            ) : null}

            {mode === 'review' ? (
              <>
                <Alert severity={summary.changed ? 'info' : 'success'}>
                  {t('inventory.countReviewSummary', {
                    changed: String(summary.changed),
                    gain: formatMoney(summary.gain),
                    loss: formatMoney(summary.loss),
                    skipped: String(summary.skipped),
                  })}
                </Alert>
                {summary.recheck > 0 ? (
                  <Alert severity="warning">{t('inventory.countRecheckWarn', { count: String(summary.recheck) })}</Alert>
                ) : null}
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>{t('items.item')}</TableCell>
                      <TableCell align="right">{t('inventory.countColSystem')}</TableCell>
                      <TableCell align="right">{t('items.counted')}</TableCell>
                      <TableCell align="right">{t('inventory.countColDiff')}</TableCell>
                      <TableCell align="right">{t('inventory.countColValue')}</TableCell>
                      <TableCell />
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {reviewLines
                      .filter((line) => !line.skipped)
                      .map((line) => {
                        const diff = toNumber(line.variance);
                        return (
                          <TableRow key={String(line.id)} sx={line.needsRecheck ? { bgcolor: 'warning.light' } : undefined}>
                            <TableCell>
                              {line.productName}
                              {line.batchNo ? ` · ${line.batchNo}` : ''}
                              {line.filledFromSystem ? (
                                <Chip size="small" color="warning" variant="outlined" label={t('inventory.countFilledBadge')} sx={{ ml: 1 }} />
                              ) : null}
                            </TableCell>
                            <TableCell align="right">{toNumber(line.systemQty)}</TableCell>
                            <TableCell align="right">{toNumber(line.countedQty)}</TableCell>
                            <TableCell align="right" sx={{ color: diff < 0 ? 'error.main' : diff > 0 ? 'success.main' : undefined, fontWeight: 600 }}>
                              {diff > 0 ? `+${diff}` : diff}
                            </TableCell>
                            <TableCell align="right">{formatMoney(toNumber(line.varianceValueEstimate))}</TableCell>
                            <TableCell>
                              {line.needsRecheck ? (
                                <FormControlLabel
                                  control={
                                    <Checkbox
                                      size="small"
                                      checked={Boolean(rechecked[String(line.id)])}
                                      onChange={(e) => setRechecked((cur) => ({ ...cur, [String(line.id)]: e.target.checked }))}
                                    />
                                  }
                                  label={t('inventory.countRechecked')}
                                />
                              ) : null}
                            </TableCell>
                          </TableRow>
                        );
                      })}
                  </TableBody>
                </Table>
              </>
            ) : (
              <>
                {lines.length === 0 ? <Typography color="text.secondary">{t('items.noOnHand')}</Typography> : null}
                {!finished && lines.length > 0 ? (
                  <TextField
                    size="small"
                    className="no-print"
                    label={t('inventory.countScan')}
                    helperText={scanNote || t('inventory.countScanHelp')}
                    error={Boolean(scanNote)}
                    value={scan}
                    onChange={(e) => {
                      setScan(e.target.value);
                      setScanNote('');
                    }}
                    onKeyDown={(e) => {
                      if (e.key !== 'Enter') return;
                      e.preventDefault();
                      const matches = scanCandidates(lines, skipped, scan);
                      if (matches.length === 0) {
                        setScanNote(t('inventory.countScanUnknown', { code: scan.trim() }));
                        return;
                      }
                      // Several lots of one item: the barcode cannot say which, so ask.
                      if (matches.length > 1) {
                        setLotChoice(matches);
                        return;
                      }
                      setCounted(countOneOn(matches[0], counted));
                      setFilled((cur) => ({ ...cur, [String(matches[0].id)]: false }));
                      setScan('');
                      setScanNote('');
                    }}
                  />
                ) : null}
                {/* F3-016: deliberately NOT virtualized — "Print sheet" below
                    relies on every line being in the DOM (a windowed list would
                    only print the currently-visible rows), which matters more
                    here than render cost for what's normally a bounded per-
                    godown SKU count. */}
                {lines.map((line) => {
                  const isSkipped = effectiveSkipped(line, skipped);
                  return (
                    <Stack key={String(line.id)} direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems="center">
                      <Typography sx={{ flex: 1 }}>
                        {String(line.productName || line.product)} {line.batchNo ? `· ${line.batchNo}` : ''}
                      </Typography>
                      {status === 'POSTED' ? (
                        <Typography variant="body2" color="text.secondary">
                          {t('inventory.countColSystem')} {String(line.systemQty ?? 0)}
                        </Typography>
                      ) : null}
                      {line.driftSkipped ? <Chip size="small" color="warning" label={t('inventory.countNotReconciled')} /> : null}
                      {line.skipped && finished ? <Chip size="small" label={t('inventory.countSkipped')} /> : null}
                      <TextField
                        size="small"
                        label={t('items.counted')}
                        type="number"
                        value={effectiveCounted(line, counted)}
                        onChange={(e) => {
                          setCounted((current) => ({ ...current, [String(line.id)]: e.target.value }));
                          setFilled((current) => ({ ...current, [String(line.id)]: false }));
                        }}
                        disabled={finished || isSkipped}
                        sx={{ width: 140 }}
                      />
                      {!finished ? (
                        <FormControlLabel
                          control={
                            <Checkbox
                              size="small"
                              checked={isSkipped}
                              onChange={(e) => setSkipped((current) => ({ ...current, [String(line.id)]: e.target.checked }))}
                            />
                          }
                          label={t('inventory.countSkip')}
                        />
                      ) : null}
                    </Stack>
                  );
                })}
                {!finished ? (
                  <Stack spacing={1} sx={{ pt: 1, borderTop: 1, borderColor: 'divider' }} className="no-print">
                    <Typography variant="subtitle2">{t('inventory.countAddItem')}</Typography>
                    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
                      <Autocomplete<Product>
                        sx={{ flex: 1 }}
                        options={addSearch.options}
                        loading={addSearch.isFetching}
                        filterOptions={(opts) => opts}
                        inputValue={addSearch.productQuery}
                        onInputChange={(_, v, reason) => {
                          if (reason === 'input' || reason === 'clear' || reason === 'reset') addSearch.setProductQuery(v);
                        }}
                        getOptionLabel={(o) => `${o.name} · ${o.sku}`}
                        value={addProduct}
                        onChange={(_, v) => {
                          setAddProduct(v);
                          setAddBatch('');
                        }}
                        renderInput={(params) => <TextField {...params} size="small" label={t('items.item')} />}
                      />
                      {addProduct?.trackBatch ? (
                        <TextField
                          select
                          size="small"
                          label={t('inventory.transferBatch')}
                          value={addBatch}
                          onChange={(e) => setAddBatch(e.target.value)}
                          sx={{ minWidth: 150 }}
                        >
                          {(addBatches.data ?? []).map((lot) => (
                            <MenuItem key={String(lot.id)} value={String(lot.id)}>
                              {lot.batchNo}
                            </MenuItem>
                          ))}
                        </TextField>
                      ) : null}
                      <TextField
                        size="small"
                        type="number"
                        label={t('inventory.countAddQty')}
                        value={addQty}
                        onChange={(e) => setAddQty(e.target.value)}
                        inputProps={{ min: 0, step: 'any' }}
                        sx={{ width: 150 }}
                      />
                      <Button
                        variant="outlined"
                        disabled={
                          writesBlocked ||
                          addLine.isPending ||
                          !addProduct ||
                          addQty.trim() === '' ||
                          (Boolean(addProduct?.trackBatch) && !addBatch)
                        }
                        onClick={() => addLine.mutate()}
                      >
                        {t('inventory.countAddButton')}
                      </Button>
                    </Stack>
                  </Stack>
                ) : null}
                {!finished && stillOpen > 0 ? (
                  <Typography variant="body2" color="text.secondary">
                    {t('inventory.countOpenLines', { count: String(stillOpen) })}
                  </Typography>
                ) : null}
              </>
            )}
          </Stack>
        </DialogContent>
        <DialogActions className="no-print">
          <Button onClick={closeSession}>{t('common.close')}</Button>
          <Button onClick={() => window.print()}>{t('items.printSheet')}</Button>
          {!finished && mode === 'count' ? (
            <>
              {fillableLineCount(lines, counted, skipped) > 0 ? (
                <Button
                  onClick={() => {
                    const result = fillWithSystemQtyIds(lines, counted, skipped);
                    setCounted(result.typed);
                    setFilled((current) => ({ ...current, ...Object.fromEntries(result.ids.map((id) => [id, true])) }));
                  }}
                >
                  {t('inventory.countFillSystem')}
                </Button>
              ) : null}
              {stillOpen > 0 ? (
                <Button
                  onClick={() =>
                    setSkipped((current) => {
                      const next = { ...current };
                      for (const line of lines) {
                        if (effectiveCounted(line, counted).trim() === '') next[String(line.id)] = true;
                      }
                      return next;
                    })
                  }
                >
                  {t('inventory.countSkipAll')}
                </Button>
              ) : null}
              <Button onClick={() => saveLines.mutate(snapshot())} disabled={writesBlocked || saveLines.isPending}>
                {t('items.saveCounts')}
              </Button>
              <Button
                color="warning"
                onClick={async () => {
                  if (!(await ask([t('inventory.confirmCancelCount')]))) return;
                  cancel.mutate();
                }}
                disabled={writesBlocked || cancel.isPending}
              >
                {t('items.cancelCount')}
              </Button>
              <Button
                variant="contained"
                onClick={() => startReview.mutate()}
                disabled={writesBlocked || startReview.isPending || stillOpen > 0}
              >
                {t('inventory.countReview')}
              </Button>
            </>
          ) : null}
          {!finished && mode === 'review' ? (
            <>
              <Button onClick={() => setMode('count')}>{t('inventory.countBackToCounting')}</Button>
              <Button
                variant="contained"
                onClick={confirmPost}
                disabled={writesBlocked || post.isPending || !canPostReview(reviewLines, rechecked)}
              >
                {t('items.postVariances')}
              </Button>
            </>
          ) : null}
        </DialogActions>
      </Dialog>

      <Dialog open={Boolean(lotChoice)} onClose={() => setLotChoice(null)} fullWidth maxWidth="xs">
        <DialogTitle>{t('inventory.countScanWhichLot')}</DialogTitle>
        <DialogContent>
          <Stack spacing={1} sx={{ mt: 1 }}>
            {(lotChoice ?? []).map((candidate) => (
              <Button
                key={String(candidate.id)}
                variant="outlined"
                onClick={() => {
                  setCounted((current) => countOneOn(candidate, current));
                  setFilled((current) => ({ ...current, [String(candidate.id)]: false }));
                  setLotChoice(null);
                  setScan('');
                  setScanNote('');
                }}
              >
                {candidate.productName} · {candidate.batchNo || t('inventory.countNoLot')}
              </Button>
            ))}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setLotChoice(null)}>{t('common.cancel')}</Button>
        </DialogActions>
      </Dialog>
      {dialog}
    </PageShell>
  );
}
