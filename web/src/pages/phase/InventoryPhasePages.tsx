import { useState } from 'react';
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
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import * as api from '@/api/resources';
import { ErrorState, LoadingState } from '@/components/PageState';
import { useProductSearch } from '@/hooks/useProductSearch';
import type { Product } from '@/types/domain';
import {
  asRows,
  DataTable,
  PageShell,
  type Row,
} from '@/pages/phase/phaseShared';


export function WarehousesPage() {
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
  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState message={getErrorMessage(query.error)} onRetry={() => void query.refetch()} />;
  return (
    <PageShell
      title="Warehouses"
      subtitle="Stock locations. Every company has one default warehouse."
      actions={
        <Button variant="contained" onClick={() => setOpen(true)}>
          Add warehouse
        </Button>
      }
    >
      <DataTable
        rows={asRows(query.data)}
        empty="No warehouses."
        columns={[
          { key: 'name', label: 'Name' },
          { key: 'code', label: 'Code' },
          { key: 'isDefault', label: 'Default', bool: true },
          { key: 'isActive', label: 'Active', bool: true },
        ]}
      />
      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>New warehouse</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} />
            <TextField label="Code" value={code} onChange={(e) => setCode(e.target.value)} />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
          <Tooltip title={!name.trim() ? 'Enter warehouse name to save' : ''}>
            <span>
              <Button variant="contained" disabled={!name.trim() || create.isPending} onClick={() => create.mutate()}>
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
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ['transfers'], queryFn: api.listTransfers });
  const warehouses = useQuery({ queryKey: ['warehouses'], queryFn: api.listWarehouses });
  const [open, setOpen] = useState(false);
  const [fromWh, setFromWh] = useState('');
  const [toWh, setToWh] = useState('');
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
  const productSearch = useProductSearch({ activeOnly: true, selected: selectedProduct });
  const [batch, setBatch] = useState('');
  const [serials, setSerials] = useState('');
  const [qty, setQty] = useState('1');
  const trackSerial = Boolean(selectedProduct?.trackSerial);
  const [error, setError] = useState('');
  const create = useMutation({
    mutationFn: () =>
      api.createTransfer({
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
      }),
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
  if (query.isError) return <ErrorState message={getErrorMessage(query.error)} onRetry={() => void query.refetch()} />;
  return (
    <PageShell
      title="Stock transfers"
      subtitle="Move stock between warehouses with append-only TRANSFER_OUT / TRANSFER_IN movements."
      actions={
        <Button variant="contained" onClick={() => setOpen(true)}>
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
            <Button size="small" variant="contained" onClick={() => complete.mutate(Number(r.id))}>
              Complete
            </Button>
          ) : r.status === 'COMPLETED' ? (
            <Button size="small" color="error" onClick={() => cancel.mutate(Number(r.id))}>
              Cancel
            </Button>
          ) : null
        }
      />
      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>New stock transfer</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField select label="From warehouse" value={fromWh} onChange={(e) => setFromWh(e.target.value)}>
              {(warehouses.data ?? []).map((w) => (
                <MenuItem key={w.id} value={String(w.id)}>
                  {w.name}
                </MenuItem>
              ))}
            </TextField>
            <TextField select label="To warehouse" value={toWh} onChange={(e) => setToWh(e.target.value)}>
              {(warehouses.data ?? []).map((w) => (
                <MenuItem key={w.id} value={String(w.id)}>
                  {w.name}
                </MenuItem>
              ))}
            </TextField>
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
            {error ? <Alert severity="error">{error}</Alert> : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={!fromWh || !toWh || !selectedProduct || create.isPending}
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
  const [days, setDays] = useState(30);
  const query = useQuery({ queryKey: ['expiry-alerts', days], queryFn: () => api.getExpiryAlerts(days) });
  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState message={getErrorMessage(query.error)} onRetry={() => void query.refetch()} />;
  return (
    <PageShell
      title="Expiry alerts"
      subtitle="Batch lots nearing or past expiry with remaining stock."
      actions={
        <TextField select size="small" label="Horizon" value={days} onChange={(e) => setDays(Number(e.target.value))}>
          {[30, 60, 90].map((d) => (
            <MenuItem key={d} value={d}>
              {d} days
            </MenuItem>
          ))}
        </TextField>
      }
    >
      <DataTable
        rows={asRows(query.data)}
        empty="No expiry risks in this horizon."
        columns={[
          { key: 'productName', label: 'Product' },
          { key: 'batchNo', label: 'Batch' },
          { key: 'expiryDate', label: 'Expiry' },
          { key: 'manufacturingDate', label: 'Mfg' },
        ]}
      />
    </PageShell>
  );
}

export function SerialsPage() {
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
  if (query.isError) return <ErrorState message={getErrorMessage(query.error)} onRetry={() => void query.refetch()} />;
  return (
    <PageShell
      title="Serial numbers"
      subtitle="Serial tracking for products with track_serial enabled."
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
          { key: 'warehouse', label: 'Warehouse' },
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
                <Button size="small" onClick={() => transition.mutate({ id: Number(row.id), status: target })}>
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
  if (q.isError) return <ErrorState message={getErrorMessage(q.error)} onRetry={() => void q.refetch()} />;
  const data = q.data as Row;
  const items = ((data.items as Row[]) || []).map((r) => ({
    ...r,
    productName: r.productName || r.product_name || r.name,
    unitCost: r.unitCost ?? r.unit_cost ?? r.avgCost,
    value: r.value ?? r.stockValue,
    quantity: r.quantity ?? r.qty ?? r.onHand,
  }));
  return (
    <PageShell
      title="Stock valuation"
      subtitle={`Method: ${String(data.method || 'WAVG')} — WAVG blends remaining unit cost; FIFO consumes purchase layers in creation order for COGS (Wave 16/17).`}
    >
      <DataTable
        rows={items}
        empty="No valuation rows."
        columns={[
          { key: 'productName', label: 'Product' },
          { key: 'quantity', label: 'Qty' },
          { key: 'unitCost', label: 'Unit cost', money: true },
          { key: 'value', label: 'Value', money: true },
        ]}
      />
    </PageShell>
  );
}

export function PriceListsPage() {
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
  if (query.isError) return <ErrorState message={getErrorMessage(query.error)} onRetry={() => void query.refetch()} />;
  return (
    <PageShell
      title="Price lists"
      subtitle="Named rate cards assigned to customers at billing time."
      actions={
        <Button variant="contained" onClick={() => setOpen(true)}>
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
          <Button variant="contained" disabled={!name || create.isPending} onClick={() => create.mutate()}>
            Create
          </Button>
        </DialogActions>
      </Dialog>
    </PageShell>
  );
}

