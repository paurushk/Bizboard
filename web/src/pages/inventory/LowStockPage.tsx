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
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {query.data?.length === 0 ? <EmptyState description="All items are well stocked above reorder levels." /> : null}
      {query.data && query.data.length > 0 ? (
        <Paper sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('common.name')}</TableCell>
                <TableCell>{t('common.sku')}</TableCell>
                <TableCell align="right">Available</TableCell>
                <TableCell align="right">Reorder Level</TableCell>
                <TableCell>Status</TableCell>
                <TableCell align="right">{t('common.actions')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {query.data.map((s, i) => (
                // F3-039: low-stock rows can be per (product, warehouse) — a
                // bare product id is not unique.
                <TableRow key={`${s.product}-${s.warehouse ?? 'all'}-${i}`}>
                  <TableCell>{s.productName}</TableCell>
                  <TableCell>{s.sku}</TableCell>
                  <TableCell align="right" sx={{ color: 'error.main', fontWeight: 600 }}>
                    {toNumber(s.available)}
                  </TableCell>
                  <TableCell align="right">{toNumber(s.reorderLevel)}</TableCell>
                  <TableCell>
                    <StatusChip tone="warning" label="Below reorder" />
                  </TableCell>
                  <TableCell align="right">
                    <Button
                      component={RouterLink}
                      to={`/purchases/new?productId=${s.product}`}
                      size="small"
                      variant="outlined"
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
  );
}
