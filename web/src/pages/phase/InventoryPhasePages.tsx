import { useState } from 'react';
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
import TextField from '@mui/material/TextField';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import * as api from '@/api/resources';
import { HelpEmptyLink } from '@/pages/help/HelpEmptyLink';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { PreventionNote } from '@/pages/help/PreventionNote';
import { ErrorState, LoadingState } from '@/components/PageState';
import { CustomFieldFilterBar } from '@/components/CustomFieldFilterBar';
import { useVisibleCustomFieldDefs } from '@/hooks/useActiveCustomFieldDefs';
import { useProductSearch } from '@/hooks/useProductSearch';
import type { Product } from '@/types/domain';
import { t } from '@/i18n';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import {
  asRows,
  DataTable,
  PageShell,
  type Row,
} from '@/pages/phase/phaseShared';


export function WarehousesPage() {
  const { writesBlocked } = useSubscriptionGate();
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ['warehouses'], queryFn: api.listWarehouses });
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [code, setCode] = useState('');
  const create = useMutation({
    mutationFn: () => api.createWarehouse({ name, code: code || name.slice(0, 8).toUpperCase() }),
    onSuccess: () => {
      setOpen(false);
      setName('');
      setCode('');
      void qc.invalidateQueries({ queryKey: ['warehouses'] });
    },
  });
  const deactivate = useMutation({
    mutationFn: (id: number) => api.updateWarehouse(id, { isActive: false }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['warehouses'] }),
  });
  const remove = useMutation({
    mutationFn: (id: number) => api.deleteWarehouse(id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['warehouses'] }),
  });
  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  return (
    <PageShell
      title={t('phase.godowns')}
      subtitle={t('phase.godownsSubtitle')}
      actions={
        <Button variant="contained" onClick={() => setOpen(true)} disabled={writesBlocked}>
          Add godown
        </Button>
      }
    >
      {(create.error || deactivate.error || remove.error) ? (
        <HelpErrorAlert error={create.error || deactivate.error || remove.error} />
      ) : null}
      <PreventionNote intent="edit-completed-invoice" slot="delete-with-history" />
      <DataTable
        rows={asRows(query.data)}
        empty="No godowns."
        emptyAction={<HelpEmptyLink intent="stock-in-another-godown" />}
        columns={[
          { key: 'name', label: 'Name' },
          { key: 'code', label: 'Code' },
          { key: 'isDefault', label: 'Default', bool: true },
          { key: 'isActive', label: 'Active', bool: true },
        ]}
        actions={(row) => (
          <Stack direction="row" spacing={1} justifyContent="flex-end">
            {row.isActive && !row.isDefault ? (
              <Button size="small" onClick={() => deactivate.mutate(Number(row.id))} disabled={writesBlocked || deactivate.isPending}>
                Deactivate
              </Button>
            ) : null}
            {!row.isDefault ? (
              <Button size="small" color="error" onClick={() => {
                if (!window.confirm(t('phase.confirmDeleteGodown'))) return;
                remove.mutate(Number(row.id));
              }} disabled={writesBlocked || remove.isPending}>
                Delete
              </Button>
            ) : null}
          </Stack>
        )}
      />
      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>New godown</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} />
            <TextField label="Code" value={code} onChange={(e) => setCode(e.target.value)} />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
          <Tooltip title={!name.trim() ? 'Enter godown name to save' : ''}>
            <span>
              <Button variant="contained" disabled={writesBlocked || !name.trim() || create.isPending} onClick={() => create.mutate()}>
                Save
              </Button>
            </span>
          </Tooltip>
        </DialogActions>
      </Dialog>
    </PageShell>
  );
}

export function StockTransferPage() {
  const { writesBlocked } = useSubscriptionGate();
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ['transfers'], queryFn: api.listTransfers });
  const warehouses = useQuery({ queryKey: ['warehouses'], queryFn: api.listWarehouses });
  const [open, setOpen] = useState(false);
  const [fromWh, setFromWh] = useState('');
  const [toWh, setToWh] = useState('');
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
  const [cfFilters, setCfFilters] = useState<Record<string, string[]>>({});
  const customDefs = useVisibleCustomFieldDefs();
  const productSearch = useProductSearch({ activeOnly: true, selected: selectedProduct, cf: cfFilters });
  const [batch, setBatch] = useState('');
  const [serials, setSerials] = useState('');
  const [qty, setQty] = useState('1');
  const trackSerial = Boolean(selectedProduct?.trackSerial);
  const [error, setError] = useState('');
  const create = useMutation({
    mutationFn: () => {
      if (!fromWh || !toWh || fromWh === toWh) {
        throw new Error('Choose a different destination godown');
      }
      return api.createTransfer({
        fromWarehouse: Number(fromWh),
        toWarehouse: Number(toWh),
        lines: [{
          product: Number(selectedProduct?.id),
          batch: batch ? Number(batch) : null,
          quantity: qty,
          ...(trackSerial && serials.trim()
            ? { serialNumbers: serials.split(/[,\n]+/).map((s) => s.trim()).filter(Boolean) }
            : {}),
        }],
      });
    },
    onSuccess: () => {
      setOpen(false);
      setSelectedProduct(null);
      productSearch.setProductQuery('');
      void qc.invalidateQueries({ queryKey: ['transfers'] });
    },
    onError: (e) => setError(getErrorMessage(e)),
  });
  const complete = useMutation({
    mutationFn: (id: number) => api.completeTransfer(id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['transfers'] }),
  });
  const cancel = useMutation({
    mutationFn: (id: number) => api.cancelTransfer(id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['transfers'] }),
    onError: (e) => setError(getErrorMessage(e)),
  });
  const batches = useQuery({
    queryKey: ['batches', selectedProduct?.id],
    queryFn: () => api.listBatches(Number(selectedProduct?.id)),
    enabled: Boolean(selectedProduct?.id),
  });
  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  return (
    <PageShell
      title={t('phase.stockTransfers')}
      subtitle={t('phase.stockTransfersSubtitle')}
      actions={
        <Button variant="contained" onClick={() => setOpen(true)} disabled={writesBlocked}>
          New transfer
        </Button>
      }
    >
      <DataTable
        rows={asRows(query.data).map((r) => ({
          ...r,
          // UXW2B-016: prefer the API's resolved name, fall back to a client-side
          // lookup against the warehouses already loaded for the dialog above, so
          // this still resolves correctly even against an older cached response.
          fromWarehouse:
            r.fromWarehouseName ??
            (warehouses.data ?? []).find((w) => w.id === Number(r.fromWarehouse))?.name ??
            r.fromWarehouse,
          toWarehouse:
            r.toWarehouseName ??
            (warehouses.data ?? []).find((w) => w.id === Number(r.toWarehouse))?.name ??
            r.toWarehouse,
        }))}
        empty="No transfers yet."
        columns={[
          { key: 'number', label: 'Number' },
          { key: 'fromWarehouse', label: 'From' },
          { key: 'toWarehouse', label: 'To' },
          { key: 'status', label: 'Status', status: true },
          { key: 'notes', label: 'Notes' },
        ]}
        actions={(r) =>
          r.status === 'DRAFT' ? (
            <Button size="small" variant="contained" disabled={writesBlocked} onClick={() => complete.mutate(Number(r.id))}>
              Complete
            </Button>
          ) : r.status === 'COMPLETED' ? (
            <Button size="small" color="error" disabled={writesBlocked} onClick={() => cancel.mutate(Number(r.id))}>
              Cancel
            </Button>
          ) : null
        }
      />
      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>New stock transfer</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              select
              label="From godown"
              value={fromWh}
              onChange={(e) => {
                setFromWh(e.target.value);
                if (toWh === e.target.value) setToWh('');
              }}
            >
              {(warehouses.data ?? []).map((w) => (
                <MenuItem key={w.id} value={String(w.id)}>
                  {w.name}
                </MenuItem>
              ))}
            </TextField>
            <TextField select label="To godown" value={toWh} onChange={(e) => setToWh(e.target.value)}>
              {(warehouses.data ?? [])
                .filter((w) => String(w.id) !== fromWh)
                .map((w) => (
                <MenuItem key={w.id} value={String(w.id)}>
                  {w.name}
                </MenuItem>
              ))}
            </TextField>
            <CustomFieldFilterBar defs={customDefs} value={cfFilters} onChange={setCfFilters} compact />
            <Autocomplete<Product>
              options={productSearch.options}
              loading={productSearch.isFetching}
              filterOptions={(opts) => opts}
              inputValue={productSearch.productQuery}
              onInputChange={(_, v, reason) => {
                if (reason === 'input' || reason === 'clear') productSearch.setProductQuery(v);
              }}
              getOptionLabel={(o) => `${o.name} · ${o.sku}`}
              value={selectedProduct}
              onChange={(_, v) => {
                setSelectedProduct(v);
                setBatch('');
              }}
              renderInput={(params) => (
                <TextField
                  {...params}
                  label="Product"
                  helperText={productSearch.helperText}
                />
              )}
            />
            <TextField select label="Batch (optional)" value={batch} onChange={(e) => setBatch(e.target.value)}>
              <MenuItem value="">No batch</MenuItem>
              {(batches.data ?? []).map((lot) => (
                <MenuItem key={String(lot.id)} value={String(lot.id)}>
                  {lot.batchNo}
                </MenuItem>
              ))}
            </TextField>
            <TextField label="Quantity" type="number" value={qty} onChange={(e) => setQty(e.target.value)} />
            {trackSerial ? (
              <TextField
                label="Serial numbers (optional)"
                multiline
                minRows={2}
                value={serials}
                onChange={(e) => setSerials(e.target.value)}
                helperText="Comma or newline separated; count must match quantity"
              />
            ) : null}
            {error ? <HelpErrorAlert message={error} /> : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={writesBlocked || !fromWh || !toWh || fromWh === toWh || !selectedProduct || create.isPending}
            onClick={() => create.mutate()}
          >
            Create draft
          </Button>
        </DialogActions>
      </Dialog>
    </PageShell>
  );
}

export function ExpiryAlertsPage() {
  const { writesBlocked } = useSubscriptionGate();
  const qc = useQueryClient();
  const [days, setDays] = useState(30);
  const [warehouseId, setWarehouseId] = useState('');
  const warehouses = useQuery({ queryKey: ['warehouses'], queryFn: api.listWarehouses });
  const query = useQuery({
    queryKey: ['expiry-alerts', days, warehouseId],
    queryFn: () => api.getExpiryAlerts(days, warehouseId ? Number(warehouseId) : undefined),
  });
  const writeOff = useMutation({
    mutationFn: (row: Row) =>
      api.writeOffExpiry({
        product: Number(row.product),
        warehouse: Number(row.warehouse) || undefined,
        batch: Number(row.batch || row.id),
        quantity: Number(row.onHand || row.quantity || 0),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['expiry-alerts'] });
      void qc.invalidateQueries({ queryKey: ['stock'] });
    },
  });
  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  return (
    <PageShell
      title={t('phase.expiryAlerts')}
      subtitle={t('phase.expiryAlertsSubtitle')}
      actions={
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          {[7, 30, 60, 90].map((d) => (
            <Chip
              key={d}
              label={`${d} days`}
              color={days === d ? 'primary' : 'default'}
              onClick={() => setDays(d)}
              variant={days === d ? 'filled' : 'outlined'}
            />
          ))}
          <TextField
            select
            size="small"
            label="Godown"
            value={warehouseId}
            onChange={(e) => setWarehouseId(e.target.value)}
            sx={{ minWidth: 180 }}
          >
            <MenuItem value="">All godowns</MenuItem>
            {(warehouses.data ?? []).map((warehouse) => (
              <MenuItem key={warehouse.id} value={String(warehouse.id)}>
                {warehouse.name}
              </MenuItem>
            ))}
          </TextField>
        </Stack>
      }
    >
      {writeOff.error ? <HelpErrorAlert error={writeOff.error} /> : null}
      <DataTable
        rows={asRows(query.data)}
        empty="No expiry risks in this horizon."
        columns={[
          { key: 'productName', label: 'Product' },
          { key: 'batchNo', label: 'Batch' },
          { key: 'warehouseName', label: 'Godown' },
          { key: 'expiryDate', label: 'Expiry' },
          { key: 'onHand', label: 'Remaining' },
          { key: 'daysToExpiry', label: 'Days' },
        ]}
        actions={(row) => (
          <Button
            size="small"
            color="warning"
            disabled={writesBlocked || writeOff.isPending || Number(row.onHand || 0) <= 0}
            onClick={() => {
              if (!window.confirm(t('inventory.confirmWriteoff'))) return;
              writeOff.mutate(row);
            }}
          >
            Write off
          </Button>
        )}
      />
    </PageShell>
  );
}

export function SerialsPage() {
  const { writesBlocked } = useSubscriptionGate();
  const qc = useQueryClient();
  const [statusFilter, setStatusFilter] = useState('');
  const query = useQuery({
    queryKey: ['serials', statusFilter],
    queryFn: () => api.listSerials(statusFilter ? { status: statusFilter } : undefined),
  });
  const transition = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) => api.transitionSerial(id, { status }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['serials'] }),
  });
  // UXW2B-017: show the resolved names the API now joins instead of raw FK ids.
  const rows = asRows(query.data).map((r) => ({
    ...r,
    product: r.productName ?? r.product,
    warehouse: r.warehouseName ?? r.warehouse ?? '—',
  }));
  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  return (
    <PageShell
      title={t('phase.serials')}
      subtitle={t('phase.serialsSubtitle')}
      actions={
        <TextField
          select
          size="small"
          label="Status"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          sx={{ minWidth: 160 }}
        >
          <MenuItem value="">All</MenuItem>
          {['AVAILABLE', 'SOLD', 'RETURNED', 'SCRAPPED'].map((s) => (
            <MenuItem key={s} value={s}>
              {s}
            </MenuItem>
          ))}
        </TextField>
      }
    >
      <DataTable
        rows={rows}
        empty="No serials recorded."
        columns={[
          { key: 'serialNumber', label: 'Serial' },
          { key: 'product', label: 'Product' },
          { key: 'warehouse', label: 'Godown' },
          { key: 'status', label: 'Status', status: true },
        ]}
        actions={(row) => {
          const status = String(row.status);
          const target = status === 'AVAILABLE' ? 'SOLD' : status === 'SOLD' ? 'RETURNED' : status === 'RETURNED' ? 'SCRAPPED' : null;
          return (
            <Stack direction="row" spacing={1} alignItems="center">
              <Typography variant="caption" color="text.secondary" title="Current status">
                Last: {status}
              </Typography>
              {target ? (
                <Button size="small" disabled={writesBlocked} onClick={() => transition.mutate({ id: Number(row.id), status: target })}>
                  Mark {target.toLowerCase()}
                </Button>
              ) : null}
            </Stack>
          );
        }}
      />
    </PageShell>
  );
}

export function StockValuationPage() {
  const q = useQuery({ queryKey: ['stock-valuation'], queryFn: () => api.getStockValuation() });
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState message={getErrorMessage(q.error)} error={q.error} onRetry={() => void q.refetch()} />;
  const data = q.data as Row;
  const items = ((data.items as Row[]) || []).map((r) => ({
    ...r,
    productName: r.productName || r.product_name || r.name,
    warehouseName: r.warehouseName || r.warehouse_name,
    unitCost: r.unitCost ?? r.unit_cost ?? r.avgCost,
    value: r.value ?? r.stockValue,
    quantity: r.quantity ?? r.qty ?? r.onHand,
  }));
  return (
    <PageShell
      title={t('phase.stockValuation')}
      subtitle={`Method: ${String(data.method || 'WAVG')} — WAVG blends remaining unit cost; FIFO consumes purchase layers in creation order for COGS (Wave 16/17).`}
    >
      <DataTable
        rows={items}
        empty="No valuation rows."
        columns={[
          { key: 'productName', label: 'Product' },
          { key: 'warehouseName', label: 'Godown' },
          { key: 'quantity', label: 'Qty' },
          { key: 'unitCost', label: 'Unit cost', money: true },
          { key: 'value', label: 'Value', money: true },
        ]}
      />
    </PageShell>
  );
}

export function PriceListsPage() {
  const { writesBlocked } = useSubscriptionGate();
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ['price-lists'], queryFn: api.listPriceLists });
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const create = useMutation({
    mutationFn: () => api.createPriceList({ name }),
    onSuccess: () => {
      setOpen(false);
      setName('');
      void qc.invalidateQueries({ queryKey: ['price-lists'] });
    },
  });
  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  return (
    <PageShell
      title={t('phase.priceLists')}
      subtitle={t('phase.priceListsSubtitle')}
      actions={
        <Button variant="contained" onClick={() => setOpen(true)} disabled={writesBlocked}>
          New list
        </Button>
      }
    >
      <Alert severity="info" sx={{ mb: 2 }}>
        Rates are interpreted using the invoice price mode (exclusive or inclusive) at billing
        time. Price lists store a unit rate only — they do not have a separate tax-inclusive flag.
      </Alert>
      <DataTable
        rows={asRows(query.data)}
        empty="No price lists."
        columns={[
          { key: 'name', label: 'Name' },
          { key: 'isActive', label: 'Active', bool: true },
        ]}
      />
      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>New price list</DialogTitle>
        <DialogContent>
          <TextField fullWidth sx={{ mt: 1 }} label="Name" value={name} onChange={(e) => setName(e.target.value)} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button variant="contained" disabled={writesBlocked || !name || create.isPending} onClick={() => create.mutate()}>
            Create
          </Button>
        </DialogActions>
      </Dialog>
    </PageShell>
  );
}

