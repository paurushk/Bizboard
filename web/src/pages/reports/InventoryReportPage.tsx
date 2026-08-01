import Alert from '@mui/material/Alert';
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

function downloadBlobUrl(url: string, filename: string) {
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

export function InventoryReportPage() {
  const { user } = useAuth();
  const query = useQuery({ queryKey: ['inventory-summary'], queryFn: getInventorySummary });
  const exportMutation = useMutation({
    mutationFn: () => exportReport('inventory'),
    onSuccess: (r) => downloadBlobUrl(r.url, 'inventory-summary.csv'),
  });

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
        <Alert severity="error">{getErrorMessage(exportMutation.error)}</Alert>
      ) : null}
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} onRetry={() => void query.refetch()} />
      ) : null}
      {query.data?.rows?.length === 0 ? <EmptyState description={t('empty.reports')} /> : null}
      {query.data && query.data.rows.length > 0 ? (
        <Paper sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                {Object.keys(query.data.rows[0]).map((key) => (
                  <TableCell key={key}>{key}</TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {query.data.rows.map((row, idx) => (
                <TableRow key={idx}>
                  {Object.entries(row).map(([key, value]) => (
                    <TableCell key={key}>{String(value ?? '—')}</TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}
    </Stack>
  );
}
