import { useMemo, useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import LinearProgress from '@mui/material/LinearProgress';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import * as api from '@/api/resources';
import { ErrorState, LoadingState } from '@/components/PageState';
import { HonestyBanner } from '@/components/HonestyBanner';
import { t } from '@/i18n';
import { asRows, DataTable, PageShell, type Row } from '@/pages/phase/phaseShared';
import { buildValuationCsv, normalizeValuationRow } from '@/pages/reports/valuationHelpers';
import { formatMoney, toNumber } from '@/utils/money';
import { useAuth } from '@/auth/AuthContext';
import { canExport } from '@/utils/permissions';

export function StockValuationPage() {
  const { user } = useAuth();
  const [basis, setBasis] = useState('cost');
  const [asOf, setAsOf] = useState('');
  const [warehouse, setWarehouse] = useState('');
  const warehouses = useQuery({ queryKey: ['warehouses'], queryFn: api.listWarehouses });
  const q = useQuery({
    // RPT-05: keep the last valuation and the filter controls on screen while a new one loads.
    placeholderData: keepPreviousData,
    queryKey: ['stock-valuation', basis, asOf, warehouse],
    queryFn: () =>
      api.getStockValuation({
        ...(basis === 'cost' ? {} : { basis }),
        ...(asOf ? { as_of: asOf } : {}),
        ...(warehouse ? { warehouse } : {}),
      }),
  });
  const failed = q.isError;
  const ready = Boolean(q.data) && !failed;
  const data = (ready ? q.data : {}) as Row;
  const items = useMemo(() => asRows(data.items as Row[]).map(normalizeValuationRow), [data.items]);

  const isCost = basis === 'cost';
  const basisLabel =
    basis === 'purchase' ? t('reportLabels.basisPurchase')
      : basis === 'selling' ? t('reportLabels.basisSelling')
        : basis === 'mrp' ? t('reportLabels.basisMrp')
          : t('reportLabels.basisCost');
  const totalValue = items.reduce((sum, r) => sum + toNumber(r.value as string | number | null | undefined), 0);
  const hasComparison = data.booksVariance !== undefined && data.booksVariance !== null;
  const variance = toNumber(data.booksVariance as string | number | undefined);
  const download = () => {
    const blob = new Blob([buildValuationCsv(items, isCost)], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'stock-valuation.csv';
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10_000);
  };

  return (
    <PageShell
      title={t('phase.stockValuation')}
      subtitle={
        isCost
          ? (String(data.method || 'WAVG').toUpperCase().includes('FIFO')
            ? t('stockValuation.methodFifo')
            : t('stockValuation.methodWavg'))
          : t('reportLabels.valuedAtPrice', { basis: basisLabel })
      }
      actions={
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems={{ sm: 'center' }} flexWrap="wrap" useFlexGap>
          <Paper variant="outlined" sx={{ px: 2, py: 1 }}>
            <Typography variant="caption" color="text.secondary" display="block">
              {t('sweep2.totalStockValue')}
            </Typography>
            <Typography variant="h6" sx={{ fontWeight: 700 }}>
              {formatMoney(totalValue)}
            </Typography>
          </Paper>
          <TextField
            select
            size="small"
            label={t('sweep.valueStockAt')}
            value={basis}
            onChange={(e) => setBasis(e.target.value)}
            sx={{ minWidth: 200 }}
          >
            <MenuItem value="cost">{t('sweep2.costWavgFifo')}</MenuItem>
            <MenuItem value="purchase">{t('sweep2.purchasePrice')}</MenuItem>
            <MenuItem value="selling">{t('sweep2.sellingPriceText')}</MenuItem>
            <MenuItem value="mrp">MRP</MenuItem>
          </TextField>
          <TextField
            size="small"
            type="date"
            label={t('inventory.valuationAsOf')}
            value={asOf}
            onChange={(e) => setAsOf(e.target.value)}
            InputLabelProps={{ shrink: true }}
          />
          <TextField
            select
            size="small"
            label={t('sweep.godown')}
            value={warehouse}
            onChange={(e) => setWarehouse(e.target.value)}
            sx={{ minWidth: 170 }}
          >
            <MenuItem value="">{t('sweep2.allGodowns')}</MenuItem>
            {(warehouses.data ?? []).map((w) => (
              <MenuItem key={w.id} value={String(w.id)}>{w.name}</MenuItem>
            ))}
          </TextField>
          {canExport(user) ? (
            <Button variant="outlined" size="small" onClick={download} disabled={items.length === 0}>
              {t('inventory.downloadCsv')}
            </Button>
          ) : null}
        </Stack>
      }
    >
      {q.isFetching ? <LinearProgress aria-label={t('common.loading')} /> : null}
      {q.isLoading ? <LoadingState /> : null}
      {failed ? (
        <ErrorState message={getErrorMessage(q.error)} error={q.error} onRetry={() => void q.refetch()} />
      ) : null}
      <HonestyBanner
        messageKey="honesty.valuationMethod"
        vars={{ method: String(data.method || 'WAVG') }}
      />
      {!isCost ? <Alert severity="info">{t('inventory.valuationNotForAccounts')}</Alert> : null}
      {ready ? (
        <>
      {hasComparison ? (
        variance === 0 ? (
          <Alert severity="success">
            {t('inventory.valuationMatchesBooks', { amount: formatMoney(toNumber(data.inventoryInBooks as string | number)) })}
          </Alert>
        ) : (
          <Alert severity="warning">
            {t('inventory.valuationBooksDiffer', {
              stock: formatMoney(toNumber(data.stockValue as string | number)),
              books: formatMoney(toNumber(data.inventoryInBooks as string | number)),
              gap: formatMoney(Math.abs(variance)),
            })}{' '}
            {data.stockWritesPosted ? t('inventory.valuationRunBackfill') : t('inventory.valuationTurnOnPosting')}
          </Alert>
        )
      ) : null}
      <DataTable
        rows={items}
        empty={t('reportLabels.noValuationRows')}
        // F3-016: one row per product/batch across the whole company —
        // window the DOM rows instead of rendering them all at once.
        virtualized
        columns={[
          { key: 'productName', label: t('reportLabels.product') },
          { key: 'warehouseName', label: t('reportLabels.godown') },
          { key: 'quantity', label: t('reportLabels.qty') },
          { key: 'unitCost', label: isCost ? t('reportLabels.unitCost') : t('inventory.valuationUnitPrice'), money: true },
          { key: 'value', label: t('reportLabels.value'), money: true },
        ]}
      />
        </>
      ) : null}
    </PageShell>
  );
}
