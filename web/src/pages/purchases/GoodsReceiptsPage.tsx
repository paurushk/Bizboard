import { useMemo, useState } from 'react';
import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
import IconButton from '@mui/material/IconButton';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink, useNavigate } from 'react-router-dom';
import { getErrorMessage, userGestureIdempotencyKey } from '@/api/client';
import { listPurchaseOrders, listSuppliersPage, listWarehouses, searchProducts } from '@/api/resources';
import {
  cancelGoodsReceipt,
  completeGoodsReceipt,
  convertGoodsReceipt,
  createGoodsReceipt,
  deleteGoodsReceipt,
  listGoodsReceiptsPage,
  type GoodsReceipt,
  type GoodsReceiptLine,
} from '@/api/legacy/purchases';
import { useAuth } from '@/auth/AuthContext';
import { todayIso } from '@/components/billing/lineHelpers';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { EmptyState } from '@/components/PageState';
import { StatusChip } from '@/components/StatusChip';
import { PageTitle } from '@/contextHelp';
import { t } from '@/i18n';
import { invalidatePurchaseSideEffects } from '@/pages/purchases/purchaseQueries';
import type { PurchaseOrder, Supplier } from '@/types/domain';
import { canCancelDocuments, canCreatePurchases } from '@/utils/permissions';
import { documentStatusTone, statusLabelKey } from '@/utils/status';

const PAGE_SIZE = 50;

interface DraftLine {
  product: string;
  quantityReceived: string;
  quantityAccepted: string;
  quantityRejected: string;
  unitPrice: string;
  rejectionReason: string;
}

function emptyLine(): DraftLine {
  return {
    product: '',
    quantityReceived: '1',
    quantityAccepted: '1',
    quantityRejected: '0',
    unitPrice: '',
    rejectionReason: '',
  };
}

type Pending = { kind: 'complete' | 'cancel' | 'delete'; row: GoodsReceipt };

function receiptLabel(row: Pick<GoodsReceipt, 'id' | 'number'>): string {
  return row.number?.trim() ? row.number : `#${row.id}`;
}

function acceptedUnits(row: GoodsReceipt): number {
  return (row.items ?? []).reduce((sum, line) => sum + (Number(line.quantityAccepted) || 0), 0);
}

export function GoodsReceiptsPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const canWrite = canCreatePurchases(user);
  const canCancel = canCancelDocuments(user);
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [supplier, setSupplier] = useState<Supplier | null>(null);
  const [supplierQuery, setSupplierQuery] = useState('');
  const [orderId, setOrderId] = useState('');
  const [warehouseId, setWarehouseId] = useState('');
  const [chosenNames, setChosenNames] = useState<Record<string, string>>({});
  const [receiptDate, setReceiptDate] = useState(() => todayIso());
  const [challan, setChallan] = useState('');
  const [lines, setLines] = useState<DraftLine[]>([emptyLine()]);
  const [productQuery, setProductQuery] = useState('');
  const [pending, setPending] = useState<Pending | null>(null);

  const receipts = useQuery({
    queryKey: ['goods-receipts', page],
    queryFn: () => listGoodsReceiptsPage({ page, pageSize: PAGE_SIZE }),
  });
  const suppliers = useQuery({
    queryKey: ['suppliers-grn', supplierQuery],
    queryFn: () => listSuppliersPage({ q: supplierQuery.trim() || undefined, pageSize: 20 }),
    enabled: canWrite,
  });
  const warehouses = useQuery({ queryKey: ['warehouses'], queryFn: listWarehouses, enabled: canWrite });
  // Open orders of the chosen supplier: a receipt can be recorded against one of them.
  const orders = useQuery({
    queryKey: ['purchase-orders', 'for-grn', supplier?.id],
    queryFn: () => listPurchaseOrders({ supplier: String(supplier?.id) }),
    enabled: canWrite && Boolean(supplier),
  });
  const openOrders = useMemo(
    () => (orders.data ?? []).filter((o) => o.status !== 'CANCELLED' && o.status !== 'CONVERTED'),
    [orders.data],
  );
  const products = useQuery({
    queryKey: ['products-grn', productQuery],
    queryFn: () => searchProducts(productQuery.trim()),
    enabled: canWrite && productQuery.trim().length > 0,
  });

  const create = useMutation({
    mutationFn: () => {
      // Check what the form can check before posting stock: whole numbers, accepted plus rejected
      // equals received, and a price (a blank price would receive stock at zero cost).
      for (const [i, line] of lines.entries()) {
        const received = Number(line.quantityReceived || 0);
        const accepted = Number(line.quantityAccepted || 0);
        const rejected = Number(line.quantityRejected || 0);
        if (![received, accepted, rejected].every((n) => Number.isFinite(n) && n >= 0)) {
          throw new Error(t('grn.badQuantity', { line: String(i + 1) }));
        }
        if (Math.abs(accepted + rejected - received) > 0.0005) {
          throw new Error(t('grn.quantityMismatch', { line: String(i + 1) }));
        }
        if (!line.unitPrice || Number(line.unitPrice) <= 0) {
          throw new Error(t('grn.priceRequired', { line: String(i + 1) }));
        }
      }
      const items: GoodsReceiptLine[] = lines.map((line) => ({
        product: Number(line.product),
        quantityReceived: line.quantityReceived || '0',
        quantityAccepted: line.quantityAccepted || '0',
        quantityRejected: line.quantityRejected || '0',
        unitPrice: line.unitPrice || '0',
        rejectionReason: line.rejectionReason,
      }));
      return createGoodsReceipt(
        {
          supplier: Number(supplier?.id),
          purchaseOrder: orderId ? Number(orderId) : null,
          warehouse: warehouseId ? Number(warehouseId) : null,
          receiptDate,
          supplierChallanNumber: challan,
          items,
        },
        { idempotencyKey: userGestureIdempotencyKey() },
      );
    },
    onSuccess: () => {
      setError(null);
      setLines([emptyLine()]);
      setChallan('');
      setOrderId('');
      void qc.invalidateQueries({ queryKey: ['goods-receipts'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const complete = useMutation({
    mutationFn: (row: GoodsReceipt) =>
      completeGoodsReceipt(row.id, { idempotencyKey: userGestureIdempotencyKey() }),
    onSuccess: (row) => {
      setError(null);
      setPending(null);
      setMessage(t('grn.completed', { label: receiptLabel(row) }));
      void qc.invalidateQueries({ queryKey: ['goods-receipts'] });
      void qc.invalidateQueries({ queryKey: ['purchase-orders'] });
      // Completing a receipt posts stock, so every stock view is stale now.
      invalidatePurchaseSideEffects(qc, { stock: true });
    },
    onError: (err) => {
      setPending(null);
      setError(getErrorMessage(err));
    },
  });

  const cancel = useMutation({
    mutationFn: (row: GoodsReceipt) => cancelGoodsReceipt(row.id),
    onSuccess: (row) => {
      setError(null);
      setPending(null);
      setMessage(t('grn.cancelled', { label: receiptLabel(row) }));
      void qc.invalidateQueries({ queryKey: ['goods-receipts'] });
    },
    onError: (err) => {
      setPending(null);
      setError(getErrorMessage(err));
    },
  });

  const remove = useMutation({
    mutationFn: (row: GoodsReceipt) => deleteGoodsReceipt(row.id),
    onSuccess: () => {
      setError(null);
      setPending(null);
      setMessage(t('grn.deleted'));
      void qc.invalidateQueries({ queryKey: ['goods-receipts'] });
    },
    onError: (err) => {
      setPending(null);
      setError(getErrorMessage(err));
    },
  });

  const toBill = useMutation({
    mutationFn: (row: GoodsReceipt) => convertGoodsReceipt(row.id),
    onSuccess: (invoice, row) => {
      setError(null);
      void qc.invalidateQueries({ queryKey: ['goods-receipts'] });
      invalidatePurchaseSideEffects(qc, { invoiceId: invoice.id });
      navigate(`/purchases/history/${invoice.id}`, {
        state: { message: t('grn.billCreated', { label: receiptLabel(row) }) },
      });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const busy = complete.isPending || cancel.isPending || remove.isPending || toBill.isPending;

  function patchLine(index: number, patch: Partial<DraftLine>) {
    setLines((current) => current.map((line, i) => (i === index ? { ...line, ...patch } : line)));
  }

  function pickOrder(order: PurchaseOrder | null) {
    setOrderId(order ? String(order.id) : '');
    if (!order) return;
    // Pre-fill what was ordered; the receiver then corrects the quantities that really arrived.
    const filled: DraftLine[] = (order.items ?? []).map((item) => {
      const qty = String(Number(item.quantity) || 0);
      return {
        product: String(item.product),
        quantityReceived: qty,
        quantityAccepted: qty,
        quantityRejected: '0',
        unitPrice: String(Number(item.unitPrice) || ''),
        rejectionReason: '',
      };
    });
    if (filled.length > 0) {
      setChosenNames((names) => ({
        ...names,
        ...Object.fromEntries(
          (order.items ?? []).map((item) => [String(item.product), item.productName ?? String(item.product)]),
        ),
      }));
      setLines(filled);
      setMessage(t('grn.fillFromOrder'));
    }
  }

  function confirmPending() {
    if (!pending) return;
    if (pending.kind === 'complete') complete.mutate(pending.row);
    else if (pending.kind === 'cancel') cancel.mutate(pending.row);
    else remove.mutate(pending.row);
  }

  const pendingLabel = pending ? receiptLabel(pending.row) : '';
  const pendingTitle =
    pending?.kind === 'complete'
      ? t('grn.confirmCompleteTitle')
      : pending?.kind === 'cancel'
        ? t('grn.cancelAction')
        : t('grn.deleteAction');
  const pendingBody = !pending
    ? ''
    : pending.kind === 'complete'
      ? t('grn.confirmCompleteBody', {
          units: String(acceptedUnits(pending.row)),
          lines: String((pending.row.items ?? []).length),
        })
      : pending.kind === 'cancel'
        ? t('grn.confirmCancel', { label: pendingLabel })
        : t('grn.confirmDelete', { label: pendingLabel });

  const rows = receipts.data?.results ?? [];

  return (
    <Stack spacing={2}>
      <PageTitle page="goods-receipts">{t('nav.goodsReceipts')}</PageTitle>
      {message ? (
        <Alert severity="success" onClose={() => setMessage(null)}>
          {message}
        </Alert>
      ) : null}
      {error ? <Alert severity="error">{error}</Alert> : null}
      {receipts.isError ? <Alert severity="error">{getErrorMessage(receipts.error)}</Alert> : null}

      {canWrite ? (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack spacing={1.5}>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} useFlexGap flexWrap="wrap">
              <Autocomplete
                size="small"
                sx={{ minWidth: 240 }}
                options={suppliers.data?.results ?? []}
                value={supplier}
                loading={suppliers.isFetching}
                getOptionLabel={(option) => option.name}
                isOptionEqualToValue={(a, b) => a.id === b.id}
                filterOptions={(options) => options}
                onInputChange={(_, value, reason) => {
                  if (reason === 'input') setSupplierQuery(value);
                }}
                onChange={(_, value) => {
                  setSupplier(value);
                  setOrderId('');
                }}
                renderInput={(params) => (
                  <TextField {...params} label={t('grn.supplier')} placeholder={t('grn.supplierSearch')} />
                )}
              />
              <TextField
                select
                size="small"
                sx={{ minWidth: 220 }}
                label={t('grn.against')}
                value={orderId}
                disabled={!supplier}
                onChange={(e) => pickOrder(openOrders.find((o) => String(o.id) === e.target.value) ?? null)}
              >
                <MenuItem value="">{t('grn.noOrder')}</MenuItem>
                {openOrders.map((order) => (
                  <MenuItem key={order.id} value={String(order.id)}>
                    {order.number || `#${order.id}`} · {order.orderDate}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                select
                size="small"
                sx={{ minWidth: 180 }}
                label={t('grn.warehouse')}
                value={warehouseId}
                onChange={(e) => setWarehouseId(e.target.value)}
              >
                <MenuItem value="">{t('common.none')}</MenuItem>
                {(warehouses.data ?? []).map((w) => (
                  <MenuItem key={w.id} value={String(w.id)}>
                    {w.name}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                size="small"
                type="date"
                label={t('common.date')}
                value={receiptDate}
                onChange={(e) => setReceiptDate(e.target.value)}
                InputLabelProps={{ shrink: true }}
              />
              <TextField
                size="small"
                label={t('common.number')}
                value={challan}
                onChange={(e) => setChallan(e.target.value)}
              />
            </Stack>
            <TextField
              size="small"
              label={t('common.product')}
              value={productQuery}
              onChange={(e) => setProductQuery(e.target.value)}
              helperText={t('billing.grnGuidance')}
            />
            {lines.map((line, index) => (
              <Stack key={index} direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ sm: 'center' }}>
                <TextField
                  select
                  size="small"
                  label={t('common.product')}
                  value={line.product}
                  onChange={(e) => {
                    const picked = (products.data ?? []).find((product) => String(product.id) === e.target.value);
                    if (picked) setChosenNames((names) => ({ ...names, [String(picked.id)]: picked.name }));
                    patchLine(index, { product: e.target.value });
                  }}
                  sx={{ minWidth: 180 }}
                >
                  <MenuItem value="">{t('common.none')}</MenuItem>
                  {/* Products already chosen on any line stay in the list when a new search replaces the results. */}
                  {[
                    ...(products.data ?? []).map((product) => ({ id: String(product.id), name: product.name })),
                    ...Object.entries(chosenNames)
                      .filter(([id]) => !(products.data ?? []).some((product) => String(product.id) === id))
                      .map(([id, name]) => ({ id, name })),
                  ].map((option) => (
                    <MenuItem key={option.id} value={option.id}>{option.name}</MenuItem>
                  ))}
                </TextField>
                <TextField size="small" label={t('common.qty')} value={line.quantityReceived} onChange={(e) => patchLine(index, { quantityReceived: e.target.value })} />
                <TextField size="small" label={t('billing.qtyAccepted')} value={line.quantityAccepted} onChange={(e) => patchLine(index, { quantityAccepted: e.target.value })} />
                <TextField size="small" label={t('billing.qtyRejected')} value={line.quantityRejected} onChange={(e) => patchLine(index, { quantityRejected: e.target.value })} />
                <TextField size="small" label={t('billing.unitPrice')} value={line.unitPrice} onChange={(e) => patchLine(index, { unitPrice: e.target.value })} />
                <TextField size="small" label={t('common.notes')} value={line.rejectionReason} onChange={(e) => patchLine(index, { rejectionReason: e.target.value })} />
                <IconButton
                  aria-label={t('grn.removeLine')}
                  disabled={lines.length === 1}
                  onClick={() => setLines((current) => current.filter((_, i) => i !== index))}
                >
                  <DeleteOutlineIcon fontSize="small" />
                </IconButton>
              </Stack>
            ))}
            <Stack direction="row" spacing={1}>
              <Button onClick={() => setLines((current) => [...current, emptyLine()])}>{t('common.add')}</Button>
              <Button
                variant="contained"
                disabled={!supplier || lines.some((line) => !line.product) || create.isPending}
                onClick={() => create.mutate()}
              >
                {t('grn.createReceipt')}
              </Button>
            </Stack>
          </Stack>
        </Paper>
      ) : null}

      <Stack spacing={1}>
        {rows.map((row) => (
          <Paper key={row.id} variant="outlined" sx={{ p: 1.5 }}>
            <Stack
              direction={{ xs: 'column', sm: 'row' }}
              spacing={1}
              alignItems={{ sm: 'center' }}
              useFlexGap
              flexWrap="wrap"
            >
              <strong>{receiptLabel(row)}</strong>
              <span>{row.supplierName}</span>
              <span>{row.receiptDate}</span>
              <StatusChip tone={documentStatusTone(row.status)} labelKey={statusLabelKey(row.status)} />
              {row.convertedPurchase ? (
                <Button size="small" component={RouterLink} to={`/purchases/history/${row.convertedPurchase}`}>
                  {t('poActions.viewBill')}
                </Button>
              ) : null}
              <Stack direction="row" spacing={1} sx={{ ml: { sm: 'auto' } }}>
                {canWrite && row.status === 'DRAFT' ? (
                  <Button
                    size="small"
                    variant="contained"
                    onClick={() => setPending({ kind: 'complete', row })}
                    disabled={busy}
                  >
                    {t('common.complete')}
                  </Button>
                ) : null}
                {canWrite && row.status === 'COMPLETED' && !row.convertedPurchase ? (
                  <Button size="small" variant="outlined" onClick={() => toBill.mutate(row)} disabled={busy}>
                    {t('grn.createBill')}
                  </Button>
                ) : null}
                {canCancel && row.status === 'DRAFT' ? (
                  <Button
                    size="small"
                    color="warning"
                    onClick={() => setPending({ kind: 'cancel', row })}
                    disabled={busy}
                  >
                    {t('grn.cancelAction')}
                  </Button>
                ) : null}
                {canWrite && row.status === 'DRAFT' ? (
                  <Button
                    size="small"
                    color="error"
                    onClick={() => setPending({ kind: 'delete', row })}
                    disabled={busy}
                  >
                    {t('grn.deleteAction')}
                  </Button>
                ) : null}
              </Stack>
            </Stack>
          </Paper>
        ))}
        {!receipts.isLoading && !receipts.isError && rows.length === 0 ? (
          <EmptyState title={t('grn.empty')} description={t('grn.emptyHint')} />
        ) : null}
      </Stack>
      {receipts.data && (receipts.data.next || page > 1) ? (
        <Stack direction="row" spacing={1} alignItems="center">
          <Button disabled={page <= 1} onClick={() => setPage((n) => n - 1)}>{t('common.previous')}</Button>
          <Typography variant="body2" color="text.secondary">
            {t('common.page')} {page}
          </Typography>
          <Button disabled={!receipts.data?.next} onClick={() => setPage((n) => n + 1)}>{t('common.next')}</Button>
        </Stack>
      ) : null}

      <ConfirmDialog
        open={pending !== null}
        title={pendingTitle}
        body={pendingBody}
        confirmLabel={pending?.kind === 'complete' ? t('common.complete') : pendingTitle}
        confirmColor={pending?.kind === 'complete' ? 'primary' : pending?.kind === 'cancel' ? 'warning' : 'error'}
        confirming={busy}
        onConfirm={confirmPending}
        onClose={() => setPending(null)}
      />
    </Stack>
  );
}
