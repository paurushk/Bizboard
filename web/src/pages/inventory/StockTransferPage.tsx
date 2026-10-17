import { useEffect, useRef, useState } from 'react';
import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
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
import { useSearchParams } from 'react-router-dom';
import { fefoLot } from '@/pages/inventory/fefo';
import { AttemptKeys } from '@/pages/inventory/attemptKeys';
import { getErrorMessage, isNetworkError } from '@/api/client';
import * as api from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { CustomFieldFilterBar } from '@/components/CustomFieldFilterBar';
import { ErrorState, LoadingState } from '@/components/PageState';
import { useVisibleCustomFieldDefs } from '@/hooks/useActiveCustomFieldDefs';
import { useProductSearch } from '@/hooks/useProductSearch';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { t } from '@/i18n';
import { enqueueDraft, listDrafts } from '@/offline/invoiceDraftCache';
import { STOCK_FLUSHED_EVENT } from '@/pages/inventory/useStockOffline';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import {
  buildReceipts,
  lineProblem,
  receivedProblem,
  splitSerials,
  filterTransfers,
  openShortages,
  summarizeLines,
  TRANSIT_STALE_DAYS,
  transferActions,
  transitDays,
  type LineDraft,
} from '@/pages/inventory/transferHelpers';
import { asRows, DataTable, PageShell, type Row } from '@/pages/phase/phaseShared';
import type { Product } from '@/types/domain';
import { toNumber } from '@/utils/money';
import { useConfirmPrompt } from '@/hooks/useConfirmPrompt';

let lineSeq = 0;
const newLine = (over: Partial<LineDraft> = {}): LineDraft => ({
  key: `line-${(lineSeq += 1)}`,
  product: null,
  batch: '',
  qty: '1',
  serials: '',
  ...over,
});

interface TransferLineView {
  id?: number;
  product: number;
  productName?: string;
  batchNo?: string | null;
  quantity: string | number;
  shortageQty?: string | number | null;
  shortageReason?: string;
  shortageResolution?: string;
}

function linesOf(row: Row): TransferLineView[] {
  return Array.isArray(row.lines) ? (row.lines as TransferLineView[]) : [];
}

/** One line of the new-transfer form: item, lot at the source godown, quantity, serials. */
function TransferLineEditor({
  line,
  fromWh,
  fromName,
  cfFilters,
  onChange,
  onRemove,
  canRemove,
}: {
  line: LineDraft;
  fromWh: string;
  fromName: string;
  cfFilters: Record<string, string[]>;
  onChange: (next: Partial<LineDraft>) => void;
  onRemove: () => void;
  canRemove: boolean;
}) {
  const search = useProductSearch({ activeOnly: true, selected: line.product, cf: cfFilters });
  const product = line.product;
  const batches = useQuery({
    queryKey: ['batches', product?.id, fromWh],
    queryFn: () => api.listBatches(Number(product?.id), fromWh ? Number(fromWh) : undefined),
    enabled: Boolean(product?.trackBatch),
  });
  // Default to the lot that expires first; the user can still pick another.
  const firstLot = fefoLot(batches.data ?? []);
  useEffect(() => {
    if (product?.trackBatch && !line.batch && firstLot) onChange({ batch: String(firstLot.id) });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [firstLot?.id, product?.id, line.batch]);
  const stock = useQuery({
    queryKey: ['stock', 'transfer-available', product?.id, fromWh],
    queryFn: () => api.listStock({ productIds: [Number(product?.id)], warehouse: Number(fromWh) }),
    enabled: Boolean(product?.id && fromWh),
  });
  const available = (stock.data ?? []).reduce((sum, row) => sum + toNumber(row.available), 0);
  const qty = Number(line.qty);
  const serialCount = splitSerials(line.serials).length;
  return (
    <Stack spacing={1.5} sx={{ p: 1.5, border: 1, borderColor: 'divider', borderRadius: 1 }}>
      <Autocomplete<Product>
        options={search.options}
        loading={search.isFetching}
        filterOptions={(opts) => opts}
        inputValue={search.productQuery}
        onInputChange={(_, v, reason) => {
          if (reason === 'input' || reason === 'clear' || reason === 'reset') search.setProductQuery(v);
        }}
        getOptionLabel={(o) => `${o.name} · ${o.sku}`}
        value={product}
        onChange={(_, v) => onChange({ product: v, productId: undefined, batch: '', serials: '' })}
        renderInput={(params) => <TextField {...params} label={t('phase.product')} helperText={search.helperText} />}
      />
      {product && fromWh ? (
        <Typography variant="caption" color={Number.isFinite(qty) && qty > available ? 'warning.main' : 'text.secondary'}>
          {t('inventory.transferAvailableAt', { godown: fromName, qty: String(available) })}
        </Typography>
      ) : null}
      {product?.trackBatch ? (
        <TextField
          select
          required
          label={t('inventory.transferBatch')}
          value={line.batch}
          onChange={(e) => onChange({ batch: e.target.value })}
        >
          {(batches.data ?? []).map((lot) => (
            <MenuItem key={String(lot.id)} value={String(lot.id)}>
              {lot.batchNo}
              {lot.expiryDate ? ` · exp ${lot.expiryDate}` : ''}
            </MenuItem>
          ))}
        </TextField>
      ) : null}
      <Stack direction="row" spacing={1} alignItems="flex-start">
        <TextField
          label={t('phase.quantity')}
          type="number"
          value={line.qty}
          inputProps={{ min: 0, step: 'any' }}
          onChange={(e) => onChange({ qty: e.target.value })}
          error={line.qty.trim() !== '' && !(qty > 0)}
          sx={{ maxWidth: 180 }}
        />
        {canRemove ? (
          <Button color="error" size="small" onClick={onRemove} sx={{ mt: 1 }}>
            {t('inventory.transferRemoveLine')}
          </Button>
        ) : null}
      </Stack>
      {product?.trackSerial ? (
        <TextField
          label={t('phase.serialsOptional')}
          multiline
          minRows={2}
          value={line.serials}
          onChange={(e) => onChange({ serials: e.target.value })}
          error={serialCount > 0 && serialCount !== qty}
          helperText={
            serialCount !== qty && Number.isFinite(qty) && qty > 0
              ? t('inventory.transferSerialCount', { qty: String(qty), count: String(serialCount) })
              : t('phase.serialsMatchQty')
          }
        />
      ) : null}
    </Stack>
  );
}

export function StockTransferPage() {
  const { writesBlocked } = useSubscriptionGate();
  const { user } = useAuth();
  const qc = useQueryClient();
  const { ask, dialog } = useConfirmPrompt();
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  // One key per attempt: kept while the outcome is unknown, dropped once the server answered.
  const attemptKeys = useRef(new AttemptKeys());
  const query = useQuery({ queryKey: ['transfers'], queryFn: api.listTransfers });
  // Dispatches saved on this device and not sent yet: those rows show "Queued" instead of a plain draft.
  const queuedQuery = useQuery({
    queryKey: ['transfers-outbox', user?.companyId, user?.id],
    queryFn: async () => {
      if (!user?.companyId || !user?.id) return [] as number[];
      const drafts = await listDrafts(user.companyId, user.id);
      return drafts
        .filter((d) => d.kind === 'stock_transfer')
        .map((d) => Number((d.payload as { transferId?: number }).transferId))
        .filter((id) => Number.isFinite(id));
    },
  });
  const refetchQueued = queuedQuery.refetch;
  useEffect(() => {
    const onFlushed = () => {
      void refetchQueued();
      void qc.invalidateQueries({ queryKey: ['transfers'] });
    };
    window.addEventListener(STOCK_FLUSHED_EVENT, onFlushed);
    return () => window.removeEventListener(STOCK_FLUSHED_EVENT, onFlushed);
  }, [refetchQueued, qc]);
  const queuedIds = new Set(queuedQuery.data ?? []);
  const warehouses = useQuery({ queryKey: ['warehouses'], queryFn: api.listWarehouses });
  const customDefs = useVisibleCustomFieldDefs();
  const [cfFilters, setCfFilters] = useState<Record<string, string[]>>({});

  const [open, setOpen] = useState(false);
  const [fromWh, setFromWh] = useState('');
  const [toWh, setToWh] = useState('');
  const [lines, setLines] = useState<LineDraft[]>([newLine()]);
  const [draftNotes, setDraftNotes] = useState('');
  const [filter, setFilter] = useState({ status: '', q: '' });
  const [showProblems, setShowProblems] = useState(false);
  const [detail, setDetail] = useState<Row | null>(null);
  const [receiving, setReceiving] = useState<Row | null>(null);
  const [received, setReceived] = useState<Record<string, string>>({});
  const [reasons, setReasons] = useState<Record<string, string>>({});

  // Prefill from the address bar (?product, ?from, ?to, ?qty, ?lines): the replenishment plan links here.
  const [searchParams] = useSearchParams();
  const prefillKey = searchParams.toString();
  const [seenPrefillKey, setSeenPrefillKey] = useState<string | null>(null);
  if (seenPrefillKey !== prefillKey) {
    setSeenPrefillKey(prefillKey);
    const params = new URLSearchParams(prefillKey);
    const productId = params.get('product');
    const from = params.get('from');
    const to = params.get('to');
    const presetQty = params.get('qty');
    const linesParam = params.get('lines');
    if (from) setFromWh(from);
    if (to) setToWh(to);
    if (linesParam) {
      try {
        const parsed = JSON.parse(linesParam) as Array<{ productId: number; qty: string; warehouseId?: number }>;
        if (parsed.length) {
          setLines(parsed.map((p) => newLine({ productId: Number(p.productId), qty: String(p.qty) })));
          if (parsed[0].warehouseId) setToWh(String(parsed[0].warehouseId));
          setOpen(true);
        }
      } catch {
        // A mangled link just opens an empty form.
      }
    } else if (productId) {
      setLines([newLine({ productId: Number(productId), qty: presetQty || '1' })]);
      if (from && to) setOpen(true);
    } else if (presetQty) {
      setLines([newLine({ qty: presetQty })]);
    }
  }

  // Resolve the product ids a link carried into products.
  const pendingIds = lines.filter((l) => l.productId && !l.product).map((l) => l.productId as number);
  const pendingKey = pendingIds.join(',');
  useEffect(() => {
    if (!pendingKey) return;
    for (const id of pendingKey.split(',').map(Number)) {
      void api.getProduct(id).then((product) => {
        setLines((current) =>
          current.map((l) => (l.productId === id && !l.product ? { ...l, product, productId: undefined } : l)),
        );
      });
    }
  }, [pendingKey]);

  const activeWarehouses = (warehouses.data ?? []).filter((w) => w.isActive !== false);
  const nameOf = (id: string | number) =>
    (warehouses.data ?? []).find((w) => String(w.id) === String(id))?.name ?? String(id);

  const problemFor = (line: LineDraft) => lineProblem(line);
  const formProblem = (() => {
    if (!fromWh || !toWh || fromWh === toWh) return t('phase.chooseDifferentGodown');
    for (const line of lines) {
      const problem = problemFor(line);
      if (!problem) continue;
      if (problem.code === 'product') return t('inventory.transferNeedProduct');
      if (problem.code === 'qty') return t('inventory.transferQtyInvalid');
      if (problem.code === 'batch') return t('inventory.transferBatchNeeded');
      return t('inventory.transferSerialCount', { qty: String(problem.qty), count: String(problem.count) });
    }
    return '';
  })();

  const create = useMutation({
    mutationFn: () =>
      api.createTransfer({
        fromWarehouse: Number(fromWh),
        toWarehouse: Number(toWh),
        ...(draftNotes.trim() ? { notes: draftNotes.trim() } : {}),
        lines: lines.map((line) => ({
          product: Number(line.product?.id),
          batch: line.batch ? Number(line.batch) : null,
          quantity: line.qty,
          ...(line.product?.trackSerial ? { serialNumbers: splitSerials(line.serials) } : {}),
        })),
      }, { idempotencyKey: attemptKeys.current.get('create') }),
    onSuccess: () => {
      attemptKeys.current.settle('create');
      setOpen(false);
      setLines([newLine()]);
      setDraftNotes('');
      setShowProblems(false);
      setError('');
      setNotice(t('inventory.transferCreated'));
      void qc.invalidateQueries({ queryKey: ['transfers'] });
    },
    onError: (e) => {
      attemptKeys.current.settle('create', e);
      setError(getErrorMessage(e));
    },
  });

  const showWarnings = (result: unknown) => {
    const warnings = (result as { warnings?: string[] } | null)?.warnings;
    return Array.isArray(warnings) && warnings.length ? warnings.join(' ') : '';
  };

  const dispatch = useMutation({
    mutationFn: async (id: number) => {
      const queue = async () => {
        const companyId = user?.companyId;
        const userId = user?.id;
        if (!companyId || !userId) throw new Error(t('inventory.offlineNeedLogin'));
        await enqueueDraft(companyId, userId, {
          kind: 'stock_transfer',
          payload: { transferId: id },
          idempotencyKey: `stock-transfer-${id}`,
        });
        return { offline: true as const };
      };
      if (typeof navigator !== 'undefined' && !navigator.onLine) return queue();
      try {
        return await api.completeTransfer(id, { idempotencyKey: attemptKeys.current.get(`dispatch-${id}`) });
      } catch (err) {
        // R-046: CSRF/network reject must queue, not drop the transfer.
        if (isNetworkError(err)) return queue();
        throw err;
      }
    },
    onSuccess: (result, id) => {
      attemptKeys.current.settle(`dispatch-${id}`);
      setError('');
      // Queued while offline: say so, otherwise the row just stays a draft with no explanation.
      setNotice(
        result && typeof result === 'object' && 'offline' in result
          ? t('inventory.queuedOffline')
          : showWarnings(result),
      );
      void qc.invalidateQueries({ queryKey: ['transfers'] });
      void qc.invalidateQueries({ queryKey: ['transfers-outbox'] });
      void qc.invalidateQueries({ queryKey: ['stock'] });
    },
    onError: (e, id) => {
      attemptKeys.current.settle(`dispatch-${id}`, e);
      setError(getErrorMessage(e));
    },
  });

  const receive = useMutation({
    mutationFn: ({ id, receipts }: { id: number; receipts: ReturnType<typeof buildReceipts> }) =>
      api.receiveTransfer(id, { idempotencyKey: attemptKeys.current.get(`receive-${id}`), receipts }),
    onSuccess: (result, { id }) => {
      attemptKeys.current.settle(`receive-${id}`);
      setError('');
      setNotice(showWarnings(result));
      setReceiving(null);
      void qc.invalidateQueries({ queryKey: ['transfers'] });
      void qc.invalidateQueries({ queryKey: ['stock'] });
    },
    onError: (e, { id }) => {
      attemptKeys.current.settle(`receive-${id}`, e);
      setError(getErrorMessage(e));
    },
  });

  const settle = useMutation({
    mutationFn: ({ id, line, action }: { id: number; line: number; action: 'WRITE_OFF' | 'RETURN' }) =>
      api.resolveTransferShortage(id, [{ line, action }], { idempotencyKey: attemptKeys.current.get(`settle-${id}-${line}`) }),
    onSuccess: (result, { id, line }) => {
      attemptKeys.current.settle(`settle-${id}-${line}`);
      setError('');
      const held = (result as { pendingApproval?: boolean } | null)?.pendingApproval;
      setNotice(held ? t('inventory.shortagePending') : t('inventory.shortageSettled'));
      void qc.invalidateQueries({ queryKey: ['transfers'] });
      void qc.invalidateQueries({ queryKey: ['stock'] });
    },
    onError: (e, { id, line }) => {
      attemptKeys.current.settle(`settle-${id}-${line}`, e);
      setError(getErrorMessage(e));
    },
  });

  const cancel = useMutation({
    mutationFn: (id: number) => api.cancelTransfer(id),
    onSuccess: () => {
      setError('');
      void qc.invalidateQueries({ queryKey: ['transfers'] });
      void qc.invalidateQueries({ queryKey: ['stock'] });
    },
    onError: (e) => setError(getErrorMessage(e)),
  });

  const confirmCancel = async (row: Row) => {
    const from = String(row.fromWarehouse);
    const to = String(row.toWarehouse);
    const key =
      row.status === 'DRAFT'
        ? 'inventory.transferCancelDraft'
        : row.status === 'DISPATCHED'
          ? 'inventory.transferCancelDispatched'
          : 'inventory.transferCancelReceived';
    if (!(await ask([t(key, { from, to })]))) return;
    cancel.mutate(Number(row.id));
  };

  const confirmDispatch = async (row: Row) => {
    const message = t('inventory.transferConfirmDispatch', { from: String(row.fromWarehouse), to: String(row.toWarehouse) });
    if (!(await ask([message]))) return;
    dispatch.mutate(Number(row.id));
  };

  const openReceive = (row: Row) => {
    setReceived({});
    setReasons({});
    setReceiving(row);
  };

  if (query.isLoading) return <LoadingState />;
  if (query.isError) {
    return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  }

  const rows: Row[] = asRows(query.data).map((r) => {
    const summary = summarizeLines(linesOf(r));
    return {
      ...r,
      queued: queuedIds.has(Number(r.id)),
      // UXW2B-016: prefer the API's resolved name, fall back to the loaded godowns.
      fromWarehouse: r.fromWarehouseName ?? nameOf(r.fromWarehouse as string | number),
      toWarehouse: r.toWarehouseName ?? nameOf(r.toWarehouse as string | number),
      itemsSummary: summary.count ? t('inventory.transferSummary', { count: String(summary.count), qty: String(summary.qty) }) : '—',
    };
  });

  const canSettle = user?.role === 'OWNER' || user?.role === 'MANAGER';
  const inTransit = rows.filter((r) => r.status === 'DISPATCHED');
  const claims = rows.flatMap((r) =>
    openShortages(String(r.status), linesOf(r)).map((line) => ({ transfer: r, line })),
  );
  const shownRows = filterTransfers(rows, filter);
  const receivingLines = receiving ? linesOf(receiving) : [];
  const shortNotes = receivingLines
    .map((l) => {
      const typed = received[String(l.id)];
      const isShort = typed !== undefined && typed.trim() !== '' && !receivedProblem(l.quantity, typed) && toNumber(typed) < toNumber(l.quantity);
      return isShort ? `${l.productName ?? l.product}: ${toNumber(l.quantity) - toNumber(typed)}` : '';
    })
    .filter(Boolean);
  const receiveBlocked = receivingLines.some((l) => receivedProblem(l.quantity, received[String(l.id)]));

  return (
    <PageShell
      title={t('phase.stockTransfers')}
      subtitle={t('phase.stockTransfersSubtitle')}
      actions={
        <Button variant="contained" onClick={() => setOpen(true)} disabled={writesBlocked}>
          {t('phase.newTransfer')}
        </Button>
      }
    >
      {notice ? (
        <Alert severity="info" sx={{ mb: 2 }} onClose={() => setNotice('')}>
          {notice}
        </Alert>
      ) : null}
      {error && !open && !receiving ? <HelpErrorAlert message={error} sx={{ mb: 2 }} onClose={() => setError('')} /> : null}
      {inTransit.length ? (
        <Alert severity="info" icon={false} sx={{ mb: 2 }}>
          <Typography variant="subtitle2">{t('inventory.transitTitle')}</Typography>
          {inTransit.map((r) => {
            const days = transitDays(r.dispatchedAt as string | undefined);
            const late = days !== null && days >= TRANSIT_STALE_DAYS;
            return (
              <Stack key={String(r.id)} direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                <Typography variant="body2">
                  {String(r.number ?? r.id)} · {String(r.fromWarehouse)} → {String(r.toWarehouse)} · {String(r.itemsSummary)}
                </Typography>
                <Chip
                  size="small"
                  color={late ? 'warning' : 'default'}
                  label={days === null ? '—' : days === 0 ? t('inventory.transitToday') : t('inventory.transitAge', { days: String(days) })}
                />
                {late ? <Chip size="small" color="warning" variant="outlined" label={t('inventory.transitStale')} /> : null}
              </Stack>
            );
          })}
        </Alert>
      ) : null}
      {claims.length ? (
        <Alert severity="warning" icon={false} sx={{ mb: 2 }}>
          <Typography variant="subtitle2">{t('inventory.shortageTitle')}</Typography>
          {claims.map(({ transfer, line }) => (
            <Stack key={`${String(transfer.id)}-${line.id}`} direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
              <Typography variant="body2">
                {t('inventory.shortageLine', {
                  item: String(line.productName ?? line.product),
                  qty: String(toNumber(line.shortageQty)),
                  number: String(transfer.number ?? transfer.id),
                })}
              </Typography>
              {canSettle ? (
                <>
                  <Button
                    size="small"
                    disabled={writesBlocked || settle.isPending}
                    onClick={() => settle.mutate({ id: Number(transfer.id), line: Number(line.id), action: 'WRITE_OFF' })}
                  >
                    {t('inventory.shortageWriteOff')}
                  </Button>
                  <Button
                    size="small"
                    disabled={writesBlocked || settle.isPending}
                    onClick={() => settle.mutate({ id: Number(transfer.id), line: Number(line.id), action: 'RETURN' })}
                  >
                    {t('inventory.shortageReturn')}
                  </Button>
                </>
              ) : null}
            </Stack>
          ))}
        </Alert>
      ) : null}
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ mb: 2 }}>
        <TextField
          size="small"
          select
          label={t('inventory.transferFilterStatus')}
          value={filter.status}
          onChange={(e) => setFilter((cur) => ({ ...cur, status: e.target.value }))}
          sx={{ minWidth: 200 }}
        >
          <MenuItem value="">{t('inventory.transferFilterAll')}</MenuItem>
          {['DRAFT', 'DISPATCHED', 'COMPLETED', 'CANCELLED'].map((s) => (
            <MenuItem key={s} value={s}>{s}</MenuItem>
          ))}
          <MenuItem value="SHORT">{t('inventory.transferFilterShort')}</MenuItem>
        </TextField>
        <TextField
          size="small"
          label={t('inventory.transferSearch')}
          value={filter.q}
          onChange={(e) => setFilter((cur) => ({ ...cur, q: e.target.value }))}
          sx={{ flex: 1 }}
        />
      </Stack>
      <DataTable
        rows={shownRows}
        empty={t('phase.noTransfers')}
        columns={[
          { key: 'number', label: t('common.number') },
          { key: 'fromWarehouse', label: t('common.from') },
          { key: 'toWarehouse', label: t('common.to') },
          { key: 'itemsSummary', label: t('inventory.transferColItems') },
          { key: 'status', label: t('common.status'), status: true },
          { key: 'notes', label: t('phase.transferNotes') },
        ]}
        actions={(r) => (
          <Stack direction="row" spacing={1} justifyContent="flex-end" flexWrap="wrap" useFlexGap>
            <Button size="small" onClick={() => setDetail(r)}>
              {t('inventory.transferDetails')}
            </Button>
            {r.queued ? <Chip size="small" color="warning" label={t('inventory.transferQueued')} /> : null}
            {(r.queued ? [] : transferActions(String(r.status), user?.role)).map((action) =>
              action === 'dispatch' ? (
                <Button key={action} size="small" variant="contained" disabled={writesBlocked || dispatch.isPending} onClick={() => confirmDispatch(r)}>
                  {t('inventory.transferDispatch')}
                </Button>
              ) : action === 'receive' ? (
                <Button key={action} size="small" variant="contained" disabled={writesBlocked || receive.isPending} onClick={() => openReceive(r)}>
                  {t('phase.receiveTransfer')}
                </Button>
              ) : (
                <Button key={action} size="small" color="error" disabled={writesBlocked || cancel.isPending} onClick={() => confirmCancel(r)}>
                  {t('common.cancel')}
                </Button>
              ),
            )}
          </Stack>
        )}
      />

      <Dialog open={Boolean(detail)} onClose={() => setDetail(null)} fullWidth maxWidth="sm">
        <DialogTitle>{t('inventory.transferDetailsTitle', { number: String(detail?.number ?? detail?.id ?? '') })}</DialogTitle>
        <DialogContent>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('phase.product')}</TableCell>
                <TableCell>{t('inventory.transferBatch')}</TableCell>
                <TableCell align="right">{t('phase.quantity')}</TableCell>
                <TableCell align="right">{t('inventory.transferShort')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(detail ? linesOf(detail) : []).map((l, i) => (
                <TableRow key={l.id ?? i}>
                  <TableCell>{l.productName ?? l.product}</TableCell>
                  <TableCell>{l.batchNo ?? '—'}</TableCell>
                  <TableCell align="right">{toNumber(l.quantity)}</TableCell>
                  <TableCell align="right">
                    {toNumber(l.shortageQty) > 0
                      ? `${toNumber(l.shortageQty)}${l.shortageReason ? ` · ${l.shortageReason}` : ''}${
                          l.shortageResolution === 'WRITE_OFF'
                            ? ` · ${t('inventory.shortageWrittenOff')}`
                            : l.shortageResolution === 'RETURN'
                              ? ` · ${t('inventory.shortageReturned')}`
                              : ''
                        }`
                      : '—'}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDetail(null)}>{t('common.close')}</Button>
        </DialogActions>
      </Dialog>

      <Dialog open={Boolean(receiving)} onClose={() => setReceiving(null)} fullWidth maxWidth="sm">
        <DialogTitle>{t('inventory.transferReceiveTitle', { number: String(receiving?.number ?? receiving?.id ?? '') })}</DialogTitle>
        <DialogContent>
          <Stack spacing={1.5} sx={{ mt: 1 }}>
            <Typography variant="body2" color="text.secondary">
              {t('inventory.transferReceiveHelp')}
            </Typography>
            {receivingLines.map((l, i) => {
              const key = String(l.id ?? i);
              const typed = received[key];
              const bad = receivedProblem(l.quantity, typed);
              const short = typed !== undefined && typed.trim() !== '' && !bad && toNumber(typed) < toNumber(l.quantity);
              return (
                <Stack key={key} direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ sm: 'center' }}>
                  <Typography sx={{ flex: 1 }}>
                    {l.productName ?? l.product}
                    {l.batchNo ? ` · ${l.batchNo}` : ''} — {t('inventory.transferSent')} {toNumber(l.quantity)}
                  </Typography>
                  <TextField
                    size="small"
                    type="number"
                    label={t('inventory.transferReceivedQty')}
                    value={typed ?? String(toNumber(l.quantity))}
                    inputProps={{ min: 0, step: 'any' }}
                    error={bad}
                    helperText={bad ? t('inventory.transferReceivedInvalid', { qty: String(toNumber(l.quantity)) }) : undefined}
                    onChange={(e) => setReceived((cur) => ({ ...cur, [key]: e.target.value }))}
                    sx={{ width: 150 }}
                  />
                  {short ? (
                    <TextField
                      size="small"
                      label={t('inventory.transferShortReason')}
                      value={reasons[key] ?? ''}
                      onChange={(e) => setReasons((cur) => ({ ...cur, [key]: e.target.value }))}
                    />
                  ) : null}
                </Stack>
              );
            })}
            {shortNotes.length ? (
              <Alert severity="warning">
                {t('inventory.transferShortNote', { qty: shortNotes.join('; '), godown: String(receiving?.fromWarehouse ?? '') })}
              </Alert>
            ) : null}
            {error ? <HelpErrorAlert message={error} onClose={() => setError('')} /> : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setReceiving(null)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={writesBlocked || receive.isPending || receiveBlocked}
            onClick={() =>
              receiving &&
              receive.mutate({
                id: Number(receiving.id),
                receipts: buildReceipts(
                  receivingLines.map((l) => ({ id: l.id, quantity: l.quantity })),
                  received,
                  reasons,
                ),
              })
            }
          >
            {t('phase.receiveTransfer')}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={open}
        onClose={() => {
          setOpen(false);
          setError('');
        }}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>{t('phase.newStockTransfer')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {activeWarehouses.length < 2 ? (
              <Typography variant="body2">
                {t('cog.transferNeedsTwo', { name: activeWarehouses[0]?.name ?? '' })}
              </Typography>
            ) : (
              <>
                <TextField
                  select
                  label={t('phase.fromGodown')}
                  value={fromWh}
                  onChange={(e) => {
                    setFromWh(e.target.value);
                    if (toWh === e.target.value) setToWh('');
                    // A lot is only valid at the godown it was picked for.
                    setLines((cur) => cur.map((l) => ({ ...l, batch: '' })));
                  }}
                >
                  {activeWarehouses.map((w) => (
                    <MenuItem key={w.id} value={String(w.id)}>
                      {w.name}
                    </MenuItem>
                  ))}
                </TextField>
                <TextField select label={t('phase.toGodown')} value={toWh} onChange={(e) => setToWh(e.target.value)}>
                  {activeWarehouses
                    .filter((w) => String(w.id) !== fromWh)
                    .map((w) => (
                      <MenuItem key={w.id} value={String(w.id)}>
                        {w.name}
                      </MenuItem>
                    ))}
                </TextField>
              </>
            )}
            <TextField
              label={t('phase.transferNotes')}
              value={draftNotes}
              onChange={(e) => setDraftNotes(e.target.value)}
              multiline
              minRows={1}
            />
            <CustomFieldFilterBar defs={customDefs} value={cfFilters} onChange={setCfFilters} compact />
            {lines.map((line, index) => (
              <TransferLineEditor
                key={line.key}
                line={line}
                fromWh={fromWh}
                fromName={nameOf(fromWh)}
                cfFilters={cfFilters}
                canRemove={lines.length > 1}
                onChange={(next) => setLines((cur) => cur.map((l, i) => (i === index ? { ...l, ...next } : l)))}
                onRemove={() => setLines((cur) => cur.filter((_, i) => i !== index))}
              />
            ))}
            <Button onClick={() => setLines((cur) => [...cur, newLine()])} sx={{ alignSelf: 'flex-start' }}>
              {t('inventory.transferAddLine')}
            </Button>
            {showProblems && formProblem ? <Alert severity="warning">{formProblem}</Alert> : null}
            {error ? <HelpErrorAlert message={error} onClose={() => setError('')} /> : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => {
              setOpen(false);
              setError('');
            }}
          >
            {t('common.cancel')}
          </Button>
          <Button
            variant="contained"
            disabled={writesBlocked || create.isPending}
            onClick={() => {
              if (formProblem) {
                setShowProblems(true);
                return;
              }
              create.mutate();
            }}
          >
            {t('phase.createDraft')}
          </Button>
        </DialogActions>
      </Dialog>
      {dialog}
    </PageShell>
  );
}
