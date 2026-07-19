import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import Button from '@mui/material/Button';
import { useQuery } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { listPurchases } from '@/api/resources';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { StatusChip } from '@/components/StatusChip';
import { t } from '@/i18n';
import { formatMoney } from '@/utils/money';
import { documentStatusTone, statusLabelKey } from '@/utils/status';

export function PurchaseHistoryPage() {
  const query = useQuery({ queryKey: ['purchases'], queryFn: listPurchases });

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="h4">{t('nav.purchaseHistory')}</Typography>
        <Button component={RouterLink} to="/purchases/new" variant="contained">
          {t('nav.newPurchase')}
        </Button>
      </Stack>
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={query.error.message} onRetry={() => void query.refetch()} />
      ) : null}
      {query.data?.length === 0 ? <EmptyState /> : null}
      {query.data && query.data.length > 0 ? (
        <Paper sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('common.number')}</TableCell>
                <TableCell>{t('common.date')}</TableCell>
                <TableCell>{t('billing.supplier')}</TableCell>
                <TableCell>{t('common.status')}</TableCell>
                <TableCell align="right">{t('common.total')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {query.data.map((p) => (
                <TableRow key={p.id}>
                  <TableCell>{p.number ?? p.id}</TableCell>
                  <TableCell>{p.invoiceDate}</TableCell>
                  <TableCell>{p.supplierName}</TableCell>
                  <TableCell>
                    <StatusChip
                      tone={documentStatusTone(p.status)}
                      labelKey={statusLabelKey(p.status)}
                    />
                  </TableCell>
                  <TableCell align="right">{formatMoney(p.grandTotal)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}
    </Stack>
  );
}
