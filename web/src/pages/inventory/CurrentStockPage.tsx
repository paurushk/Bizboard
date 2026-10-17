import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Checkbox from '@mui/material/Checkbox';
import Chip from '@mui/material/Chip';
import FormControlLabel from '@mui/material/FormControlLabel';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Button from '@mui/material/Button';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import TextField from '@mui/material/TextField';
import { useInfiniteQuery, useMutation, useQueries, useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { Link as RouterLink, useSearchParams } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import {
  exportReport,
  getInventorySummary,
  listAllStockByProduct,
  listStock,
  listStockByProduct,
  listWarehouses,
  type StockByProductRow,
} from '@/api/resources';
import { ColumnPicker } from '@/components/ColumnPicker';
import { CustomFieldFilterBar } from '@/components/CustomFieldFilterBar';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import {
  EMPTY_HISTORY_FILTERS,
  HistoryFilterBar,
  type HistoryFilters,
} from '@/components/HistoryFilterBar';
import { VirtualizedTable } from '@/components/VirtualizedTable';
import { useVisibleCustomFieldDefs } from '@/hooks/useActiveCustomFieldDefs';
import { useAuth } from '@/auth/AuthContext';
import { useCfFilters } from '@/hooks/useCfFilters';
import { useColumnPrefs, type ColumnSpec } from '@/hooks/useColumnPrefs';
import { isItemCustomFieldsV2Enabled } from '@/config/features';
import { PageTitle } from '@/contextHelp';
import { t, useLocale } from '@/i18n';
import type { StockBalance } from '@/types/domain';
import { formatMoney, toNumber } from '@/utils/money';
import { canAdjustInventory, canExport } from '@/utils/permissions';
import { customFieldCell } from '@/pages/inventory/itemCustomFieldDefaults';
import { lotKey, SORT_OPTIONS, type StockSort } from '@/pages/inventory/stockListHelpers';
import { computeStockKpis, type SummaryRow } from '@/pages/inventory/stockKpis';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';

type StockRow = StockByProductRow & {
  warehouseLabel: string;
  onHandNum: number;
  reservedNum: number;
  availableNum: number;
};

type LotRow = StockBalance & {
  warehouseLabel: string;
  onHandNum: number;
  reservedNum: number;
  availableNum: number;
  lotLabel: string;
};

const SORT_LABEL: Record<StockSort, string> = {
  name: 'inventory.stockSortName',
  available: 'inventory.stockSortLeast',
  '-available': 'inventory.stockSortMost',
  '-on_hand': 'inventory.stockSortOnHand',
};

export function CurrentStockPage() {
  const locale = useLocale();
  const { user } = useAuth();
  const canAdjust = canAdjustInventory(user);
  const [searchParams, setSearchParams] = useSearchParams();
  // The filters live in the address bar so a refresh, a shared link or Back keeps the view.
  const [filters, setFilters] = useState<HistoryFilters>({ ...EMPTY_HISTORY_FILTERS, q: searchParams.get('q') ?? '' });
  const warehouse = searchParams.get('warehouse') ?? '';
  const sortParam = searchParams.get('sort') as StockSort | null;
  const sort: StockSort = sortParam && SORT_OPTIONS.includes(sortParam) ? sortParam : 'name';
  const onlyOut = searchParams.get('out') === '1';
  const patchParams = (patch: Record<string, string>) => {
    const next = new URLSearchParams(searchParams);
    for (const [key, value] of Object.entries(patch)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    setSearchParams(next, { replace: true });
  };
  useEffect(() => {
    if ((searchParams.get('q') ?? '') !== filters.q) patchParams({ q: filters.q });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters.q]);

  const customDefs = useVisibleCustomFieldDefs();
  const { value: cfFilters, onChange: setCfFilters } = useCfFilters();
  const columns = useMemo<ColumnSpec[]>(
    () => [
      { id: 'name', label: t('common.name'), group: 'standard', removable: false },
      { id: 'sku', label: t('common.sku'), group: 'standard' },
      { id: 'warehouse', label: t('items.godown'), group: 'standard' },
      { id: 'expiry', label: t('items.nearestExpiry'), group: 'standard' },
      { id: 'onHand', label: t('items.onHand'), group: 'standard' },
      { id: 'reserved', label: t('products.reserved'), group: 'standard' },
      { id: 'available', label: t('items.available'), group: 'standard' },
      ...customDefs.map((def) => ({ id: `cf:${def.key}`, label: def.label, group: 'custom' as const })),
    ],
    // locale: the labels come from t(), so they must be rebuilt when the language changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [customDefs, locale],
  );
  const prefs = useColumnPrefs('stock', columns, user?.companyId, user?.id);

  const listParams = {
    q: filters.q || undefined,
    cf: isItemCustomFieldsV2Enabled() ? cfFilters : undefined,
    warehouse: warehouse ? Number(warehouse) : undefined,
    ordering: sort,
    negative: onlyOut,
  };
  // The server groups, sorts and pages: a big catalogue no longer travels to the browser to be added up.
  const query = useInfiniteQuery({
    queryKey: ['stock', 'grouped', listParams],
    queryFn: ({ pageParam }) => listStockByProduct({ ...listParams, page: pageParam }),
    initialPageParam: 1,
    getNextPageParam: (last, pages) => (last.next ? pages.length + 1 : undefined),
  });
  const summary = useQuery({ queryKey: ['inventory-summary'], queryFn: getInventorySummary });
  const exportMutation = useMutation({
    mutationFn: () => exportReport('inventory', { warehouse: warehouse || undefined, q: filters.q || undefined }),
    onSuccess: (r) => {
      const a = document.createElement('a');
      a.href = r.url;
      a.download = 'inventory-summary.csv';
      document.body.appendChild(a);
      a.click();
      a.remove();
    },
  });
  const warehouses = useQuery({ queryKey: ['warehouses'], queryFn: listWarehouses });
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const visibleCustom = customDefs.filter((def) => prefs.isVisible(`cf:${def.key}`));

  const warehouseName = useMemo(() => {
    const map = new Map<number | string, string>();
    for (const w of warehouses.data ?? []) {
      map.set(w.id, w.name);
      map.set(String(w.id), w.name);
    }
    return map;
  }, [warehouses.data]);

  const rows = useMemo<StockRow[]>(
    () =>
      (query.data?.pages ?? []).flatMap((page) => page.results).map((s) => ({
        ...s,
        warehouseLabel: s.warehouse ? (warehouseName.get(s.warehouse) ?? String(s.warehouse)) : t('inventory.stockAllGodowns'),
        onHandNum: toNumber(s.onHand),
        reservedNum: toNumber(s.reserved),
        availableNum: toNumber(s.available),
      })),
    [query.data, warehouseName],
  );
  const total = query.data?.pages[0]?.count ?? 0;
  const serverSummary = query.data?.pages[0]?.summary;

  // Lots are fetched for the items the user opens, not for the whole catalogue.
  const openIds = Object.keys(expanded).filter((id) => expanded[id]).map(Number);
  const lotQueries = useQueries({
    queries: openIds.map((id) => ({
      queryKey: ['stock', 'lots', id, warehouse],
      queryFn: () => listStock({ productIds: [id], warehouse: warehouse ? Number(warehouse) : undefined }),
    })),
  });
  const lotsStamp = lotQueries.map((q) => q.dataUpdatedAt).join(',');
  const openKey = openIds.join(',');
  const lotsByProduct = useMemo(() => {
    const map = new Map<number, LotRow[]>();
    openIds.forEach((id, index) => {
      const data = lotQueries[index]?.data;
      if (!data) return;
      map.set(
        id,
        data.map((s) => ({
          ...s,
          warehouseLabel: warehouseName.get(s.warehouse as never) ?? String(s.warehouse ?? '—'),
          onHandNum: toNumber(s.onHand),
          reservedNum: toNumber(s.reserved),
          availableNum: toNumber(s.available),
          lotLabel: s.batchNo ? String(s.batchNo) : t('inventory.stockNoLot'),
        })),
      );
    });
    return map;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lotsStamp, openKey, warehouseName]);

  // The list is windowed: group rows and the lots of opened items are flattened into one array.
  type FlatRow =
    | { key: string; kind: 'group'; groupRow: StockRow }
    | { key: string; kind: 'lot'; lotRow: LotRow };
  const flatRows = useMemo<FlatRow[]>(() => {
    const out: FlatRow[] = [];
    for (const s of rows) {
      const rowKey = `p-${s.product}-${s.warehouse ?? 'all'}`;
      out.push({ key: rowKey, kind: 'group', groupRow: s });
      if (expanded[s.product]) {
        for (const lot of lotsByProduct.get(s.product) ?? []) {
          out.push({ key: lotKey(lot), kind: 'lot', lotRow: lot });
        }
      }
    }
    return out;
  }, [rows, expanded, lotsByProduct]);

  // Figures that move with the filters: items (not a sum of unlike units) and the value of the rows shown.
  const summaryRows = useMemo(
    () => ((summary.data as { rows?: SummaryRow[] } | undefined)?.rows ?? []) as SummaryRow[],
    [summary.data],
  );
  const kpis = useMemo(() => {
    const base = computeStockKpis([], summaryRows, {
      warehouseId: warehouse,
      query: filters.q,
      customFieldFilterActive: Object.values(cfFilters).some((values) => values.length > 0),
    });
    return {
      ...base,
      // A person who may not read the books gets a refusal here: show no value, not "0".
      value: summary.isError || summary.isLoading ? null : base.value,
      hasDrift: summary.isError ? false : base.hasDrift,
      itemsInStock: serverSummary?.itemsInStock ?? 0,
      itemsOut: serverSummary?.itemsOut ?? 0,
    };
  }, [summaryRows, warehouse, filters.q, cfFilters, serverSummary, summary.isError, summary.isLoading]);

  // Print: the on-screen table is windowed, so printing it would cut off everything below the fold.
  // Fetch every row for the current filters into a plain table and print that instead.
  const [printRows, setPrintRows] = useState<StockRow[] | null>(null);
  const [printing, setPrinting] = useState(false);
  const [printError, setPrintError] = useState('');
  const startPrint = async () => {
    setPrinting(true);
    setPrintError('');
    try {
      const all = await listAllStockByProduct(listParams);
      setPrintRows(
        all.map((s) => ({
          ...s,
          warehouseLabel: s.warehouse ? (warehouseName.get(s.warehouse) ?? String(s.warehouse)) : t('inventory.stockAllGodowns'),
          onHandNum: toNumber(s.onHand),
          reservedNum: toNumber(s.reserved),
          availableNum: toNumber(s.available),
        })),
      );
    } catch (e) {
      setPrintError(getErrorMessage(e));
    } finally {
      setPrinting(false);
    }
  };
  useEffect(() => {
    if (!printRows) return;
    // Let the print table reach the page first; print() blocks until the dialog closes.
    const id = window.setTimeout(() => {
      window.print();
      setPrintRows(null);
    }, 0);
    return () => window.clearTimeout(id);
  }, [printRows]);

  return (
    <Stack spacing={2}>
      <Box sx={{ '@media print': { display: 'none' } }}>
        <Stack spacing={2}>
          <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1}>
            <PageTitle>{t('nav.currentStock')}</PageTitle>
            <Stack direction="row" spacing={1} flexWrap="wrap">
              {isItemCustomFieldsV2Enabled() ? (
                <ColumnPicker columns={columns} isVisible={prefs.isVisible} toggle={prefs.toggle} reset={prefs.reset} />
              ) : null}
              {canExport(user) ? (
                <Button size="small" variant="outlined" disabled={exportMutation.isPending} onClick={() => exportMutation.mutate()}>
                  {t('inventory.downloadCsv')}
                </Button>
              ) : null}
              <Button size="small" variant="outlined" disabled={printing} onClick={() => void startPrint()}>
                {printing ? t('inventory.stockPreparingPrint') : t('common.print')}
              </Button>
            </Stack>
          </Stack>
          <HistoryFilterBar
            value={filters}
            onChange={setFilters}
            showDateRange={false}
            searchPlaceholder={t('customFields.searchHint')}
          />
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <Chip size="small" label={t('inventory.kpiInStock', { count: String(kpis.itemsInStock) })} />
            <Chip size="small" color={kpis.itemsOut ? 'warning' : 'default'} label={t('inventory.kpiOut', { count: String(kpis.itemsOut) })} />
            {kpis.value !== null ? (
              <Chip size="small" label={`${t('reports.stockValue')}: ${formatMoney(kpis.value)}`} />
            ) : null}
          </Stack>
          {kpis.hasDrift ? (
            <Alert
              severity="warning"
              action={
                <Button color="inherit" size="small" component={RouterLink} to="/reports/inventory">
                  {t('inventory.driftOpenReport')}
                </Button>
              }
            >
              {t('inventory.driftWarning')}
            </Alert>
          ) : null}
          {exportMutation.isError ? <HelpErrorAlert error={exportMutation.error} /> : null}
          {printError ? <Alert severity="error" onClose={() => setPrintError('')}>{printError}</Alert> : null}
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ sm: 'center' }} flexWrap="wrap" useFlexGap>
            <TextField
              select
              size="small"
              label={t('nav.warehouses')}
              value={warehouse}
              onChange={(e) => patchParams({ warehouse: e.target.value })}
              sx={{ minWidth: 200, maxWidth: 280 }}
            >
              <MenuItem value="">{t('inventory.stockAllGodowns')}</MenuItem>
              {(warehouses.data ?? []).map((item) => (
                <MenuItem key={item.id} value={String(item.id)}>
                  {item.name}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              size="small"
              label={t('inventory.stockSort')}
              value={sort}
              onChange={(e) => patchParams({ sort: e.target.value === 'name' ? '' : e.target.value })}
              sx={{ minWidth: 200 }}
            >
              {SORT_OPTIONS.map((option) => (
                <MenuItem key={option} value={option}>
                  {t(SORT_LABEL[option])}
                </MenuItem>
              ))}
            </TextField>
            <FormControlLabel
              control={<Checkbox size="small" checked={onlyOut} onChange={(e) => patchParams({ out: e.target.checked ? '1' : '' })} />}
              label={t('inventory.stockOnlyOut')}
            />
            <CustomFieldFilterBar defs={customDefs} value={cfFilters} onChange={setCfFilters} />
          </Stack>
          {query.isLoading ? <LoadingState /> : null}
          {query.isError ? (
            <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
          ) : null}
          {!query.isLoading && !query.isError && rows.length === 0 ? (
            <EmptyState
              description={
                filters.q || warehouse || onlyOut || Object.values(cfFilters).some((v) => v.length) ? t('empty.stockFiltered') : t('empty.stock')
              }
            />
          ) : null}
          {rows.length > 0 ? (
            <Paper sx={{ overflow: 'hidden' }}>
              <VirtualizedTable rowCount={flatRows.length} rowHeight={52}>
                {({ rows: virtualRows, totalSize, measureElement }) => {
                  const colCount =
                    (prefs.isVisible('name') ? 1 : 0) +
                    (prefs.isVisible('sku') ? 1 : 0) +
                    visibleCustom.length +
                    (prefs.isVisible('warehouse') ? 1 : 0) +
                    (prefs.isVisible('expiry') ? 1 : 0) +
                    (prefs.isVisible('onHand') ? 1 : 0) +
                    (prefs.isVisible('reserved') ? 1 : 0) +
                    (prefs.isVisible('available') ? 1 : 0);
                  return (
                    <Table size="small" stickyHeader>
                      <TableHead>
                        <TableRow>
                          {prefs.isVisible('name') ? <TableCell>{t('common.name')}</TableCell> : null}
                          {prefs.isVisible('sku') ? <TableCell>{t('common.sku')}</TableCell> : null}
                          {visibleCustom.map((def) => (
                            <TableCell key={def.key}>{def.label}</TableCell>
                          ))}
                          {prefs.isVisible('warehouse') ? <TableCell>{t('nav.warehouses')}</TableCell> : null}
                          {prefs.isVisible('expiry') ? <TableCell>{t('items.nearestExpiry')}</TableCell> : null}
                          {prefs.isVisible('onHand') ? <TableCell align="right">{t('items.onHand')}</TableCell> : null}
                          {prefs.isVisible('reserved') ? (
                            <TableCell align="right">
                              {t('products.reserved')}{' '}
                              <Tooltip title={t('billing.reservedStockHint')}>
                                <span
                                  role="img"
                                  aria-label={t('billing.reservedStockHint')}
                                  tabIndex={0}
                                  style={{ verticalAlign: 'middle', cursor: 'help', display: 'inline-flex' }}
                                >
                                  <InfoOutlinedIcon fontSize="inherit" />
                                </span>
                              </Tooltip>
                            </TableCell>
                          ) : null}
                          {prefs.isVisible('available') ? <TableCell align="right">{t('items.available')}</TableCell> : null}
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {virtualRows.length ? (
                          <TableRow style={{ height: virtualRows[0].start, padding: 0, border: 0 }} aria-hidden>
                            <TableCell style={{ padding: 0, border: 0 }} colSpan={colCount} />
                          </TableRow>
                        ) : null}
                        {virtualRows.map((vRow) => {
                          const flat = flatRows[vRow.index];
                          if (flat.kind === 'group') {
                            const s = flat.groupRow;
                            const isOpen = Boolean(expanded[s.product]);
                            return (
                              <TableRow key={flat.key} data-index={vRow.index} ref={measureElement}>
                                {prefs.isVisible('name') ? (
                                  <TableCell
                                    sx={{
                                      position: { xs: 'sticky', md: 'static' },
                                      left: 0,
                                      zIndex: 1,
                                      bgcolor: 'background.paper',
                                      minWidth: 120,
                                    }}
                                  >
                                    {s.lots > 0 ? (
                                      <Button
                                        size="small"
                                        onClick={() => setExpanded((current) => ({ ...current, [s.product]: !isOpen }))}
                                      >
                                        {isOpen ? t('inventory.stockHideLots') : t('inventory.stockShowLots')}
                                      </Button>
                                    ) : null}{' '}
                                    {s.productName}
                                    {s.rackCode ? ` · ${t('products.rack')} ${s.rackCode}` : ''}
                                    {' '}
                                    <Button
                                      size="small"
                                      component={RouterLink}
                                      to={`/inventory/ledger?product=${s.product}${warehouse ? `&warehouse=${warehouse}` : ''}`}
                                      aria-label={`${t('inventory.viewLedger')}: ${s.productName}`}
                                    >
                                      {t('inventory.viewLedger')}
                                    </Button>
                                    {canAdjust ? (
                                      <>
                                        <Button
                                          size="small"
                                          component={RouterLink}
                                          to={`/inventory/adjustments?product=${s.product}${warehouse ? `&warehouse=${warehouse}` : ''}`}
                                          aria-label={`${t('inventory.adjustFromRow')}: ${s.productName}`}
                                        >
                                          {t('inventory.adjustFromRow')}
                                        </Button>
                                        <Button
                                          size="small"
                                          component={RouterLink}
                                          to={`/inventory/transfers?product=${s.product}${warehouse ? `&from=${warehouse}` : ''}`}
                                          aria-label={`${t('inventory.transferFromRow')}: ${s.productName}`}
                                        >
                                          {t('inventory.transferFromRow')}
                                        </Button>
                                      </>
                                    ) : null}
                                  </TableCell>
                                ) : null}
                                {prefs.isVisible('sku') ? <TableCell>{s.sku}</TableCell> : null}
                                {visibleCustom.map((def) => (
                                  <TableCell key={def.key}>{customFieldCell(s.customFields, def.key)}</TableCell>
                                ))}
                                {prefs.isVisible('warehouse') ? <TableCell>{s.warehouseLabel}</TableCell> : null}
                                {prefs.isVisible('expiry') ? <TableCell>{s.nearestExpiry ?? '—'}</TableCell> : null}
                                {prefs.isVisible('onHand') ? (
                                  <TableCell
                                    align="right"
                                    sx={{
                                      fontWeight: 600,
                                      color: s.availableNum < 0 ? 'error.main' : undefined,
                                    }}
                                  >
                                    {s.onHandNum}
                                  </TableCell>
                                ) : null}
                                {prefs.isVisible('reserved') ? <TableCell align="right">{s.reservedNum}</TableCell> : null}
                                {prefs.isVisible('available') ? (
                                  <TableCell
                                    align="right"
                                    sx={{
                                      color: s.availableNum < 0 ? 'error.main' : 'success.main',
                                      fontWeight: 600,
                                    }}
                                  >
                                    {s.availableNum}
                                  </TableCell>
                                ) : null}
                              </TableRow>
                            );
                          }
                          const lot = flat.lotRow;
                          return (
                            <TableRow
                              key={flat.key}
                              data-index={vRow.index}
                              ref={measureElement}
                              sx={{ bgcolor: 'action.hover' }}
                            >
                              {prefs.isVisible('name') ? <TableCell sx={{ pl: 6 }}>{lot.lotLabel}</TableCell> : null}
                              {prefs.isVisible('sku') ? <TableCell /> : null}
                              {visibleCustom.map((def) => (
                                <TableCell key={def.key} />
                              ))}
                              {prefs.isVisible('warehouse') ? <TableCell>{lot.warehouseLabel}</TableCell> : null}
                              {prefs.isVisible('expiry') ? <TableCell>{lot.nearestExpiry ?? '—'}</TableCell> : null}
                              {prefs.isVisible('onHand') ? <TableCell align="right">{lot.onHandNum}</TableCell> : null}
                              {prefs.isVisible('reserved') ? <TableCell align="right">{lot.reservedNum}</TableCell> : null}
                              {prefs.isVisible('available') ? <TableCell align="right">{lot.availableNum}</TableCell> : null}
                            </TableRow>
                          );
                        })}
                        {virtualRows.length ? (
                          <TableRow
                            style={{ height: totalSize - virtualRows[virtualRows.length - 1].end, padding: 0, border: 0 }}
                            aria-hidden
                          >
                            <TableCell style={{ padding: 0, border: 0 }} colSpan={colCount} />
                          </TableRow>
                        ) : null}
                      </TableBody>
                    </Table>
                  );
                }}
              </VirtualizedTable>
            </Paper>
          ) : null}
          {rows.length > 0 ? (
            <Stack direction="row" spacing={2} alignItems="center">
              <Typography variant="body2" color="text.secondary">
                {t('inventory.stockShowing', { shown: String(rows.length), total: String(total) })}
              </Typography>
              {query.hasNextPage ? (
                <Button size="small" disabled={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>
                  {t('inventory.stockLoadMore')}
                </Button>
              ) : null}
            </Stack>
          ) : null}
        </Stack>
      </Box>
      {/* Only drawn for the printer: every row, no windowing. */}
      <Box sx={{ display: 'none', '@media print': { display: printRows ? 'block' : 'none' } }}>
        <Typography variant="h6">{t('nav.currentStock')}</Typography>
        <Table size="small" aria-label={t('inventory.stockPrintTable')}>
          <TableHead>
            <TableRow>
              <TableCell>{t('common.name')}</TableCell>
              <TableCell>{t('common.sku')}</TableCell>
              <TableCell>{t('nav.warehouses')}</TableCell>
              <TableCell align="right">{t('items.onHand')}</TableCell>
              <TableCell align="right">{t('products.reserved')}</TableCell>
              <TableCell align="right">{t('items.available')}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {(printRows ?? []).map((s) => (
              <TableRow key={`print-${s.product}-${s.warehouse ?? 'all'}`}>
                <TableCell>{s.productName}</TableCell>
                <TableCell>{s.sku}</TableCell>
                <TableCell>{s.warehouseLabel}</TableCell>
                <TableCell align="right">{s.onHandNum}</TableCell>
                <TableCell align="right">{s.reservedNum}</TableCell>
                <TableCell align="right">{s.availableNum}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Box>
    </Stack>
  );
}
