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
import { useQuery } from '@tanstack/react-query';
import { Link as RouterLink, useNavigate } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { listProducts, listProductsPage, listStock } from '@/api/resources';
import { ItemFormDialog } from '@/pages/inventory/ItemFormDialog';
import { useAuth } from '@/auth/AuthContext';
import { ColumnPicker } from '@/components/ColumnPicker';
import { CustomFieldFilterBar } from '@/components/CustomFieldFilterBar';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { StatusChip } from '@/components/StatusChip';
import { useVisibleCustomFieldDefs } from '@/hooks/useActiveCustomFieldDefs';
import { useCfFilters } from '@/hooks/useCfFilters';
import { useColumnPrefs, type ColumnSpec } from '@/hooks/useColumnPrefs';
import { t } from '@/i18n';
import type { Product } from '@/types/domain';
import { formatMoney, toNumber } from '@/utils/money';
import { canImport, isViewer } from '@/utils/permissions';
import { productStatusTone, statusLabelKey } from '@/utils/status';
import { isItemCustomFieldsV2Enabled, isSetupWizardEnabled } from '@/config/features';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { customFieldCell } from '@/pages/inventory/itemCustomFieldDefaults';

const PAGE_SIZE = 50;

const STANDARD_COLUMNS: ColumnSpec[] = [
  { id: 'name', label: 'Name', group: 'standard', removable: false },
  { id: 'sku', label: 'SKU', group: 'standard' },
  { id: 'unit', label: 'Unit', group: 'standard' },
  { id: 'price', label: 'Selling price', group: 'standard' },
  { id: 'gst', label: 'GST %', group: 'standard' },
  { id: 'stock', label: 'Stock', group: 'standard' },
  { id: 'tracking', label: 'Tracking', group: 'standard' },
  { id: 'status', label: 'Status', group: 'standard' },
];

function csvEscape(value: string) {
  return `"${value.replace(/"/g, '""')}"`;
}

export function ProductsPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const debouncedSearch = useDebouncedValue(search, 300);
  const customDefs = useVisibleCustomFieldDefs();
  const { value: cfFilters, onChange: setCfFilters } = useCfFilters();
  const columns = useMemo<ColumnSpec[]>(
    () => [
      ...STANDARD_COLUMNS,
      ...customDefs.map((def) => ({ id: `cf:${def.key}`, label: def.label, group: 'custom' as const })),
    ],
    [customDefs],
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
  const stockQuery = useQuery({ queryKey: ['stock'], queryFn: () => listStock() });

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
  const [saveOk, setSaveOk] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [bulkAnchor, setBulkAnchor] = useState<null | HTMLElement>(null);
  const rows = query.data?.results ?? [];
  const canMutate = !!user && !isViewer(user.role);
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
        ...STANDARD_COLUMNS.filter((col) => prefs.isVisible(col.id)),
        ...visibleCustom.map((def) => ({ id: `cf:${def.key}`, label: def.label })),
      ];
      const header = cols.map((col) => csvEscape(col.label)).join(',');
      const exported = await listProducts({
        q: search || undefined,
        cf: isItemCustomFieldsV2Enabled() ? cfFilters : undefined,
      });
      const lines = exported.map((p) =>
        cols
          .map((col) => {
            if (col.id === 'name') return p.name;
            if (col.id === 'sku') return p.sku;
            if (col.id === 'unit') return p.unitName || 'PCS';
            if (col.id === 'price') return String(p.sellingPrice ?? '');
            if (col.id === 'gst') return String(p.gstRate ?? '');
            if (col.id === 'stock') return String(stockMap.get(p.id) ?? '');
            if (col.id === 'tracking') {
              return [p.trackBatch ? 'Batch' : '', p.trackSerial ? 'Serial' : ''].filter(Boolean).join(' ');
            }
            if (col.id === 'status') return p.status;
            if (col.id.startsWith('cf:')) return customFieldCell(p.customFields, col.id.slice(3));
            return '';
          })
          .map((value) => csvEscape(String(value)))
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

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1}>
        <Typography variant="h4">{t('nav.products')}</Typography>
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
          Product saved.
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
        <Paper sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                {prefs.isVisible('name') ? <TableCell>{t('common.name')}</TableCell> : null}
                {prefs.isVisible('sku') ? <TableCell>{t('common.sku')}</TableCell> : null}
                {prefs.isVisible('unit') ? <TableCell>{t('products.unit')}</TableCell> : null}
                {prefs.isVisible('price') ? <TableCell align="right">{t('products.sellingPrice')}</TableCell> : null}
                {prefs.isVisible('gst') ? <TableCell align="right">GST %</TableCell> : null}
                {prefs.isVisible('stock') ? <TableCell align="right">{t('billing.stockAvailable')}</TableCell> : null}
                {prefs.isVisible('tracking') ? <TableCell>Tracking</TableCell> : null}
                {visibleCustom.map((def) => (
                  <TableCell key={def.key}>{def.label}</TableCell>
                ))}
                {prefs.isVisible('status') ? <TableCell>{t('common.status')}</TableCell> : null}
                <TableCell />
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((p) => {
                const stockQty = stockMap.get(p.id);
                return (
                  <TableRow key={p.id}>
                    {prefs.isVisible('name') ? <TableCell>{p.name}</TableCell> : null}
                    {prefs.isVisible('sku') ? <TableCell>{p.sku}</TableCell> : null}
                    {prefs.isVisible('unit') ? <TableCell>{p.unitName || 'PCS'}</TableCell> : null}
                    {prefs.isVisible('price') ? <TableCell align="right">{formatMoney(p.sellingPrice)}</TableCell> : null}
                    {prefs.isVisible('gst') ? <TableCell align="right">{toNumber(p.gstRate)}%</TableCell> : null}
                    {prefs.isVisible('stock') ? (
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
                    {prefs.isVisible('tracking') ? (
                      <TableCell>
                        {p.trackBatch ? <Chip size="small" label="Batch" sx={{ mr: 0.5 }} /> : null}
                        {p.trackSerial ? <Chip size="small" label="Serial" /> : null}
                        {!p.trackBatch && !p.trackSerial ? '—' : null}
                      </TableCell>
                    ) : null}
                    {visibleCustom.map((def) => (
                      <TableCell key={def.key}>{customFieldCell(p.customFields, def.key)}</TableCell>
                    ))}
                    {prefs.isVisible('status') ? (
                      <TableCell>
                        <StatusChip tone={productStatusTone(p.status)} labelKey={statusLabelKey(p.status)} />
                      </TableCell>
                    ) : null}
                    <TableCell align="right">
                      {canMutate ? (
                        <Button
                          size="small"
                          onClick={() => {
                            setEditing(p);
                            setOpen(true);
                          }}
                        >
                          {t('common.edit')}
                        </Button>
                      ) : null}
                    </TableCell>
                  </TableRow>
                );
              })}
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

      <ItemFormDialog
        open={open}
        product={editing}
        existingNames={rows.map((row) => row.name)}
        onClose={() => {
          setOpen(false);
          setEditing(null);
        }}
        onSaved={(keepOpen) => {
          setSaveOk(true);
          if (!keepOpen) {
            setOpen(false);
            setEditing(null);
          }
        }}
      />
    </Stack>
  );
}
