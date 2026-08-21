import { useMemo, useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import Menu from '@mui/material/Menu';
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
import FormControlLabel from '@mui/material/FormControlLabel';
import CloudUploadOutlinedIcon from '@mui/icons-material/CloudUploadOutlined';
import TableViewOutlinedIcon from '@mui/icons-material/TableViewOutlined';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink, useNavigate } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { createOpeningStock, createProduct, listProductsPage, listStock, listWarehouses, updateProduct } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { StatusChip } from '@/components/StatusChip';
import { t } from '@/i18n';
import type { Product } from '@/types/domain';
import { isValidHsnSac, normalizeGstRate } from '@/utils/gst';
import { formatMoney, toNumber } from '@/utils/money';
import { canImport, isViewer } from '@/utils/permissions';
import { productStatusTone, statusLabelKey } from '@/utils/status';
import { isSetupWizardEnabled } from '@/config/features';

const PAGE_SIZE = 50;

const STANDARD_UNITS = [
  'PCS',
  'BOX',
  'KG',
  'MTR',
  'LTR',
  'NOS',
  'PKT',
  'SET',
  'PAIR',
  'DOZ',
  'GMS',
  'ROLL',
  'BAG',
];

const GST_RATES = [
  { value: '0', label: '0% (Exempt / Nil)' },
  { value: '0.25', label: '0.25% (Precious Stones)' },
  { value: '3', label: '3% (Gold / Silver)' },
  { value: '5', label: '5%' },
  { value: '12', label: '12%' },
  { value: '18', label: '18% (Standard Goods & Services)' },
  { value: '28', label: '28% (Luxury & Demerit)' },
];

const emptyForm: {
  name: string;
  sku: string;
  unitName: string;
  barcode: string;
  hsnCode: string;
  gstRate: string;
  purchasePrice: string;
  sellingPrice: string;
  openingStock: string;
  warehouseId: string;
  reorderLevel: string;
  trackBatch: boolean;
  trackSerial: boolean;
  status: 'ACTIVE' | 'INACTIVE';
} = {
  name: '',
  sku: '',
  unitName: 'PCS',
  barcode: '',
  hsnCode: '',
  gstRate: '18',
  purchasePrice: '0',
  sellingPrice: '0',
  openingStock: '0',
  warehouseId: '',
  reorderLevel: '0',
  trackBatch: false,
  trackSerial: false,
  status: 'ACTIVE',
};

export function ProductsPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const query = useQuery({
    queryKey: ['products', page, search],
    queryFn: () => listProductsPage({ page, pageSize: PAGE_SIZE, q: search || undefined }),
  });
  const stockQuery = useQuery({ queryKey: ['stock'], queryFn: listStock });
  const warehouses = useQuery({ queryKey: ['warehouses'], queryFn: listWarehouses });

  const stockMap = useMemo(() => {
    const map = new Map<number, number>();
    for (const s of stockQuery.data ?? []) {
      const current = map.get(s.product) ?? 0;
      map.set(s.product, current + toNumber(s.available));
    }
    return map;
  }, [stockQuery.data]);

  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Product | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState<string | null>(null);
  const [saveOk, setSaveOk] = useState(false);
  const [bulkAnchor, setBulkAnchor] = useState<null | HTMLElement>(null);
  const rows = query.data?.results ?? [];
  const canMutate = !!user && !isViewer(user.role);
  const canContinueSetup =
    isSetupWizardEnabled() &&
    user?.role === 'OWNER' &&
    !user.company?.onboarding?.activationDone;

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (form.hsnCode && !isValidHsnSac(form.hsnCode)) {
        throw new Error('HSN/SAC must be 4, 6, or 8 digits');
      }
      const generatedSku = form.sku.trim() || `ITEM-${Date.now().toString(36).toUpperCase()}`;
      const payload = {
        name: form.name.trim(),
        sku: generatedSku,
        unitName: form.unitName,
        barcode: form.barcode.trim() || undefined,
        hsnCode: form.hsnCode.trim() || undefined,
        gstRate: normalizeGstRate(Number(form.gstRate) || 0),
        purchasePrice: Number(form.purchasePrice),
        sellingPrice: Number(form.sellingPrice),
        reorderLevel: Number(form.reorderLevel),
        trackBatch: form.trackBatch,
        trackSerial: form.trackSerial,
        status: form.status,
      };
      if (editing) {
        return updateProduct(editing.id, payload);
      }
      const created = await createProduct(payload);
      const openingQty = Number(form.openingStock);
      if (openingQty > 0 && created?.id) {
        const whId = Number(form.warehouseId) || warehouses.data?.[0]?.id;
        const purchaseCost = Number(form.purchasePrice) > 0 ? Number(form.purchasePrice) : undefined;
        try {
          await createOpeningStock({
            product: created.id,
            quantity: openingQty,
            unit_cost: purchaseCost,
            warehouse: whId || undefined,
          });
        } catch (stockErr) {
          void qc.invalidateQueries({ queryKey: ['products'] });
          void qc.invalidateQueries({ queryKey: ['products-count'] });
          void qc.invalidateQueries({ queryKey: ['stock'] });
          throw new Error(`Product created, but opening stock could not be recorded: ${getErrorMessage(stockErr)}`);
        }
      }
      return created;
    },
    onSuccess: () => {
      setOpen(false);
      setEditing(null);
      setForm(emptyForm);
      setError(null);
      setSaveOk(true);
      void qc.invalidateQueries({ queryKey: ['products'] });
      void qc.invalidateQueries({ queryKey: ['products-count'] });
      void qc.invalidateQueries({ queryKey: ['stock'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1}>
        <Typography variant="h4">{t('nav.products')}</Typography>
        <TextField
          size="small"
          placeholder={`${t('common.search')} name or SKU`}
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
          sx={{ minWidth: 220, flex: 1, maxWidth: 360 }}
        />
        <Stack direction="row" spacing={1}>
          {canImport(user) ? (
            <>
              <Button variant="outlined" onClick={(e) => setBulkAnchor(e.currentTarget)}>
                {t('products.bulkActions')}
              </Button>
              <Menu
                anchorEl={bulkAnchor}
                open={Boolean(bulkAnchor)}
                onClose={() => setBulkAnchor(null)}
                anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
                transformOrigin={{ vertical: 'top', horizontal: 'right' }}
              >
                <MenuItem
                  onClick={() => {
                    setBulkAnchor(null);
                    void navigate('/settings/import?kind=PRODUCTS');
                  }}
                >
                  <ListItemIcon>
                    <TableViewOutlinedIcon fontSize="small" />
                  </ListItemIcon>
                  <ListItemText
                    primary={t('products.bulkAddItems')}
                    secondary={t('products.bulkAddItemsHint')}
                  />
                </MenuItem>
                <MenuItem
                  onClick={() => {
                    setBulkAnchor(null);
                    void navigate('/purchases/bill-upload');
                  }}
                >
                  <ListItemIcon>
                    <CloudUploadOutlinedIcon fontSize="small" />
                  </ListItemIcon>
                  <ListItemText
                    primary={t('products.purchaseBillUpload')}
                    secondary={t('products.purchaseBillUploadHint')}
                  />
                </MenuItem>
              </Menu>
            </>
          ) : null}
          {canMutate ? (
            <Button
              variant="contained"
              onClick={() => {
                setEditing(null);
                setForm(emptyForm);
                setOpen(true);
              }}
            >
              {t('common.add')}
            </Button>
          ) : null}
        </Stack>
      </Stack>
      {error ? <Alert severity="error">{error}</Alert> : null}
      {saveOk ? (
        <Alert severity="success" onClose={() => setSaveOk(false)}>
          Product saved.
        </Alert>
      ) : null}
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} onRetry={() => void query.refetch()} />
      ) : null}
      {rows.length === 0 && !query.isLoading && !query.isError ? (
        <EmptyState
          description={t('empty.products')}
          action={
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
              {canContinueSetup ? (
                <Button component={RouterLink} to="/setup?step=catalog" variant="contained">
                  {t('setup.continueSetup')}
                </Button>
              ) : null}
              {canMutate ? (
                <Button
                  variant={canContinueSetup ? 'outlined' : 'contained'}
                  onClick={() => {
                    setEditing(null);
                    setForm(emptyForm);
                    setOpen(true);
                  }}
                >
                  {t('common.add')} {t('nav.products')}
                </Button>
              ) : null}
            </Stack>
          }
        />
      ) : null}
      {rows.length > 0 ? (
        <Paper sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('common.name')}</TableCell>
                <TableCell>{t('common.sku')}</TableCell>
                <TableCell>{t('products.unit')}</TableCell>
                <TableCell align="right">{t('products.sellingPrice')}</TableCell>
                <TableCell align="right">GST %</TableCell>
                <TableCell align="right">{t('billing.stockAvailable')}</TableCell>
                <TableCell>Tracking</TableCell>
                <TableCell>{t('common.status')}</TableCell>
                <TableCell />
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((p) => {
                const stockQty = stockMap.get(p.id);
                return (
                <TableRow key={p.id}>
                  <TableCell>{p.name}</TableCell>
                  <TableCell>{p.sku}</TableCell>
                  <TableCell>{p.unitName || 'PCS'}</TableCell>
                  <TableCell align="right">{formatMoney(p.sellingPrice)}</TableCell>
                  <TableCell align="right">{toNumber(p.gstRate)}%</TableCell>
                  <TableCell align="right">
                    {stockQty == null ? (
                      '—'
                    ) : (
                      <Chip
                        size="small"
                        label={`${stockQty} ${p.unitName || 'PCS'}`}
                        color={stockQty <= 0 ? 'error' : stockQty <= toNumber(p.reorderLevel) ? 'warning' : 'success'}
                        variant="outlined"
                        sx={{ fontWeight: 600 }}
                      />
                    )}
                  </TableCell>
                  <TableCell>
                    {p.trackBatch ? <Chip size="small" label="Batch" sx={{ mr: 0.5 }} /> : null}
                    {p.trackSerial ? <Chip size="small" label="Serial" /> : null}
                    {!p.trackBatch && !p.trackSerial ? '—' : null}
                  </TableCell>
                  <TableCell>
                    <StatusChip
                      tone={productStatusTone(p.status)}
                      labelKey={statusLabelKey(p.status)}
                    />
                  </TableCell>
                  <TableCell align="right">
                    {canMutate ? (
                      <Button
                        size="small"
                        onClick={() => {
                          setEditing(p);
                          setForm({
                            name: p.name,
                            sku: p.sku,
                            unitName: p.unitName || 'PCS',
                            barcode: p.barcode ?? '',
                            hsnCode: p.hsnCode ?? '',
                            gstRate: String(p.gstRate),
                            purchasePrice: String(p.purchasePrice),
                            sellingPrice: String(p.sellingPrice),
                            openingStock: '0',
                            warehouseId: '',
                            reorderLevel: String(p.reorderLevel),
                            trackBatch: Boolean(p.trackBatch),
                            trackSerial: Boolean(p.trackSerial),
                            status: p.status === 'INACTIVE' ? 'INACTIVE' : 'ACTIVE',
                          });
                          setOpen(true);
                        }}
                      >
                        {t('common.edit')}
                      </Button>
                    ) : null}
                  </TableCell>
                </TableRow>
              );})}
            </TableBody>
          </Table>
        </Paper>
      ) : null}
      {query.data && (query.data.next || page > 1) ? (
        <Stack direction="row" spacing={1} justifyContent="flex-end" alignItems="center">
          <Typography variant="body2" color="text.secondary">
            {t('common.page')} {page}
            {query.data.count ? ` / ${Math.max(1, Math.ceil(query.data.count / PAGE_SIZE))}` : ''}
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

      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editing ? t('common.edit') : t('common.create')} {t('nav.products')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label={t('common.name')}
              required
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              helperText={
                !editing &&
                form.name.trim() &&
                rows.some(
                  (p) => p.name.trim().toLowerCase() === form.name.trim().toLowerCase(),
                )
                  ? 'A product with this name already exists — check SKU carefully when billing'
                  : undefined
              }
              error={
                !editing &&
                Boolean(form.name.trim()) &&
                rows.some(
                  (p) => p.name.trim().toLowerCase() === form.name.trim().toLowerCase(),
                )
              }
            />
            <Stack direction="row" spacing={2}>
              <TextField
                select
                label={t('products.unit')}
                value={form.unitName}
                onChange={(e) => setForm((f) => ({ ...f, unitName: e.target.value }))}
                sx={{ minWidth: 140 }}
              >
                {STANDARD_UNITS.map((u) => (
                  <MenuItem key={u} value={u}>
                    {u}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                select
                label="GST Rate"
                value={form.gstRate}
                onChange={(e) => setForm((f) => ({ ...f, gstRate: e.target.value }))}
                sx={{ flex: 1 }}
              >
                {GST_RATES.map((r) => (
                  <MenuItem key={r.value} value={r.value}>
                    {r.label}
                  </MenuItem>
                ))}
              </TextField>
            </Stack>
            <Stack direction="row" spacing={2}>
              <TextField
                label={t('products.sellingPrice')}
                helperText={t('products.sellingPriceHint')}
                type="number"
                inputProps={{ min: 0 }}
                value={form.sellingPrice}
                onChange={(e) => {
                  const v = e.target.value;
                  if (!v.startsWith('-')) setForm((f) => ({ ...f, sellingPrice: v }));
                }}
                error={Number(form.sellingPrice) < 0}
                sx={{ flex: 1 }}
              />
              <TextField
                label={t('products.purchasePrice')}
                helperText={t('products.purchasePriceHint')}
                type="number"
                inputProps={{ min: 0 }}
                value={form.purchasePrice}
                onChange={(e) => {
                  const v = e.target.value;
                  if (!v.startsWith('-')) setForm((f) => ({ ...f, purchasePrice: v }));
                }}
                error={Number(form.purchasePrice) < 0}
                sx={{ flex: 1 }}
              />
            </Stack>
            {editing ? (
              <Stack spacing={1} sx={{ p: 1.5, bgcolor: 'action.hover', borderRadius: 1 }}>
                <Typography variant="caption" color="text.secondary">
                  {t('billing.openingStockLocked')}
                </Typography>
                <Button
                  size="small"
                  variant="outlined"
                  component={RouterLink}
                  to={`/inventory/adjustments?product=${editing.id}`}
                  sx={{ alignSelf: 'flex-start' }}
                >
                  {t('billing.adjustStockLink')}
                </Button>
              </Stack>
            ) : (
              <Stack spacing={1.5}>
                <TextField
                  label={t('products.openingStock')}
                  helperText={t('products.openingStockHint')}
                  type="number"
                  inputProps={{ min: 0 }}
                  value={form.openingStock}
                  onChange={(e) => {
                    const v = e.target.value;
                    if (!v.startsWith('-')) setForm((f) => ({ ...f, openingStock: v }));
                  }}
                />
                <TextField
                  select
                  label={t('nav.warehouses')}
                  value={form.warehouseId || String(warehouses.data?.[0]?.id ?? '')}
                  onChange={(e) => setForm((f) => ({ ...f, warehouseId: e.target.value }))}
                  helperText="Warehouse for opening stock"
                >
                  {(warehouses.data ?? []).map((w) => (
                    <MenuItem key={w.id} value={String(w.id)}>
                      {w.name}
                    </MenuItem>
                  ))}
                </TextField>
              </Stack>
            )}
            <TextField
              label={t('products.skuOptional')}
              helperText={t('products.skuOptionalHint')}
              value={form.sku}
              onChange={(e) => setForm((f) => ({ ...f, sku: e.target.value }))}
            />
            <TextField
              label={t('common.barcode')}
              value={form.barcode}
              onChange={(e) => setForm((f) => ({ ...f, barcode: e.target.value }))}
            />
            <TextField
              label="HSN / SAC Code"
              value={form.hsnCode}
              onChange={(e) => setForm((f) => ({ ...f, hsnCode: e.target.value }))}
              error={Boolean(form.hsnCode) && !isValidHsnSac(form.hsnCode)}
              helperText={
                Boolean(form.hsnCode) && !isValidHsnSac(form.hsnCode)
                  ? 'HSN/SAC must be 4, 6, or 8 digits'
                  : undefined
              }
            />
            <TextField
              label={t('products.reorderLevel')}
              helperText={t('products.reorderLevelHint')}
              type="number"
              inputProps={{ min: 0 }}
              value={form.reorderLevel}
              onChange={(e) => {
                const v = e.target.value;
                if (!v.startsWith('-')) setForm((f) => ({ ...f, reorderLevel: v }));
              }}
              error={Number(form.reorderLevel) < 0}
            />
            <TextField
              select
              label={t('common.status')}
              value={form.status}
              onChange={(e) =>
                setForm((f) => ({ ...f, status: e.target.value as 'ACTIVE' | 'INACTIVE' }))
              }
            >
              <MenuItem value="ACTIVE">ACTIVE</MenuItem>
              <MenuItem value="INACTIVE">INACTIVE</MenuItem>
            </TextField>
            <Stack direction="row">
              <FormControlLabel
                control={<Checkbox checked={form.trackBatch} onChange={(e) => setForm((f) => ({ ...f, trackBatch: e.target.checked }))} />}
                label={t('products.trackBatch')}
              />
              <FormControlLabel
                control={<Checkbox checked={form.trackSerial} onChange={(e) => setForm((f) => ({ ...f, trackSerial: e.target.checked }))} />}
                label={t('products.trackSerial')}
              />
            </Stack>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>{t('common.cancel')}</Button>
          <Tooltip
            title={
              !form.name.trim()
                ? 'Enter product name to save'
                : Boolean(form.hsnCode) && !isValidHsnSac(form.hsnCode)
                  ? 'Enter a valid HSN/SAC code (2-8 digits)'
                  : Number(form.purchasePrice) < 0 || Number(form.sellingPrice) < 0
                    ? 'Prices cannot be negative'
                    : Number(form.reorderLevel) < 0
                      ? 'Reorder level cannot be negative'
                      : ''
            }
          >
            <span>
              <Button
                variant="contained"
                disabled={
                  !form.name.trim() ||
                  (Boolean(form.hsnCode) && !isValidHsnSac(form.hsnCode)) ||
                  Number(form.purchasePrice) < 0 ||
                  Number(form.sellingPrice) < 0 ||
                  Number(form.reorderLevel) < 0 ||
                  saveMutation.isPending
                }
                onClick={() => saveMutation.mutate()}
              >
                {t('common.save')}
              </Button>
            </span>
          </Tooltip>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
