import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { listStock } from '@/api/resources';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';
import { toNumber } from '@/utils/money';

export function CurrentStockPage() {
  const query = useQuery({ queryKey: ['stock'], queryFn: listStock });

  return (
    <Stack spacing={2}>
      <Typography variant="h4">{t('nav.currentStock')}</Typography>
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} onRetry={() => void query.refetch()} />
      ) : null}
      {query.data?.length === 0 ? <EmptyState description={t('empty.stock')} /> : null}
      {query.data && query.data.length > 0 ? (
        <Paper sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Product</TableCell>
                <TableCell>SKU</TableCell>
                <TableCell align="right">On hand</TableCell>
                <TableCell align="right">Reserved</TableCell>
                <TableCell align="right">Available</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {query.data.map((s) => (
                <TableRow key={s.product}>
                  <TableCell>{s.productName}</TableCell>
                  <TableCell>{s.sku}</TableCell>
                  <TableCell align="right">{toNumber(s.onHand)}</TableCell>
                  <TableCell align="right">{toNumber(s.reserved)}</TableCell>
                  <TableCell align="right">{toNumber(s.available)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}
    </Stack>
  );
}
