import { useMemo, useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
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
import Typography from '@mui/material/Typography';
import CloudUploadOutlinedIcon from '@mui/icons-material/CloudUploadOutlined';
import DownloadOutlinedIcon from '@mui/icons-material/DownloadOutlined';
import TableViewOutlinedIcon from '@mui/icons-material/TableViewOutlined';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink, useNavigate } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { csvCell } from '@/utils/csv';
import { deleteProduct, listProducts, listProductsPage, listStock } from '@/api/resources';
import { VirtualizedTable } from '@/components/VirtualizedTable';
import { ItemFormDialog } from '@/pages/inventory/ItemFormDialog';
import { useAuth } from '@/auth/AuthContext';
import { ColumnPicker } from '@/components/ColumnPicker';
import { CustomFieldFilterBar } from '@/components/CustomFieldFilterBar';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { StatusChip } from '@/components/StatusChip';
import { useVisibleCustomFieldDefs } from '@/hooks/useActiveCustomFieldDefs';
import { useCfFilters } from '@/hooks/useCfFilters';
import { useColumnPrefs, type ColumnSpec } from '@/hooks/useColumnPrefs';
import { PageTitle } from '@/contextHelp';
import { t, useLocale } from '@/i18n';
import type { Product } from '@/types/domain';
import { formatMoney, toNumber } from '@/utils/money';
import { ForbiddenPage } from '@/pages/ForbiddenPage';
import { canAdjustInventory, canImport, canViewInventorySurfaces } from '@/utils/permissions';
import { productStatusTone, statusLabelKey } from '@/utils/status';
import { isItemCustomFieldsV2Enabled, isSetupWizardEnabled } from '@/config/features';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { customFieldCell } from '@/pages/inventory/itemCustomFieldDefaults';

const PAGE_SIZE = 50;

function standardColumns(): ColumnSpec[] {
  return [
    { id: 'name', label: t('common.name'), group: 'standard', removable: false },
    { id: 'sku', label: t('common.sku'), group: 'standard' },
    { id: 'unit', label: t('products.unit'), group: 'standard' },
    { id: 'price', label: t('products.sellingPrice'), group: 'standard' },
    { id: 'gst', label: t('products.gstPercent'), group: 'standard' },
    { id: 'stock', label: t('products.stock'), group: 'standard' },
    { id: 'tracking', label: t('products.tracking'), group: 'standard' },
    { id: 'status', label: t('products.status'), group: 'standard' },
  ];
}

export function ProductsPage() {
  const locale = useLocale();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { user } = useAuth();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [showDense, setShowDense] = useState(false);
  const [categoryFilter, setCategoryFilter] = useState('');
  const [brandFilter, setBrandFilter] = useState('');
  const [stockFilter, setStockFilter] = useState('');
  const [taxFilter, setTaxFilter] = useState('');
  const debouncedSearch = useDebouncedValue(search, 300);
  const customDefs = useVisibleCustomFieldDefs();
  const { value: cfFilters, onChange: setCfFilters } = useCfFilters();
  const columns = useMemo<ColumnSpec[]>(
    () => [
      ...standardColumns(),
      ...customDefs.map((def) => ({ id: `cf:${def.key}`, label: def.label, group: 'custom' as const })),
    ],
    [customDefs, locale],
  );
  const prefs = useColumnPrefs('items', columns, user?.companyId, user?.id);
  const query = useQuery({
    queryKey: ['products', page, debouncedSearch, cfFilters],
    queryFn: () =>
      listProductsPage({
        page,
        pageSize: PAGE_SIZE,
        q: debouncedSearch || undefined,
        cf: isItemCustomFieldsV2Enabled() ? cfFilters : undefined,
      }),
  });
  // The filters below work on whole products and stock, but the list is paged. While a filter is
  // chosen (or its menu was opened, to list every category, brand and slab) the whole catalogue is
  // loaded and filtered, so a filter means "every item that matches", not "matches on this page".
  const [filtersTouched, setFiltersTouched] = useState(false);
  const filtersActive = Boolean(categoryFilter || brandFilter || stockFilter || taxFilter);
  const allQuery = useQuery({
    queryKey: ['products-all', debouncedSearch, cfFilters],
    queryFn: () => listProducts({ q: debouncedSearch || undefined, cf: isItemCustomFieldsV2Enabled() ? cfFilters : undefined }),
    enabled: filtersActive || filtersTouched,
  });
  const sourceRows = filtersActive && allQuery.data ? allQuery.data : (query.data?.results ?? []);
  const pageIds = sourceRows.map((row) => row.id);
  const stockQuery = useQuery({
    queryKey: ['stock', pageIds],
    queryFn: () => listStock({ productIds: pageIds }),
    enabled: pageIds.length > 0,
  });

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
  const [saveOk, setSaveOk] = useState<string | false>(false);
  const [notice, setNotice] = useState<{ severity: 'success' | 'info' | 'error'; message: string } | null>(null);
  const [exporting, setExporting] = useState(false);
  const [bulkAnchor, setBulkAnchor] = useState<null | HTMLElement>(null);
  const removeProduct = useMutation({
    mutationFn: (id: number) => deleteProduct(id),
    onSuccess: (result) => {
      void qc.invalidateQueries({ queryKey: ['products'] });
      void qc.invalidateQueries({ queryKey: ['products-count'] });
      void qc.invalidateQueries({ queryKey: ['stock'] });
      setNotice(
        result.deactivated
          ? { severity: 'info', message: result.detail || 'Product is referenced by documents; marked Inactive instead of deleting.' }
          : { severity: 'success', message: t('products.deleted') },
      );
    },
    onError: (err) => setNotice({ severity: 'error', message: getErrorMessage(err) }),
  });
  const pageRows = sourceRows;
  const optionRows = allQuery.data ?? pageRows;
  const rows = pageRows.filter((p) => {
    if (categoryFilter && (p.categoryName || '') !== categoryFilter) return false;
    if (brandFilter && (p.brandName || '') !== brandFilter) return false;
    if (taxFilter && String(toNumber(p.gstRate)) !== taxFilter) return false;
    const qty = stockMap.get(p.id);
    if (stockFilter === 'in' && !(qty != null && qty > toNumber(p.reorderLevel))) return false;
    if (stockFilter === 'low' && !(qty != null && qty > 0 && qty <= toNumber(p.reorderLevel))) return false;
    // An item with no stock rows has nothing on hand: it is out of stock, not "unknown".
    if (stockFilter === 'out' && !(qty == null || qty <= 0)) return false;
    return true;
  });
  const categories = [...new Set(optionRows.map((p) => p.categoryName).filter(Boolean))] as string[];
  const brands = [...new Set(optionRows.map((p) => p.brandName).filter(Boolean))] as string[];
  const taxSlabs = [...new Set(optionRows.map((p) => String(toNumber(p.gstRate))))];
  const showCol = (id: string) =>
    prefs.isVisible(id) && (showDense || id === 'name' || id === 'price' || id === 'stock');
  const canMutate = canAdjustInventory(user);
  const canContinueSetup =
    isSetupWizardEnabled() &&
    user?.role === 'OWNER' &&
    !user.company?.onboarding?.activationDone;
  const visibleCustom = customDefs.filter((def) => prefs.isVisible(`cf:${def.key}`));

  const openCreate = () => {
    setEditing(null);
    setOpen(true);
  };

  const exportCsv = async () => {
    setExporting(true);
    try {
      const cols = [
        ...standardColumns().filter((col) => prefs.isVisible(col.id)),
        ...visibleCustom.map((def) => ({ id: `cf:${def.key}`, label: def.label })),
      ];
      const header = cols.map((col) => csvCell(col.label)).join(',');
      const exported = await listProducts({
        q: search || undefined,
        cf: isItemCustomFieldsV2Enabled() ? cfFilters : undefined,
      });
      // The on-screen stock map only covers the current page; the export covers every product.
      const exportStock = new Map<number, number>();
      if (cols.some((col) => col.id === 'stock') && exported.length > 0) {
        for (const row of await listStock({ productIds: exported.map((p) => p.id) })) {
          exportStock.set(row.product, (exportStock.get(row.product) ?? 0) + toNumber(row.available));
        }
      }
      const lines = exported.map((p) =>
        cols
          .map((col) => {
            if (col.id === 'name') return p.name;
            if (col.id === 'sku') return p.sku;
            if (col.id === 'unit') return p.unitName || 'PCS';
            if (col.id === 'price') return String(p.sellingPrice ?? '');
            if (col.id === 'gst') return String(p.gstRate ?? '');
            if (col.id === 'stock') return String(exportStock.get(p.id) ?? '');
            if (col.id === 'tracking') {
              return [p.trackBatch ? t('items.batch') : '', p.trackSerial ? t('items.serial') : ''].filter(Boolean).join(' ');
            }
            if (col.id === 'status') return p.status;
            if (col.id.startsWith('cf:')) return customFieldCell(p.customFields, col.id.slice(3));
            return '';
          })
          .map((value) => csvCell(value))
          .join(','),
      );
      const blob = new Blob([`${header}\n${lines.join('\n')}`], { type: 'text/csv;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'items.csv';
      link.click();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  };

  if (!canViewInventorySurfaces(user)) {
    return <ForbiddenPage />;
  }

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1}>
        <PageTitle>{t('nav.products')}</PageTitle>
        <TextField
          size="small"
          placeholder={t('customFields.searchHint')}
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
          sx={{ minWidth: 220, flex: 1, maxWidth: 360 }}
        />
        <TextField select size="small" label={t('cog.filterCategory')} SelectProps={{ onOpen: () => setFiltersTouched(true) }} value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)} sx={{ minWidth: 140 }}>
          <MenuItem value="">{t('common.all')}</MenuItem>
          {categories.map((name) => <MenuItem key={name} value={name}>{name}</MenuItem>)}
        </TextField>
        <TextField select size="small" label={t('cog.filterBrand')} SelectProps={{ onOpen: () => setFiltersTouched(true) }} value={brandFilter} onChange={(e) => setBrandFilter(e.target.value)} sx={{ minWidth: 140 }}>
          <MenuItem value="">{t('common.all')}</MenuItem>
          {brands.map((name) => <MenuItem key={name} value={name}>{name}</MenuItem>)}
        </TextField>
        <TextField select size="small" label={t('cog.filterStock')} SelectProps={{ onOpen: () => setFiltersTouched(true) }} value={stockFilter} onChange={(e) => setStockFilter(e.target.value)} sx={{ minWidth: 140 }}>
          <MenuItem value="">{t('common.all')}</MenuItem>
          <MenuItem value="in">{t('cog.inStock')}</MenuItem>
          <MenuItem value="low">{t('cog.lowStock')}</MenuItem>
          <MenuItem value="out">{t('cog.outOfStock')}</MenuItem>
        </TextField>
        <TextField select size="small" label={t('cog.filterTax')} SelectProps={{ onOpen: () => setFiltersTouched(true) }} value={taxFilter} onChange={(e) => setTaxFilter(e.target.value)} sx={{ minWidth: 120 }}>
          <MenuItem value="">{t('common.all')}</MenuItem>
          {taxSlabs.map((rate) => <MenuItem key={rate} value={rate}>{rate}%</MenuItem>)}
        </TextField>
        <Button size="small" variant="outlined" onClick={() => setShowDense((v) => !v)}>
          {t('cog.moreColumns')}
        </Button>
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          {isItemCustomFieldsV2Enabled() ? (
            <ColumnPicker columns={columns} isVisible={prefs.isVisible} toggle={prefs.toggle} reset={prefs.reset} />
          ) : null}
          {rows.length ? (
            <Button size="small" variant="outlined" startIcon={<DownloadOutlinedIcon />} disabled={exporting} onClick={() => void exportCsv()}>
              {t('customFields.exportCsv')}
            </Button>
          ) : null}
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
            <Button variant="contained" onClick={openCreate}>
              {t('common.add')}
            </Button>
          ) : null}
        </Stack>
      </Stack>
      <CustomFieldFilterBar
        defs={customDefs}
        value={cfFilters}
        onChange={(next) => {
          setCfFilters(next);
          setPage(1);
        }}
      />
      {saveOk ? (
        <Alert severity="success" onClose={() => setSaveOk(false)}>
          {saveOk}
        </Alert>
      ) : null}
      {notice ? (
        <Alert severity={notice.severity} onClose={() => setNotice(null)}>
          {notice.message}
        </Alert>
      ) : null}
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
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
                <Button variant={canContinueSetup ? 'outlined' : 'contained'} onClick={openCreate}>
                  {t('common.add')} {t('nav.products')}
                </Button>
              ) : null}
            </Stack>
          }
        />
      ) : null}
      {rows.length > 0 ? (
        <Paper tabIndex={0} role="region" aria-label={t('common.scrollableTable')} sx={{ overflow: 'auto' }}>
          <VirtualizedTable rowCount={rows.length} rowHeight={52}>
            {({ rows: virtualRows, totalSize }) => (
          <Table size="small">
            <TableHead>
              <TableRow>
                {showCol('name') ? <TableCell>{t('common.name')}</TableCell> : null}
                {showCol('sku') ? <TableCell>{t('common.sku')}</TableCell> : null}
                {showCol('unit') ? <TableCell>{t('products.unit')}</TableCell> : null}
                {showCol('price') ? <TableCell align="right">{t('products.sellingPrice')}</TableCell> : null}
                {showCol('gst') ? <TableCell align="right">{t('products.gstPercent')}</TableCell> : null}
                {showCol('stock') ? <TableCell align="right">{t('billing.stockAvailable')}</TableCell> : null}
                {showCol('tracking') ? <TableCell>{t('products.tracking')}</TableCell> : null}
                {visibleCustom.map((def) => (
                  <TableCell key={def.key}>{def.label}</TableCell>
                ))}
                {showCol('status') ? <TableCell>{t('common.status')}</TableCell> : null}
                <TableCell />
              </TableRow>
            </TableHead>
            <TableBody>
              {virtualRows.length > 0 && virtualRows[0].start > 0 ? (
                <TableRow style={{ height: virtualRows[0].start }} aria-hidden>
                  <TableCell style={{ padding: 0, border: 0 }} colSpan={12} />
                </TableRow>
              ) : null}
              {virtualRows.map((vRow) => {
                const p = rows[vRow.index];
                const stockQty = stockMap.get(p.id);
                return (
                  <TableRow key={p.id} data-index={vRow.index}>
                    {showCol('name') ? (
                      <TableCell>
                        {p.name}
                        {p.rackCode ? (
                          <Chip size="small" label={`${t('products.rack')} ${p.rackCode}`} sx={{ ml: 1 }} />
                        ) : null}
                      </TableCell>
                    ) : null}
                    {showCol('sku') ? <TableCell>{p.sku}</TableCell> : null}
                    {showCol('unit') ? <TableCell>{p.unitName || 'PCS'}</TableCell> : null}
                    {showCol('price') ? <TableCell align="right">{formatMoney(p.sellingPrice)}</TableCell> : null}
                    {showCol('gst') ? <TableCell align="right">{toNumber(p.gstRate)}%</TableCell> : null}
                    {showCol('stock') ? (
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
                    ) : null}
                    {showCol('tracking') ? (
                      <TableCell>
                        {p.trackBatch ? <Chip size="small" label={t('items.batch')} sx={{ mr: 0.5 }} /> : null}
                        {p.trackSerial ? <Chip size="small" label={t('items.serial')} /> : null}
                        {!p.trackBatch && !p.trackSerial ? '—' : null}
                      </TableCell>
                    ) : null}
                    {visibleCustom.map((def) => (
                      <TableCell key={def.key}>{customFieldCell(p.customFields, def.key)}</TableCell>
                    ))}
                    {showCol('status') ? (
                      <TableCell>
                        <StatusChip tone={productStatusTone(p.status)} labelKey={statusLabelKey(p.status)} />
                      </TableCell>
                    ) : null}
                    <TableCell align="right">
                      {canMutate ? (
                        <Stack direction="row" spacing={0.5} justifyContent="flex-end">
                          <Button
                            size="small"
                            onClick={() => {
                              setEditing(p);
                              setOpen(true);
                            }}
                          >
                            {t('common.edit')}
                          </Button>
                          <Button
                            size="small"
                            color="error"
                            disabled={removeProduct.isPending}
                            onClick={() => {
                              setNotice(null);
                              if (!window.confirm(t('products.confirmDelete'))) return;
                              removeProduct.mutate(p.id);
                            }}
                          >
                            {t('common.delete')}
                          </Button>
                        </Stack>
                      ) : null}
                    </TableCell>
                  </TableRow>
                );
              })}
              {virtualRows.length > 0 &&
              Math.max(0, totalSize - virtualRows[virtualRows.length - 1].end) > 0 ? (
                <TableRow
                  style={{ height: Math.max(0, totalSize - virtualRows[virtualRows.length - 1].end) }}
                  aria-hidden
                >
                  <TableCell style={{ padding: 0, border: 0 }} colSpan={12} />
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
            )}
          </VirtualizedTable>
        </Paper>
      ) : null}
      {query.data && !filtersActive && (query.data.next || page > 1) ? (
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

      <ItemFormDialog
        open={open}
        product={editing}
        existingNames={rows.map((row) => row.name)}
        onClose={() => {
          setOpen(false);
          setEditing(null);
        }}
        onSaved={(keepOpen, rateNotice) => {
          setSaveOk(rateNotice ? `Product saved. ${rateNotice}` : 'Product saved.');
          if (!keepOpen) {
            setOpen(false);
            setEditing(null);
          }
        }}
      />
    </Stack>
  );
}
