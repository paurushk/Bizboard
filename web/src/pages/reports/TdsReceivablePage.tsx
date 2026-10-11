import { useState } from 'react';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { exportTdsReceivableCsv, getTdsReceivableReport } from '@/api/resources';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { PageTitle } from '@/contextHelp';
import { t } from '@/i18n';
import { DataTable, DateRangeFields } from '@/pages/phase/phaseShared';
import { triggerBlobDownload } from '@/utils/blob';
import { formatMoney } from '@/utils/money';
import { useAuth } from '@/auth/AuthContext';
import { canExport } from '@/utils/permissions';

/**
 * Tax customers deducted from what they paid, one row per receipt, to set against Form 26AS and
 * the certificates they send. The same total sits in ledger account 1270 until it is claimed.
 */
export function TdsReceivablePage() {
  const { user } = useAuth();
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const params = {
    ...(dateFrom ? { date_from: dateFrom } : {}),
    ...(dateTo ? { date_to: dateTo } : {}),
  };
  const query = useQuery({
    queryKey: ['tds-receivable', dateFrom, dateTo],
    queryFn: () => getTdsReceivableReport(params),
  });
  const exportCsv = useMutation({
    mutationFn: () => exportTdsReceivableCsv(params),
    onSuccess: (blob) => triggerBlobDownload(blob, 'tds-receivable.csv'),
  });
  const data = query.data;

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1}>
        <PageTitle>{t('nav.tdsReceivable')}</PageTitle>
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
          <DateRangeFields from={dateFrom} to={dateTo} onFromChange={setDateFrom} onToChange={setDateTo} />
          {canExport(user) ? (
            <Button variant="outlined" size="small" disabled={exportCsv.isPending} onClick={() => exportCsv.mutate()}>
              {t('receipts.exportCsv')}
            </Button>
          ) : null}
        </Stack>
      </Stack>
      <Typography variant="body2" color="text.secondary">
        {t('reports.tdsReceivableHelp')}
      </Typography>
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {exportCsv.isError ? <Typography color="error">{getErrorMessage(exportCsv.error)}</Typography> : null}
      {data ? (
        <>
          <Card variant="outlined" sx={{ p: 2, maxWidth: 260 }}>
            <Typography variant="caption" color="text.secondary">
              {t('reports.tdsReceivableTotal')}
            </Typography>
            <Typography variant="h6">{formatMoney(data.totalTds)}</Typography>
          </Card>
          {data.rows.length === 0 ? (
            <EmptyState description={t('reports.tdsReceivableEmpty')} />
          ) : (
            <DataTable
              rows={data.rows as never}
              empty={t('reports.tdsReceivableEmpty')}
              columns={[
                { key: 'receiptNumber', label: t('common.number') },
                { key: 'receiptDate', label: t('common.date') },
                { key: 'customer', label: t('billing.customer') },
                { key: 'pan', label: t('reports.pan') },
                { key: 'section', label: t('receipts.tdsSection') },
                { key: 'amountReceived', label: t('common.amount'), money: true },
                { key: 'tdsDeducted', label: t('receipts.tdsDeducted'), money: true },
                { key: 'tdsUnapplied', label: t('reports.tdsNotYetSet'), money: true },
              ]}
            />
          )}
        </>
      ) : null}
    </Stack>
  );
}
