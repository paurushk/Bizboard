import { useState } from 'react';
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
import { exportReport, getSalesRegister } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';
import { formatMoney } from '@/utils/money';
import { canExport } from '@/utils/permissions';
import { downloadReportUrl, formatColumnHeader, isMoneyColumn } from '@/utils/reportFormat';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';

export function SalesReportPage() {
  const { user } = useAuth();
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const query = useQuery({
    queryKey: ['sales-register', dateFrom, dateTo],
    queryFn: () => getSalesRegister({ dateFrom: dateFrom || undefined, dateTo: dateTo || undefined }),
  });

  const exportMutation = useMutation({
    // BUG-616: forward the same date filter the on-screen table is using —
    // previously export ignored it and always exported the full register.
    mutationFn: () => exportReport('sales', { dateFrom: dateFrom || undefined, dateTo: dateTo || undefined }),
    onSuccess: (r) => downloadReportUrl(r.url, 'sales-register.csv'),
  });

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1}>
        <Typography variant="h4">{t('nav.salesReports')}</Typography>
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
        <HelpErrorAlert error={exportMutation.error} />
      ) : null}
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {query.data?.rows?.length === 0 ? <EmptyState description={t('empty.reports')} /> : null}
      {query.data && query.data.rows.length > 0 ? (
        <Paper sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                {Object.keys(query.data.rows[0]).map((key) => (
                  <TableCell key={key}>{formatColumnHeader(key)}</TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {query.data.rows.map((row, idx) => (
                <TableRow key={idx}>
                  {Object.entries(row).map(([key, value]) => (
                    <TableCell key={key}>
                      {/* F3-006: only money-format columns whose *name* is a money field —
                          "any numeric value" also caught hsn_code / gst_rate / quantity. */}
                      {isMoneyColumn(key) && (typeof value === 'number' || typeof value === 'string')
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
