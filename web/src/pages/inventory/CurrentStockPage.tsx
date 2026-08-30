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
import TextField from '@mui/material/TextField';
import { useQuery } from '@tanstack/react-query';
import { useMemo, useState, Fragment } from 'react';
import { getErrorMessage } from '@/api/client';
import { listStock, listWarehouses } from '@/api/resources';
import { ColumnPicker } from '@/components/ColumnPicker';
import { CustomFieldFilterBar } from '@/components/CustomFieldFilterBar';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { useVisibleCustomFieldDefs } from '@/hooks/useActiveCustomFieldDefs';
import { useAuth } from '@/auth/AuthContext';
import { useCfFilters } from '@/hooks/useCfFilters';
import { useColumnPrefs, type ColumnSpec } from '@/hooks/useColumnPrefs';
import { isItemCustomFieldsV2Enabled } from '@/config/features';
import { t } from '@/i18n';
import type { StockBalance } from '@/types/domain';
import { toNumber } from '@/utils/money';
import { customFieldCell } from '@/pages/inventory/itemCustomFieldDefaults';

type StockRow = StockBalance & {
  warehouseLabel: string;
  onHandNum: number;
  reservedNum: number;
  availableNum: number;
  nearestExpiryLabel: string;
  lots?: StockRow[];
  lotLabel?: string;
};

function earlierDate(a?: string | null, b?: string | null): string | null {
  if (!a) return b ?? null;
  if (!b) return a;
  return a < b ? a : b;
}

export function CurrentStockPage() {
  const { user } = useAuth();
  const [search, setSearch] = useState('');
  const customDefs = useVisibleCustomFieldDefs();
  const { value: cfFilters, onChange: setCfFilters } = useCfFilters();
  const columns = useMemo<ColumnSpec[]>(
    () => [
      { id: 'name', label: 'Name', group: 'standard', removable: false },
      { id: 'sku', label: 'SKU', group: 'standard' },
      { id: 'warehouse', label: 'Godown', group: 'standard' },
      { id: 'expiry', label: 'Nearest expiry', group: 'standard' },
      { id: 'onHand', label: 'On Hand', group: 'standard' },
      { id: 'reserved', label: 'Reserved', group: 'standard' },
      { id: 'available', label: 'Available', group: 'standard' },
      ...customDefs.map((def) => ({ id: `cf:${def.key}`, label: def.label, group: 'custom' as const })),
    ],
    [customDefs],
  );
  const prefs = useColumnPrefs('stock', columns, user?.companyId, user?.id);
  const query = useQuery({
    queryKey: ['stock', search, cfFilters],
    queryFn: () =>
      listStock({
        q: search || undefined,
        cf: isItemCustomFieldsV2Enabled() ? cfFilters : undefined,
      }),
  });
  const warehouses = useQuery({ queryKey: ['warehouses'], queryFn: listWarehouses });
  const [warehouse, setWarehouse] = useState('');
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

  const rows = useMemo(() => {
    const src = (query.data ?? []).filter((s) => !warehouse || String(s.warehouse) === warehouse);
    if (!warehouse) {
      const map = new Map<number | string, StockRow>();
      for (const s of src) {
        const key = s.product;
        const onHand = toNumber(s.onHand);
        const reserved = toNumber(s.reserved);
        const available = toNumber(s.available);
        const existing = map.get(key);
        if (!existing) {
          map.set(key, {
            ...s,
            warehouseLabel: 'All godowns',
            onHandNum: onHand,
            reservedNum: reserved,
            availableNum: available,
            nearestExpiryLabel: s.nearestExpiry ?? '—',
            lots: [
              {
                ...s,
                warehouseLabel: warehouseName.get(s.warehouse as never) ?? String(s.warehouse ?? '—'),
                onHandNum: onHand,
                reservedNum: reserved,
                availableNum: available,
                nearestExpiryLabel: s.nearestExpiry ?? '—',
                lotLabel: s.batchNo ? String(s.batchNo) : 'No lot',
              },
            ],
          });
        } else {
          existing.onHandNum += onHand;
          existing.reservedNum += reserved;
          existing.availableNum += available;
          existing.nearestExpiryLabel = earlierDate(existing.nearestExpiry, s.nearestExpiry) ?? existing.nearestExpiryLabel;
          existing.nearestExpiry = earlierDate(existing.nearestExpiry, s.nearestExpiry);
          existing.lots = [
            ...(existing.lots ?? []),
            {
              ...s,
              warehouseLabel: warehouseName.get(s.warehouse as never) ?? String(s.warehouse ?? '—'),
              onHandNum: onHand,
              reservedNum: reserved,
              availableNum: available,
              nearestExpiryLabel: s.nearestExpiry ?? '—',
              lotLabel: s.batchNo ? String(s.batchNo) : 'No lot',
            },
          ];
        }
      }
      return [...map.values()];
    }
    return src.map((s) => ({
      ...s,
      warehouseLabel: warehouseName.get(s.warehouse as never) ?? String(s.warehouse ?? '—'),
      onHandNum: toNumber(s.onHand),
      reservedNum: toNumber(s.reserved),
      availableNum: toNumber(s.available),
      nearestExpiryLabel: s.nearestExpiry ?? '—',
      lots: [] as StockRow[],
      lotLabel: s.batchNo ? String(s.batchNo) : 'No lot',
    })) as StockRow[];
  }, [query.data, warehouse, warehouseName]);

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1}>
        <Typography variant="h4">{t('nav.currentStock')}</Typography>
        <TextField
          size="small"
          placeholder={t('customFields.searchHint')}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          sx={{ minWidth: 220, flex: 1, maxWidth: 360 }}
        />
        {isItemCustomFieldsV2Enabled() ? (
          <ColumnPicker columns={columns} isVisible={prefs.isVisible} toggle={prefs.toggle} reset={prefs.reset} />
        ) : null}
      </Stack>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ sm: 'center' }} flexWrap="wrap" useFlexGap>
        <TextField
          select
          size="small"
          label={t('nav.warehouses')}
          value={warehouse}
          onChange={(e) => setWarehouse(e.target.value)}
          sx={{ maxWidth: 280 }}
        >
          <MenuItem value="">{t('common.all')} godowns</MenuItem>
          {(warehouses.data ?? []).map((item) => (
            <MenuItem key={item.id} value={String(item.id)}>
              {item.name}
            </MenuItem>
          ))}
        </TextField>
        <CustomFieldFilterBar defs={customDefs} value={cfFilters} onChange={setCfFilters} />
      </Stack>
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {query.data?.length === 0 ? <EmptyState description={t('empty.stock')} /> : null}
      {rows.length > 0 ? (
        <Paper sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                {prefs.isVisible('name') ? <TableCell>{t('common.name')}</TableCell> : null}
                {prefs.isVisible('sku') ? <TableCell>{t('common.sku')}</TableCell> : null}
                {visibleCustom.map((def) => (
                  <TableCell key={def.key}>{def.label}</TableCell>
                ))}
                {prefs.isVisible('warehouse') ? <TableCell>{t('nav.warehouses')}</TableCell> : null}
                {prefs.isVisible('expiry') ? <TableCell>Nearest expiry</TableCell> : null}
                {prefs.isVisible('onHand') ? <TableCell align="right">On Hand</TableCell> : null}
                {prefs.isVisible('reserved') ? (
                  <TableCell align="right">
                    <Tooltip title={t('billing.reservedStockHint')}>
                      <span style={{ cursor: 'help' }}>Reserved ℹ️</span>
                    </Tooltip>
                  </TableCell>
                ) : null}
                {prefs.isVisible('available') ? <TableCell align="right">Available</TableCell> : null}
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((s) => {
                const rowKey = `${s.warehouse ?? 'all'}-${s.product}`;
                const children = s.lots ?? [];
                const isOpen = Boolean(expanded[rowKey]);
                return (
                  <Fragment key={rowKey}>
                    <TableRow>
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
                          {children.length > 0 ? (
                            <Button
                              size="small"
                              onClick={() => setExpanded((current) => ({ ...current, [rowKey]: !isOpen }))}
                            >
                              {isOpen ? 'Hide lots' : 'Show lots'}
                            </Button>
                          ) : null}{' '}
                          {s.productName}
                        </TableCell>
                      ) : null}
                      {prefs.isVisible('sku') ? <TableCell>{s.sku}</TableCell> : null}
                      {visibleCustom.map((def) => (
                        <TableCell key={def.key}>{customFieldCell(s.customFields, def.key)}</TableCell>
                      ))}
                      {prefs.isVisible('warehouse') ? <TableCell>{s.warehouseLabel}</TableCell> : null}
                      {prefs.isVisible('expiry') ? <TableCell>{s.nearestExpiryLabel}</TableCell> : null}
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
                    {isOpen
                      ? children.map((lot: StockRow) => (
                          <TableRow key={`${rowKey}-${lot.id ?? lot.batchNo}-${lot.warehouse}`} sx={{ bgcolor: 'action.hover' }}>
                            {prefs.isVisible('name') ? <TableCell sx={{ pl: 6 }}>{lot.lotLabel}</TableCell> : null}
                            {prefs.isVisible('sku') ? <TableCell /> : null}
                            {visibleCustom.map((def) => (
                              <TableCell key={def.key} />
                            ))}
                            {prefs.isVisible('warehouse') ? <TableCell>{lot.warehouseLabel}</TableCell> : null}
                            {prefs.isVisible('expiry') ? <TableCell>{lot.nearestExpiryLabel}</TableCell> : null}
                            {prefs.isVisible('onHand') ? <TableCell align="right">{lot.onHandNum}</TableCell> : null}
                            {prefs.isVisible('reserved') ? <TableCell align="right">{lot.reservedNum}</TableCell> : null}
                            {prefs.isVisible('available') ? <TableCell align="right">{lot.availableNum}</TableCell> : null}
                          </TableRow>
                        ))
                      : null}
                  </Fragment>
                );
              })}
            </TableBody>
          </Table>
        </Paper>
      ) : null}
    </Stack>
  );
}
