import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { exportReport, getInventorySummary } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';
import { canExport } from '@/utils/permissions';
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
};

const COLUMNS: { key: keyof InventoryRow; label: string; money?: boolean }[] = [
  { key: 'product', label: 'Product' },
  { key: 'sku', label: 'SKU' },
  { key: 'warehouse', label: 'Godown' },
  { key: 'onHand', label: 'On hand' },
  { key: 'reserved', label: 'Reserved' },
  { key: 'available', label: 'Available' },
  { key: 'reorderLevel', label: 'Reorder' },
  { key: 'stockValue', label: 'Stock value', money: true },
];

export function InventoryReportPage() {
  const { user } = useAuth();
  const query = useQuery({ queryKey: ['inventory-summary'], queryFn: getInventorySummary });
  const exportMutation = useMutation({
    mutationFn: () => exportReport('inventory'),
    onSuccess: (r) => downloadBlobUrl(r.url, 'inventory-summary.csv'),
  });

  const rows = ((query.data?.rows ?? []) as Record<string, unknown>[]).map((r) => ({
    product: String(r.product ?? r.productName ?? r.product_name ?? '—'),
    sku: String(r.sku ?? '—'),
    warehouse: String(r.warehouse ?? r.warehouseName ?? r.warehouse_name ?? '—'),
    onHand: (r.onHand ?? r.on_hand) as string | number,
    reserved: (r.reserved) as string | number,
    available: (r.available) as string | number,
    reorderLevel: (r.reorderLevel ?? r.reorder_level) as string | number,
    stockValue: (r.stockValue ?? r.stock_value) as string | number,
  })) as InventoryRow[];

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="h4">{t('nav.inventoryReports')}</Typography>
        {canExport(user) ? (
          <Button
            variant="outlined"
            disabled={exportMutation.isPending}
            onClick={() => exportMutation.mutate()}
          >
            {t('common.export')}
          </Button>
        ) : null}
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
