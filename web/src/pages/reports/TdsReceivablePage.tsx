import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { exportTdsReceivableCsv, getTdsReceivableReport, setReceiptTdsCertificate } from '@/api/resources';
import { MoneyHandoffBar } from '@/components/MoneyHandoffBar';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { PageTitle } from '@/contextHelp';
import { t } from '@/i18n';
import { DataTable, DateRangeFields } from '@/pages/phase/phaseShared';
import { triggerBlobDownload } from '@/utils/blob';
import { formatMoney } from '@/utils/money';
import { useAuth } from '@/auth/AuthContext';
import { canCreatePayments, canExport } from '@/utils/permissions';

type CertificateFilter = '' | 'pending' | 'received';

/**
 * Tax customers deducted from what they paid, one row per receipt, to set against Form 26AS and
 * the certificates they send. The same total sits in ledger account 1270 until it is claimed.
 * Recording that a certificate arrived is bookkeeping only: it posts nothing to the ledger.
 */
export function TdsReceivablePage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  // The Money hub links here with ?certificate=pending (TDS still waiting for its certificate).
  const [certificate, setCertificate] = useState<CertificateFilter>(() => {
    const raw = searchParams.get('certificate');
    return raw === 'pending' || raw === 'received' ? raw : '';
  });
  const [recording, setRecording] = useState<{ id: number; number: string } | null>(null);
  const [receivedOn, setReceivedOn] = useState('');
  const [reference, setReference] = useState('');
  const canRecord = canCreatePayments(user);
  const params = {
    ...(dateFrom ? { date_from: dateFrom } : {}),
    ...(dateTo ? { date_to: dateTo } : {}),
    ...(certificate ? { certificate } : {}),
  };
  const query = useQuery({
    queryKey: ['tds-receivable', dateFrom, dateTo, certificate],
    queryFn: () => getTdsReceivableReport(params),
  });
  const exportCsv = useMutation({
    mutationFn: () => exportTdsReceivableCsv(params),
    onSuccess: (blob) => triggerBlobDownload(blob, 'tds-receivable.csv'),
  });
  const certificateMutation = useMutation({
    mutationFn: (payload: { id: number; received: boolean; receivedOn?: string; reference?: string }) =>
      setReceiptTdsCertificate(payload.id, payload),
    onSuccess: () => {
      setRecording(null);
      setReceivedOn('');
      setReference('');
      void qc.invalidateQueries({ queryKey: ['tds-receivable'] });
    },
  });
  const data = query.data;

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1}>
        <PageTitle>{t('nav.tdsReceivable')}</PageTitle>
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
          <TextField
            select
            size="small"
            label={t('reports.tdsCertificateFilter')}
            value={certificate}
            onChange={(event) => setCertificate(event.target.value as CertificateFilter)}
            sx={{ minWidth: 190 }}
          >
            <MenuItem value="">{t('common.all')}</MenuItem>
            <MenuItem value="pending">{t('reports.tdsCertificatePending')}</MenuItem>
            <MenuItem value="received">{t('reports.tdsCertificateReceived')}</MenuItem>
          </TextField>
          <DateRangeFields from={dateFrom} to={dateTo} onFromChange={setDateFrom} onToChange={setDateTo} />
          {canExport(user) ? (
            <Button variant="outlined" size="small" disabled={exportCsv.isPending} onClick={() => exportCsv.mutate()}>
              {t('receipts.exportCsv')}
            </Button>
          ) : null}
        </Stack>
      </Stack>
      <MoneyHandoffBar
        filterLabel={t('money.filters.tdsAwaiting')}
        onShowAll={() => {
          setCertificate('');
          setSearchParams({}, { replace: true });
        }}
      />
      <Typography variant="body2" color="text.secondary">
        {t('reports.tdsReceivableHelp')}
      </Typography>
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {exportCsv.isError ? <Typography color="error">{getErrorMessage(exportCsv.error)}</Typography> : null}
      {certificateMutation.isError && !recording ? (
        <Alert severity="error">{getErrorMessage(certificateMutation.error)}</Alert>
      ) : null}
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
                {
                  key: 'certificateReceivedOn',
                  label: t('reports.tdsCertificate'),
                  render: (row) =>
                    row.certificateReceivedOn
                      ? t('reports.tdsCertificateOn', {
                          date: String(row.certificateReceivedOn),
                          ref: row.certificateRef ? ` · ${String(row.certificateRef)}` : '',
                        })
                      : t('reports.tdsCertificateAwaiting'),
                },
              ]}
              actions={
                canRecord
                  ? (row) =>
                      row.certificateReceivedOn ? (
                        <Button
                          size="small"
                          disabled={certificateMutation.isPending}
                          onClick={() => certificateMutation.mutate({ id: Number(row.receiptId), received: false })}
                        >
                          {t('reports.tdsCertificateUndo')}
                        </Button>
                      ) : (
                        <Button
                          size="small"
                          variant="outlined"
                          onClick={() => setRecording({ id: Number(row.receiptId), number: String(row.receiptNumber) })}
                        >
                          {t('reports.tdsCertificateRecord')}
                        </Button>
                      )
                  : undefined
              }
            />
          )}
        </>
      ) : null}

      <Dialog open={Boolean(recording)} onClose={() => setRecording(null)} fullWidth maxWidth="xs">
        <DialogTitle>{t('reports.tdsCertificateTitle', { number: recording?.number ?? '' })}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Typography variant="body2" color="text.secondary">
              {t('reports.tdsCertificateHelp')}
            </Typography>
            <TextField
              type="date"
              label={t('reports.tdsCertificateDate')}
              value={receivedOn}
              onChange={(event) => setReceivedOn(event.target.value)}
              slotProps={{ inputLabel: { shrink: true } }}
              helperText={t('reports.tdsCertificateDateHelp')}
            />
            <TextField
              label={t('reports.tdsCertificateRef')}
              value={reference}
              onChange={(event) => setReference(event.target.value)}
              slotProps={{ htmlInput: { maxLength: 64 } }}
            />
            {certificateMutation.isError ? (
              <Alert severity="error">{getErrorMessage(certificateMutation.error)}</Alert>
            ) : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRecording(null)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={certificateMutation.isPending}
            onClick={() =>
              recording &&
              certificateMutation.mutate({
                id: recording.id,
                received: true,
                receivedOn: receivedOn || undefined,
                reference: reference.trim() || undefined,
              })
            }
          >
            {t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
