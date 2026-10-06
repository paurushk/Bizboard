import { useEffect, useMemo, useState } from 'react';
import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage, isNetworkError } from '@/api/client';
import { useAuth } from '@/auth/AuthContext';
import { enqueueDraft } from '@/offline/invoiceDraftCache';
import {
  resolveOfflineStockCountConflict,
  STOCK_COUNT_CONFLICT_EVENT,
  useStockOffline,
  type StockCountConflictDetail,
} from '@/pages/inventory/useStockOffline';
import { parseStockCountConflicts, type QtyConflict } from '@/pages/inventory/godownConflict';
import { StockConflictModal } from '@/pages/inventory/StockConflictModal';
import * as api from '@/api/resources';
import { ErrorState, LoadingState } from '@/components/PageState';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { CustomFieldFilterBar } from '@/components/CustomFieldFilterBar';
import { useVisibleCustomFieldDefs } from '@/hooks/useActiveCustomFieldDefs';
import { useProductSearch } from '@/hooks/useProductSearch';
import type { Product } from '@/types/domain';
import { t, useLocale } from '@/i18n';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { asRows, DataTable, PageShell, type Row } from '@/pages/phase/phaseShared';

export function StockCountPage() {
  useLocale();
  const { writesBlocked } = useSubscriptionGate();
  const { user } = useAuth();
  useStockOffline(user?.companyId ?? 0, user?.id ?? 0);
  const qc = useQueryClient();
  const warehouses = useQuery({ queryKey: ['warehouses'], queryFn: api.listWarehouses });
  const counts = useQuery({ queryKey: ['stock-counts'], queryFn: api.listStockCounts });
  const reorders = useQuery({ queryKey: ['reorder-levels'], queryFn: api.listReorderLevels });
  const [createOpen, setCreateOpen] = useState(false);
  const [warehouseId, setWarehouseId] = useState('');
  const [notes, setNotes] = useState('');
  const [active, setActive] = useState<Row | null>(null);
  const [counted, setCounted] = useState<Record<string, string>>({});
  const [reorderOpen, setReorderOpen] = useState(false);
  const [reorderWarehouse, setReorderWarehouse] = useState('');
  const [reorderQty, setReorderQty] = useState('');
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
  const [cfFilters, setCfFilters] = useState<Record<string, string[]>>({});
  const customDefs = useVisibleCustomFieldDefs();
  const productSearch = useProductSearch({ activeOnly: true, selected: selectedProduct, cf: cfFilters });
  const [error, setError] = useState('');
  const [conflicts, setConflicts] = useState<QtyConflict[]>([]);
  const [offlineConflict, setOfflineConflict] = useState<StockCountConflictDetail | null>(null);
  const [lastSynced, setLastSynced] = useState<string | null>(null);
  const [pendingCount, setPendingCount] = useState(0);

  // CR-143: offline flush 409 → open the same conflict modal as online post.
  useEffect(() => {
    const onConflict = (event: Event) => {
      const detail = (event as CustomEvent<StockCountConflictDetail>).detail;
      if (!detail?.conflicts?.length) return;
      setOfflineConflict(detail);
      setConflicts(detail.conflicts);
    };
    window.addEventListener(STOCK_COUNT_CONFLICT_EVENT, onConflict);
    return () => window.removeEventListener(STOCK_COUNT_CONFLICT_EVENT, onConflict);
  }, []);

  const create = useMutation({
    mutationFn: () => api.createStockCount({ warehouse: Number(warehouseId), notes }),
    onSuccess: (created) => {
      setCreateOpen(false);
      setNotes('');
      setActive(created as Row);
      setCounted({});
      void qc.invalidateQueries({ queryKey: ['stock-counts'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const saveLines = useMutation({
    mutationFn: async () => {
      if (!active?.id) return;
      const lines = ((active.lines as Row[]) || []).map((line) => ({
        id: line.id,
        countedQty: counted[String(line.id)] === undefined ? line.countedQty : counted[String(line.id)],
      }));
      return api.updateStockCount(Number(active.id), { lines });
    },
    onSuccess: (updated) => {
      if (updated) setActive(updated as Row);
      void qc.invalidateQueries({ queryKey: ['stock-counts'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const post = useMutation({
    mutationFn: async (resolve?: 'KEEP_SERVER' | 'KEEP_LOCAL') => {
      const id = Number(active?.id);
      const key = `stock-count-${id}`;
      const queue = async () => {
        const companyId = user?.companyId;
        const userId = user?.id;
        if (!companyId || !userId) throw new Error(t('inventory.offlineNeedLogin'));
        await enqueueDraft(companyId, userId, {
          kind: 'stock_count',
          payload: { sessionId: id, lines: counted, resolveConflicts: resolve ?? '' },
          idempotencyKey: key,
        });
        return { offline: true as const };
      };
      if (typeof navigator !== 'undefined' && !navigator.onLine) {
        return queue();
      }
      try {
        return await api.postStockCount(
          id,
          resolve ? { resolveConflicts: resolve } : {},
          { idempotencyKey: key },
        );
      } catch (err) {
        // R-046: CSRF/network reject must queue, not drop the count.
        if (isNetworkError(err)) return queue();
        throw err;
      }
    },
    onSuccess: (result) => {
      setConflicts([]);
      if (result && typeof result === 'object' && 'offline' in result) {
        setPendingCount((n) => n + 1);
        setError('');
        setActive(null);
        return;
      }
      setLastSynced(new Date().toISOString());
      setActive(null);
      void qc.invalidateQueries({ queryKey: ['stock-counts'] });
      void qc.invalidateQueries({ queryKey: ['stock'] });
    },
    onError: (err) => {
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
      setActive(null);
      void qc.invalidateQueries({ queryKey: ['stock-counts'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const saveReorder = useMutation({
    mutationFn: () =>
      api.createReorderLevel({
        warehouse: Number(reorderWarehouse),
        product: Number(selectedProduct?.id),
        reorderLevel: reorderQty,
      }),
    onSuccess: () => {
      setReorderOpen(false);
      setReorderQty('');
      setSelectedProduct(null);
      void qc.invalidateQueries({ queryKey: ['reorder-levels'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const rows = asRows(counts.data);
  const lines = useMemo(() => ((active?.lines as Row[]) || []) as Row[], [active]);

  if (counts.isLoading) return <LoadingState />;
  if (counts.isError) {
    return <ErrorState message={getErrorMessage(counts.error)} error={counts.error} onRetry={() => void counts.refetch()} />;
  }

  return (
    <PageShell
      title={t('inventory.stockCounts')}
      subtitle={t('inventory.stockCountsSubtitle')}
      actions={
        <Stack direction="row" spacing={1}>
          <Button variant="outlined" onClick={() => setReorderOpen(true)} disabled={writesBlocked}>
            {t('sweep2.addGodownReorder')}
          </Button>
          <Button variant="contained" onClick={() => setCreateOpen(true)} disabled={writesBlocked}>
            {t('sweep2.newCount')}
          </Button>
        </Stack>
      }
    >
      {error ? (
        <HelpErrorAlert message={error} sx={{ mb: 2 }} onClose={() => setError('')} />
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
        open={conflicts.length > 0}
        conflicts={conflicts}
        onCancel={() => {
          setConflicts([]);
          setOfflineConflict(null);
        }}
        onKeepServer={() => {
          if (offlineConflict) {
            void resolveOfflineStockCountConflict({
              sessionId: offlineConflict.sessionId,
              resolve: 'KEEP_SERVER',
              idempotencyKey: offlineConflict.idempotencyKey,
              companyId: offlineConflict.companyId,
              userId: offlineConflict.userId,
            })
              .then(() => {
                setConflicts([]);
                setOfflineConflict(null);
                setPendingCount((n) => Math.max(0, n - 1));
                void qc.invalidateQueries({ queryKey: ['stock-counts'] });
                void qc.invalidateQueries({ queryKey: ['stock'] });
              })
              .catch((err) => setError(getErrorMessage(err)));
            return;
          }
          post.mutate('KEEP_SERVER');
        }}
        onKeepLocal={() => {
          if (offlineConflict) {
            void resolveOfflineStockCountConflict({
              sessionId: offlineConflict.sessionId,
              resolve: 'KEEP_LOCAL',
              idempotencyKey: offlineConflict.idempotencyKey,
              companyId: offlineConflict.companyId,
              userId: offlineConflict.userId,
            })
              .then(() => {
                setConflicts([]);
                setOfflineConflict(null);
                setPendingCount((n) => Math.max(0, n - 1));
                void qc.invalidateQueries({ queryKey: ['stock-counts'] });
                void qc.invalidateQueries({ queryKey: ['stock'] });
              })
              .catch((err) => setError(getErrorMessage(err)));
            return;
          }
          post.mutate('KEEP_LOCAL');
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
        ]}
        actions={(row) => (
          <Button
            size="small"
            onClick={async () => {
              setError('');
              setCounted({});
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

      <Typography variant="h6" sx={{ mt: 4, mb: 1 }}>
        {t('sweep2.perGodownReorder')}
      </Typography>
      <DataTable
        rows={asRows(reorders.data)}
        empty={t('items.noReorderRules')}
        // F3-016: can grow to product-count × godown-count rows for a large
        // catalog — window the DOM rows.
        virtualized
        columns={[
          { key: 'productName', label: t('items.item') },
          { key: 'warehouseName', label: t('items.godown') },
          { key: 'reorderLevel', label: t('items.reorderQty') },
        ]}
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
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateOpen(false)}>{t('common.cancel')}</Button>
          <Button variant="contained" disabled={!warehouseId || create.isPending} onClick={() => create.mutate()}>
            {t('items.startCount')}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={Boolean(active)} onClose={() => setActive(null)} fullWidth maxWidth="md">
        <DialogTitle>
          {t('items.countTitle', { name: String(active?.warehouseName || ''), status: String(active?.status || '') })}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={1.5} sx={{ mt: 1 }}>
            {lines.length === 0 ? <Typography color="text.secondary">{t('items.noOnHand')}</Typography> : null}
            {/* F3-016: deliberately NOT virtualized — "Print sheet" below
                relies on every line being in the DOM (a windowed list would
                only print the currently-visible rows), which matters more
                here than render cost for what's normally a bounded per-
                godown SKU count. */}
            {lines.map((line) => (
              <Stack key={String(line.id)} direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems="center">
                <Typography sx={{ flex: 1 }}>
                  {String(line.productName || line.product)} {line.batchNo ? `· ${line.batchNo}` : ''}
                </Typography>
                {String(active?.status) === 'POSTED' ? (
                  <Typography variant="body2" color="text.secondary">
                    System {String(line.systemQty ?? 0)}
                  </Typography>
                ) : null}
                <TextField
                  size="small"
                  label={t('items.counted')}
                  type="number"
                  value={counted[String(line.id)] ?? String(line.countedQty ?? '')}
                  onChange={(e) => setCounted((current) => ({ ...current, [String(line.id)]: e.target.value }))}
                  disabled={String(active?.status) === 'POSTED' || String(active?.status) === 'CANCELLED'}
                  sx={{ width: 140 }}
                />
              </Stack>
            ))}
          </Stack>
        </DialogContent>
        <DialogActions className="no-print">
          <Button onClick={() => setActive(null)}>{t('common.close')}</Button>
          <Button onClick={() => window.print()}>{t('items.printSheet')}</Button>
          {String(active?.status) !== 'POSTED' && String(active?.status) !== 'CANCELLED' ? (
            <>
              <Button onClick={() => saveLines.mutate()} disabled={writesBlocked || saveLines.isPending}>
                {t('items.saveCounts')}
              </Button>
              <Button color="warning" onClick={() => cancel.mutate()} disabled={writesBlocked || cancel.isPending}>
                {t('items.cancelCount')}
              </Button>
              <Button
                variant="contained"
                onClick={() => {
                  if (!window.confirm(t('inventory.confirmPostCount'))) return;
                  post.mutate(undefined);
                }}
              disabled={writesBlocked || post.isPending || String(active?.status) !== 'COUNTED'}
              >
                {t('items.postVariances')}
              </Button>
            </>
          ) : null}
        </DialogActions>
      </Dialog>

      <Dialog open={reorderOpen} onClose={() => setReorderOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>{t('items.perGodownReorder')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <CustomFieldFilterBar defs={customDefs} value={cfFilters} onChange={setCfFilters} compact />
            <Autocomplete
              options={productSearch.options}
              value={selectedProduct}
              onChange={(_, value) => setSelectedProduct(value)}
              getOptionLabel={(option) => option.name}
              inputValue={productSearch.productQuery}
              onInputChange={(_, value) => productSearch.setProductQuery(value)}
              renderInput={(params) => <TextField {...params} label={t('items.item')} helperText={productSearch.helperText} />}
            />
            <TextField select label={t('items.godown')} value={reorderWarehouse} onChange={(e) => setReorderWarehouse(e.target.value)}>
              {(warehouses.data ?? []).map((warehouse) => (
                <MenuItem key={warehouse.id} value={String(warehouse.id)}>
                  {warehouse.name}
                </MenuItem>
              ))}
            </TextField>
            <TextField label={t('items.reorderQty')} type="number" value={reorderQty} onChange={(e) => setReorderQty(e.target.value)} />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setReorderOpen(false)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={!selectedProduct || !reorderWarehouse || !reorderQty || writesBlocked || saveReorder.isPending}
            onClick={() => saveReorder.mutate()}
          >
            {t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>
    </PageShell>
  );
}
