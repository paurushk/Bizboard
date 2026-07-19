import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { listLowStock } from '@/api/resources';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { StatusChip } from '@/components/StatusChip';
import { t } from '@/i18n';
import { toNumber } from '@/utils/money';

export function LowStockPage() {
  const query = useQuery({ queryKey: ['low-stock'], queryFn: listLowStock });

  return (
    <Stack spacing={2}>
      <Typography variant="h4">{t('nav.lowStock')}</Typography>
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={query.error.message} onRetry={() => void query.refetch()} />
      ) : null}
      {query.data?.length === 0 ? <EmptyState description="No low-stock alerts" /> : null}
      {query.data && query.data.length > 0 ? (
        <Paper sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Product</TableCell>
                <TableCell>SKU</TableCell>
                <TableCell align="right">Available</TableCell>
                <TableCell align="right">Reorder</TableCell>
                <TableCell>Alert</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {query.data.map((s) => (
                <TableRow key={s.product}>
                  <TableCell>{s.productName}</TableCell>
                  <TableCell>{s.sku}</TableCell>
                  <TableCell align="right">{toNumber(s.available)}</TableCell>
                  <TableCell align="right">{toNumber(s.reorderLevel)}</TableCell>
                  <TableCell>
                    <StatusChip tone="warning" label="Below reorder" />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}
    </Stack>
  );
}
