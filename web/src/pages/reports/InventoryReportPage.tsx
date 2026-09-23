import { useMemo, useState } from 'react';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Stack from '@mui/material/Stack';
import Tooltip from '@mui/material/Tooltip';
import { useMutation, useQuery } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { exportReport, getInventorySummary } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import {
  EMPTY_HISTORY_FILTERS,
  HistoryFilterBar,
  type HistoryFilters,
} from '@/components/HistoryFilterBar';
import { PageTitle } from '@/contextHelp';
import { t } from '@/i18n';
import { canExport } from '@/utils/permissions';
import { formatMoney, toNumber } from '@/utils/money';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { DataTable } from '@/pages/phase/phaseShared';

function downloadBlobUrl(url: string, filename: string) {
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

type InventoryRow = {
  product?: string;
  sku?: string;
  warehouse?: string;
  warehouseId?: number;
  onHand?: string | number;
  reserved?: string | number;
  available?: string | number;
  reorderLevel?: string | number;
  stockValue?: string | number;
  balanceDrift?: boolean;
  reservedDrift?: boolean;
  balanceOnHand?: string | number;
  status?: string;
};

const COLUMNS: {
  key: keyof InventoryRow;
  label: string;
  money?: boolean;
  render?: (row: Record<string, unknown>) => React.ReactNode;
}[] = [
  { key: 'product', label: 'Product' },
  { key: 'sku', label: 'SKU' },
  { key: 'warehouse', label: 'Godown' },
  { key: 'onHand', label: 'On hand' },
  { key: 'reserved', label: 'Reserved' },
  { key: 'available', label: 'Available' },
  { key: 'reorderLevel', label: 'Reorder' },
  { key: 'stockValue', label: 'Stock value', money: true },
  {
    key: 'status',
    label: 'Status',
    render: (row) => {
      const bDrift = Boolean(row.balanceDrift);
      const rDrift = Boolean(row.reservedDrift);
      if (!bDrift && !rDrift) {
        return <Chip size="small" label="Healthy" color="success" variant="outlined" />;
      }
      return (
        <Stack direction="row" spacing={0.5}>
          {bDrift ? (
            <Tooltip title={`Cache drift: StockBalance has ${String(row.balanceOnHand ?? 'unknown')}`}>
              <Chip size="small" label="Balance Drift" color="warning" />
            </Tooltip>
          ) : null}
          {rDrift ? (
            <Tooltip title="Reserved quantity exceeds physical stock or is negative">
              <Chip size="small" label="Reserved Drift" color="error" />
            </Tooltip>
          ) : null}
        </Stack>
      );
    },
  },
];

export function InventoryReportPage() {
  const { user } = useAuth();
  const [filters, setFilters] = useState<HistoryFilters>(EMPTY_HISTORY_FILTERS);
  const query = useQuery({ queryKey: ['inventory-summary'], queryFn: getInventorySummary });
  const exportMutation = useMutation({
    mutationFn: () => exportReport('inventory'),
    onSuccess: (r) => downloadBlobUrl(r.url, 'inventory-summary.csv'),
  });

  const rows = useMemo(() => {
    const mapped = ((query.data?.rows ?? []) as Record<string, unknown>[]).map((r) => ({
      product: String(r.product ?? r.productName ?? r.product_name ?? '—'),
      sku: String(r.sku ?? '—'),
      warehouse: String(r.warehouse ?? r.warehouseName ?? r.warehouse_name ?? '—'),
      onHand: (r.onHand ?? r.on_hand) as string | number,
      reserved: (r.reserved) as string | number,
      available: (r.available) as string | number,
      reorderLevel: (r.reorderLevel ?? r.reorder_level) as string | number,
      stockValue: (r.stockValue ?? r.stock_value) as string | number,
      balanceDrift: Boolean(r.balanceDrift ?? r.balance_drift),
      reservedDrift: Boolean(r.reservedDrift ?? r.reserved_drift),
      balanceOnHand: (r.balanceOnHand ?? r.balance_on_hand) as string | number,
    })) as InventoryRow[];
    const q = filters.q.trim().toLowerCase();
    if (!q) return mapped;
    return mapped.filter(
      (row) =>
        (row.product ?? '').toLowerCase().includes(q) ||
        (row.sku ?? '').toLowerCase().includes(q) ||
        String(row.warehouse ?? '').toLowerCase().includes(q),
    );
  }, [query.data?.rows, filters.q]);

  const kpis = useMemo(() => {
    let qty = 0;
    let value = 0;
    for (const row of rows) {
      qty += toNumber(row.onHand);
      value += toNumber(row.stockValue);
    }
    return { qty, value };
  }, [rows]);

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1}>
        <PageTitle>{t('nav.inventoryReports')}</PageTitle>
        <Stack direction="row" spacing={1}>
          {canExport(user) ? (
            <Button
              variant="outlined"
              disabled={exportMutation.isPending}
              onClick={() => exportMutation.mutate()}
            >
              {t('common.download')}
            </Button>
          ) : null}
          <Button
            variant="outlined"
            onClick={() => {
              const url = exportMutation.data?.url;
              if (url) {
                window.location.href = `mailto:?subject=${encodeURIComponent('Inventory')}&body=${encodeURIComponent(url)}`;
              } else {
                exportMutation.mutate();
              }
            }}
          >
            {t('reports.emailExcel')}
          </Button>
          <Button variant="outlined" onClick={() => window.print()}>
            {t('common.print')}
          </Button>
        </Stack>
      </Stack>
      <HistoryFilterBar value={filters} onChange={setFilters} showDateRange={false} />
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
        <Chip label={`${t('reports.stockQty')}: ${kpis.qty}`} />
        <Chip label={`${t('reports.stockValue')}: ${formatMoney(kpis.value)}`} />
      </Stack>
      {exportMutation.isError ? (
        <HelpErrorAlert error={exportMutation.error} />
      ) : null}
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {query.data?.rows?.length === 0 ? <EmptyState description={t('empty.reports')} /> : null}
      {rows.length > 0 ? (
        // F3-017: one row per product/warehouse company-wide — window the
        // DOM rows via phaseShared.DataTable's virtualized mode.
        <DataTable rows={rows} columns={COLUMNS} empty={t('empty.reports')} virtualized />
      ) : null}
    </Stack>
  );
}
