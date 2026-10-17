import { useMemo, useState } from 'react';
import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { listLowStock } from '@/api/resources';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { StatusChip } from '@/components/StatusChip';
import { PageTitle } from '@/contextHelp';
import { useAuth } from '@/auth/AuthContext';
import { ChipTabs, chipPanelId, chipTabId } from '@/components/ChipTabs';
import { GodownReorderRules } from '@/pages/inventory/GodownReorderRules';
import { t, useLocale } from '@/i18n';
import {
  matchesSearch,
  reorderHref,
  shortfall,
  sortByShortfall,
  suggestedOrderQty,
} from '@/pages/inventory/lowStockHelpers';
import { toNumber } from '@/utils/money';
import { canAdjustInventory } from '@/utils/permissions';

export function LowStockPage() {
  useLocale();
  const { user } = useAuth();
  // One request fills both tabs: rows with a reorder rule are "low", rows without are "out of stock".
  const query = useQuery({ queryKey: ['low-stock', 'all'], queryFn: () => listLowStock('all') });
  const [search, setSearch] = useState('');
  const [tab, setTab] = useState<'low' | 'out'>('low');
  const lowRows = useMemo(() => (query.data ?? []).filter((row) => row.hasReorderRule !== false), [query.data]);
  const outRows = useMemo(() => (query.data ?? []).filter((row) => row.hasReorderRule === false), [query.data]);
  const tabRows = tab === 'low' ? lowRows : outRows;
  const rows = useMemo(
    () => sortByShortfall(tabRows.filter((row) => matchesSearch(row, search))),
    [tabRows, search],
  );

  return (
    <Stack spacing={2}>
      <PageTitle>{t('nav.lowStock')}</PageTitle>
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {query.data?.length === 0 ? <EmptyState description={t('products.wellStocked')} /> : null}
      {query.data && query.data.length > 0 ? (
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ sm: 'center' }}>
          <ChipTabs
            idPrefix="lowstock"
            label={t('nav.lowStock')}
            value={tab}
            onChange={setTab}
            tabs={[
              { value: 'low', label: t('inventory.lowStockTabLow', { count: String(lowRows.length) }) },
              { value: 'out', label: t('inventory.lowStockTabOut', { count: String(outRows.length) }) },
            ]}
          />
          <TextField
            size="small"
            label={t('inventory.lowStockSearch')}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            sx={{ maxWidth: 320 }}
          />
          <Button variant="contained" component={RouterLink} to="/inventory/purchase-planning?select=all">
            {t('inventory.lowStockPlanPurchases')}
          </Button>
        </Stack>
      ) : null}
      {query.data && query.data.length > 0 ? (
        <Stack spacing={2} role="tabpanel" id={chipPanelId('lowstock')} aria-labelledby={chipTabId('lowstock', tab)}>
      {tab === 'out' && query.data && query.data.length > 0 ? (
        <Typography variant="body2" color="text.secondary">
          {t('inventory.lowStockOutHelp')}
        </Typography>
      ) : null}
      {query.data && query.data.length > 0 && tabRows.length === 0 ? (
        <EmptyState description={tab === 'low' ? t('products.wellStocked') : t('inventory.lowStockOutEmpty')} />
      ) : null}
      {tabRows.length > 0 && rows.length === 0 ? (
        <EmptyState description={t('inventory.lowStockNoMatch')} />
      ) : null}
      {rows.length > 0 ? (
        <Paper tabIndex={0} role="region" aria-label={t('common.scrollableTable')} sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('common.name')}</TableCell>
                <TableCell>{t('common.sku')}</TableCell>
                <TableCell>{t('items.godown')}</TableCell>
                <TableCell align="right">{t('products.available')}</TableCell>
                <TableCell align="right">{t('products.reorderLevel')}</TableCell>
                <TableCell align="right">{t('inventory.lowStockShortBy')}</TableCell>
                <TableCell>{t('products.status')}</TableCell>
                <TableCell align="right">{t('common.actions')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((s, i) => (
                // F3-039: low-stock rows can be per (product, warehouse) — a
                // bare product id is not unique.
                <TableRow key={`${s.product}-${s.warehouse ?? 'all'}-${i}`}>
                  <TableCell>{s.productName}</TableCell>
                  <TableCell>{s.sku}</TableCell>
                  {/* A company-wide row's `warehouse` is just one godown that holds the item. */}
                  <TableCell>
                    {s.isWarehouseSpecific === false ? t('sweep2.allGodowns') : (s.warehouseName ?? '—')}
                  </TableCell>
                  <TableCell align="right" sx={{ color: 'error.main', fontWeight: 600 }}>
                    {toNumber(s.available)}
                  </TableCell>
                  <TableCell align="right">{toNumber(s.reorderLevel)}</TableCell>
                  <TableCell align="right">{shortfall(s)}</TableCell>
                  <TableCell>
                    {s.hasReorderRule === false ? (
                      <StatusChip tone="error" label={t('inventory.lowStockNoRuleChip')} />
                    ) : (
                      <StatusChip tone="warning" label={t('products.atOrBelowReorder')} />
                    )}
                  </TableCell>
                  <TableCell align="right">
                    <Button
                      component={RouterLink}
                      to={reorderHref(s)}
                      size="small"
                      variant="outlined"
                      aria-label={t('inventory.lowStockOrderLabel', {
                        qty: String(suggestedOrderQty(s)),
                        name: String(s.productName),
                      })}
                    >
                      {t('billing.reorderItem')}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}
        </Stack>
      ) : null}
      {canAdjustInventory(user) ? <GodownReorderRules /> : null}
    </Stack>
  );
}
