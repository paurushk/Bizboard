import { useMemo, useState } from 'react';
import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { getDemandForecast, type ForecastRow, type OverstockRow } from '@/api/osPlan';
import TextField from '@mui/material/TextField';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { ChipTabs, chipPanelId, chipTabId } from '@/components/ChipTabs';
import { PageTitle } from '@/contextHelp';
import { t, useLocale } from '@/i18n';
import { enumLabel } from '@/utils/enumLabels';

/** The order link: the quantity the server worked out (stock and open orders already taken off). */
function planHref(row: ForecastRow): string {
  const suggested = Number(row.suggestedQty);
  // An older response without a suggestion falls back to a month of sales.
  const qty = Number.isFinite(suggested) && row.suggestedQty !== undefined
    ? suggested
    : Math.max(1, Math.ceil(Number(row.dailyRate || 0) * 30));
  const params = new URLSearchParams({ product: String(row.productId), qty: String(Math.max(qty, 1)) });
  if (row.supplierId) params.set('supplier', String(row.supplierId));
  return `/purchases/orders/new?${params.toString()}`;
}

/** The rows on screen as a spreadsheet file (the forecast, or the overstock list). */
function downloadForecastCsv(rows: ForecastRow[] | null, overstock: OverstockRow[]) {
  const cell = (value: unknown) => `"${String(value ?? '').replace(/"/g, '""')}"`;
  const lines = rows
    ? [
        ['Product', 'Sold', 'Per day', 'Available', 'On order', 'Days of cover', 'Suggested', 'Supplier'],
        ...rows.map((r) => [r.productName, r.soldQty, r.dailyRate, r.available, r.onOrder, r.daysOfCover, r.suggestedQty, r.supplierName]),
      ]
    : [
        ['Product', 'Available', 'Per day', 'Days of cover'],
        ...overstock.map((r) => [r.productName, r.available, r.noSales ? '' : r.dailyRate, r.noSales ? 'no sales' : r.daysOfCover]),
      ];
  const blob = new Blob([lines.map((line) => line.map(cell).join(',')).join('\n')], { type: 'text/csv' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = rows ? 'demand-forecast.csv' : 'overstock.csv';
  document.body.appendChild(a);
  a.click();
  a.remove();
}

export function DemandForecastPage() {
  useLocale();
  const forecast = useQuery({ queryKey: ['demand-forecast'], queryFn: getDemandForecast });
  const allRows = useMemo(() => forecast.data?.rows ?? [], [forecast.data]);
  const needing = useMemo(() => allRows.filter((row) => row.needsAction !== false), [allRows]);
  const overstock = useMemo(() => forecast.data?.overstock ?? [], [forecast.data]);
  const [tab, setTab] = useState<'needs' | 'all' | 'overstock'>('needs');
  const [search, setSearch] = useState('');
  const needle = search.trim().toLowerCase();
  const matches = (name: string) => !needle || name.toLowerCase().includes(needle);
  const rows = (tab === 'needs' ? needing : allRows).filter((row) => matches(row.productName));
  const idleRows = overstock.filter((row) => matches(row.productName));
  return (
    <div>
      <PageTitle>{t('nav.demandForecast')}</PageTitle>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>{t('osPlan.forecastHelp')}</Typography>
      <Button component={RouterLink} to="/inventory/purchase-planning" size="small" sx={{ mb: 2 }}>
        {t('osPlan.openPlanning')}
      </Button>
      {forecast.isLoading ? <LoadingState /> : null}
      {forecast.isError ? (
        <ErrorState message={getErrorMessage(forecast.error)} error={forecast.error} onRetry={() => void forecast.refetch()} />
      ) : null}
      {!forecast.isLoading && !forecast.isError && allRows.length === 0 ? (
        <EmptyState description={t('osPlan.forecastEmpty')} />
      ) : null}
      {allRows.length > 0 || overstock.length > 0 ? (
        <Stack direction="row" spacing={1} sx={{ mb: 1 }} alignItems="center" flexWrap="wrap" useFlexGap>
          <ChipTabs
            idPrefix="forecast"
            label={t('nav.demandForecast')}
            value={tab}
            onChange={setTab}
            tabs={[
              { value: 'needs', label: t('inventory.forecastTabNeeds', { count: String(needing.length) }) },
              { value: 'all', label: t('inventory.forecastTabAll', { count: String(allRows.length) }) },
              { value: 'overstock', label: t('inventory.forecastTabOverstock', { count: String(overstock.length) }) },
            ]}
          />
          <TextField
            size="small"
            label={t('inventory.forecastSearch')}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            sx={{ minWidth: 220 }}
          />
          <Button size="small" variant="outlined" onClick={() => downloadForecastCsv(tab === 'overstock' ? null : rows, idleRows)}>
            {t('inventory.downloadCsv')}
          </Button>
        </Stack>
      ) : null}
      <div role="tabpanel" id={chipPanelId('forecast')} aria-labelledby={chipTabId('forecast', tab)}>
      {tab !== 'overstock' && allRows.length > 0 && rows.length === 0 ? <EmptyState description={t('inventory.forecastNothingNeeded')} /> : null}
      {tab === 'overstock' ? (
        idleRows.length === 0 ? (
          <EmptyState description={t('inventory.forecastNoOverstock')} />
        ) : (
          <Paper variant="outlined" tabIndex={0} role="region" aria-label={t('common.scrollableTable')} sx={{ overflow: 'auto' }}>
            <Typography variant="body2" color="text.secondary" sx={{ p: 1.5 }}>
              {t('inventory.forecastOverstockHelp')}
            </Typography>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>{t('common.product')}</TableCell>
                  <TableCell align="right">{t('inventory.forecastColAvailable')}</TableCell>
                  <TableCell align="right">{t('osPlan.dailyRate')}</TableCell>
                  <TableCell align="right">{t('inventory.forecastColCover')}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {idleRows.map((row) => (
                  <TableRow key={row.productId}>
                    <TableCell>{row.productName}</TableCell>
                    <TableCell align="right">{row.available}{row.unit ? ` ${row.unit}` : ''}</TableCell>
                    <TableCell align="right">{row.noSales ? '—' : row.dailyRate}</TableCell>
                    <TableCell align="right">
                      {row.noSales ? t('inventory.forecastNoSales', { days: String(row.lookbackDays) }) : row.daysOfCover}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Paper>
        )
      ) : null}
      {tab !== 'overstock' && rows.length > 0 ? (
        <Paper variant="outlined" tabIndex={0} role="region" aria-label={t('common.scrollableTable')} sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('common.product')}</TableCell>
                <TableCell align="right">{t('osPlan.soldQty')}</TableCell>
                <TableCell align="right">{t('osPlan.dailyRate')}</TableCell>
                <TableCell align="right">{t('inventory.forecastColAvailable')}</TableCell>
                <TableCell align="right">{t('inventory.forecastColOnOrder')}</TableCell>
                <TableCell align="right">{t('inventory.forecastColCover')}</TableCell>
                <TableCell align="right">{t('inventory.forecastColSuggested')}</TableCell>
                <TableCell>{t('inventory.forecastColSupplier')}</TableCell>
                <TableCell>{t('osPlan.method')}</TableCell>
                <TableCell align="right">{t('common.actions')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.productId}>
                  <TableCell>{row.productName}</TableCell>
                  <TableCell align="right">{row.soldQty}</TableCell>
                  <TableCell align="right">{row.dailyRate}</TableCell>
                  <TableCell align="right">{row.available ?? '—'}</TableCell>
                  <TableCell align="right">{row.onOrder && Number(row.onOrder) > 0 ? row.onOrder : '—'}</TableCell>
                  <TableCell align="right">{row.daysOfCover ?? '—'}</TableCell>
                  <TableCell align="right">
                    {row.suggestedQty !== undefined && Number(row.suggestedQty) > 0 ? `${Number(row.suggestedQty)}${row.unit ? ` ${row.unit}` : ''}` : '—'}
                  </TableCell>
                  <TableCell>{row.supplierName || '—'}</TableCell>
                  <TableCell>
                    {enumLabel('forecastMethod', row.method)}
                    {row.method === 'in_stock_days_mean' && row.inStockDays != null
                      ? ` · ${t('inventory.forecastInStock', { days: String(row.inStockDays), window: String(row.windowDays) })}`
                      : row.windowDays != null
                        ? ` · ${row.windowDays}`
                        : ''}
                  </TableCell>
                  <TableCell align="right">
                    <Button
                      size="small"
                      component={RouterLink}
                      aria-label={t('osPlan.planPurchaseFor', { name: row.productName })}
                      to={planHref(row)}
                    >
                      {t('osPlan.planPurchase')}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}
      </div>
    </div>
  );
}
