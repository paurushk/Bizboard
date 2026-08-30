import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { exportReport, getInventorySummary } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';
import { canExport } from '@/utils/permissions';
import { formatMoney, toNumber } from '@/utils/money';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';

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

const COLUMNS: { key: keyof InventoryRow; label: string; align?: 'right'; money?: boolean }[] = [
  { key: 'product', label: 'Product' },
  { key: 'sku', label: 'SKU' },
  { key: 'warehouse', label: 'Godown' },
  { key: 'onHand', label: 'On hand', align: 'right' },
  { key: 'reserved', label: 'Reserved', align: 'right' },
  { key: 'available', label: 'Available', align: 'right' },
  { key: 'reorderLevel', label: 'Reorder', align: 'right' },
  { key: 'stockValue', label: 'Stock value', align: 'right', money: true },
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
        <Paper sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                {COLUMNS.map((col) => (
                  <TableCell key={col.key} align={col.align}>
                    {col.label}
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((row, idx) => (
                <TableRow key={idx}>
                  {COLUMNS.map((col) => {
                    const raw = row[col.key];
                    const display = col.money
                      ? formatMoney(toNumber(raw as string | number))
                      : String(raw ?? '—');
                    return (
                      <TableCell key={col.key} align={col.align}>
                        {display}
                      </TableCell>
                    );
                  })}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}
    </Stack>
  );
}
