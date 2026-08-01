import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { exportReport, getPurchaseRegister } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';
import { formatMoney } from '@/utils/money';
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

export function PurchaseReportPage() {
  const { user } = useAuth();
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const query = useQuery({
    queryKey: ['purchase-register', dateFrom, dateTo],
    queryFn: () =>
      getPurchaseRegister({ dateFrom: dateFrom || undefined, dateTo: dateTo || undefined }),
  });

  const exportMutation = useMutation({
    mutationFn: () =>
      exportReport('purchases', { dateFrom: dateFrom || undefined, dateTo: dateTo || undefined }),
    onSuccess: (r) => downloadBlobUrl(r.url, 'purchase-register.csv'),
  });

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1}>
        <Typography variant="h4">{t('nav.purchaseReports')}</Typography>
        <Stack direction="row" spacing={1} alignItems="center">
          <TextField
            type="date"
            size="small"
            label={t('common.dateFrom')}
            InputLabelProps={{ shrink: true }}
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
          />
          <TextField
            type="date"
            size="small"
            label={t('common.dateTo')}
            InputLabelProps={{ shrink: true }}
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
          />
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
                    <TableCell key={key}>
                      {typeof value === 'number' ||
                      (typeof value === 'string' && /total|amount|tax/i.test(key))
                        ? formatMoney(value as string | number)
                        : String(value ?? '—')}
                    </TableCell>
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
