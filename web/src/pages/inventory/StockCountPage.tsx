import { useMemo, useState } from 'react';
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
import { getErrorMessage } from '@/api/client';
import * as api from '@/api/resources';
import { ErrorState, LoadingState } from '@/components/PageState';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { CustomFieldFilterBar } from '@/components/CustomFieldFilterBar';
import { useVisibleCustomFieldDefs } from '@/hooks/useActiveCustomFieldDefs';
import { useProductSearch } from '@/hooks/useProductSearch';
import type { Product } from '@/types/domain';
import { t } from '@/i18n';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { asRows, DataTable, PageShell, type Row } from '@/pages/phase/phaseShared';

export function StockCountPage() {
  const { writesBlocked } = useSubscriptionGate();
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
    mutationFn: () => api.postStockCount(Number(active?.id)),
    onSuccess: () => {
      setActive(null);
      void qc.invalidateQueries({ queryKey: ['stock-counts'] });
      void qc.invalidateQueries({ queryKey: ['stock'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
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
      title="Stock counts"
      subtitle="Physical count sessions post quantity variance as ADJUSTMENT movements. Per-godown reorder lives here too."
      actions={
        <Stack direction="row" spacing={1}>
          <Button variant="outlined" onClick={() => setReorderOpen(true)} disabled={writesBlocked}>
            Add godown reorder
          </Button>
          <Button variant="contained" onClick={() => setCreateOpen(true)} disabled={writesBlocked}>
            New count
          </Button>
        </Stack>
      }
    >
      {error ? (
        <HelpErrorAlert message={error} sx={{ mb: 2 }} onClose={() => setError('')} />
      ) : null}
      <DataTable
        rows={rows}
        empty="No stock counts yet."
        columns={[
          { key: 'id', label: '#' },
          { key: 'warehouseName', label: 'Godown' },
          { key: 'status', label: 'Status', status: true },
          { key: 'countedOn', label: 'Counted on' },
          { key: 'notes', label: 'Notes' },
        ]}
        actions={(row) => (
          <Button
            size="small"
            onClick={() => {
              setActive(row);
              setCounted({});
              setError('');
            }}
          >
            {String(row.status) === 'POSTED' ? 'View' : 'Count'}
          </Button>
        )}
      />

      <Typography variant="h6" sx={{ mt: 4, mb: 1 }}>
        Per-godown reorder
      </Typography>
      <DataTable
        rows={asRows(reorders.data)}
        empty="No per-godown reorder rules. Company-wide reorder on the item is used until you add one."
        columns={[
          { key: 'productName', label: 'Item' },
          { key: 'warehouseName', label: 'Godown' },
          { key: 'reorderLevel', label: 'Reorder qty' },
        ]}
      />

      <Dialog open={createOpen} onClose={() => setCreateOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>New stock count</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField select label="Godown" value={warehouseId} onChange={(e) => setWarehouseId(e.target.value)}>
              {(warehouses.data ?? []).map((warehouse) => (
                <MenuItem key={warehouse.id} value={String(warehouse.id)}>
                  {warehouse.name}
                </MenuItem>
              ))}
            </TextField>
            <TextField label="Notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateOpen(false)}>Cancel</Button>
          <Button variant="contained" disabled={!warehouseId || create.isPending} onClick={() => create.mutate()}>
            Start count
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={Boolean(active)} onClose={() => setActive(null)} fullWidth maxWidth="md">
        <DialogTitle>
          Count {String(active?.warehouseName || '')} ({String(active?.status || '')})
        </DialogTitle>
        <DialogContent>
          <Stack spacing={1.5} sx={{ mt: 1 }}>
            {lines.length === 0 ? <Typography color="text.secondary">No on-hand lines at this godown.</Typography> : null}
            {lines.map((line) => (
              <Stack key={String(line.id)} direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems="center">
                <Typography sx={{ flex: 1 }}>
                  {String(line.productName || line.product)} {line.batchNo ? `· ${line.batchNo}` : ''}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  System {String(line.systemQty ?? 0)}
                </Typography>
                <TextField
                  size="small"
                  label="Counted"
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
        <DialogActions>
          <Button onClick={() => setActive(null)}>Close</Button>
          <Button onClick={() => window.print()}>Print sheet</Button>
          {String(active?.status) !== 'POSTED' && String(active?.status) !== 'CANCELLED' ? (
            <>
              <Button onClick={() => saveLines.mutate()} disabled={writesBlocked || saveLines.isPending}>
                Save counts
              </Button>
              <Button color="warning" onClick={() => cancel.mutate()} disabled={writesBlocked || cancel.isPending}>
                Cancel count
              </Button>
              <Button
                variant="contained"
                onClick={() => {
                  if (!window.confirm(t('inventory.confirmPostCount'))) return;
                  post.mutate();
                }}
              disabled={writesBlocked || post.isPending || String(active?.status) !== 'COUNTED'}
              >
                Post variances
              </Button>
            </>
          ) : null}
        </DialogActions>
      </Dialog>

      <Dialog open={reorderOpen} onClose={() => setReorderOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>Per-godown reorder</DialogTitle>
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
              renderInput={(params) => <TextField {...params} label="Item" helperText={productSearch.helperText} />}
            />
            <TextField select label="Godown" value={reorderWarehouse} onChange={(e) => setReorderWarehouse(e.target.value)}>
              {(warehouses.data ?? []).map((warehouse) => (
                <MenuItem key={warehouse.id} value={String(warehouse.id)}>
                  {warehouse.name}
                </MenuItem>
              ))}
            </TextField>
            <TextField label="Reorder qty" type="number" value={reorderQty} onChange={(e) => setReorderQty(e.target.value)} />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setReorderOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={!selectedProduct || !reorderWarehouse || !reorderQty || writesBlocked || saveReorder.isPending}
            onClick={() => saveReorder.mutate()}
          >
            Save
          </Button>
        </DialogActions>
      </Dialog>
    </PageShell>
  );
}
