import Paper from '@mui/material/Paper';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import Stack from '@mui/material/Stack';
import { useQuery } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { listCollectionsWorklist } from '@/api/osPlan';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { PageTitle } from '@/contextHelp';
import { t } from '@/i18n';
import { formatMoney } from '@/utils/money';

export function CollectionsWorklistPage() {
  const query = useQuery({ queryKey: ['collections-worklist'], queryFn: listCollectionsWorklist });
  return (
    <Stack spacing={2}>
      <PageTitle>{t('nav.collections')}</PageTitle>
      <Typography variant="body2" color="text.secondary">{t('osPlan.collectionsHelp')}</Typography>
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {!query.isLoading && !query.isError && (query.data?.length ?? 0) === 0 ? (
        <EmptyState description={t('osPlan.collectionsEmpty')} />
      ) : null}
      {(query.data?.length ?? 0) > 0 ? (
        <Paper variant="outlined" sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('billing.customer')}</TableCell>
                <TableCell>{t('common.number')}</TableCell>
                <TableCell>{t('osPlan.dueDate')}</TableCell>
                <TableCell align="right">{t('portal.outstanding')}</TableCell>
                <TableCell align="right">{t('osPlan.predictedLate')}</TableCell>
                <TableCell>{t('osPlan.confidence')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {query.data!.map((row) => (
                <TableRow key={row.invoiceId}>
                  <TableCell>{row.customerName}</TableCell>
                  <TableCell>{row.invoiceNumber}</TableCell>
                  <TableCell>{row.dueDate}</TableCell>
                  <TableCell align="right">{formatMoney(row.outstanding)}</TableCell>
                  <TableCell align="right">
                    {row.predictedDaysLate == null ? '—' : t('osPlan.daysLate', { count: row.predictedDaysLate })}
                  </TableCell>
                  <TableCell>{row.confident ? t('osPlan.confident') : t('osPlan.notEnoughHistory')}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}
    </Stack>
  );
}
