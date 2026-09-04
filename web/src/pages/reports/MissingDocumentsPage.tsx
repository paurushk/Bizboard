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
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { chaseMissingPhoto, chaseMissingWhatsApp, fetchMissingDocuments } from '@/api/gstr2b';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { PageHeader } from '@/components/insights';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';
import { openShareUrl } from '@/utils/safeUrl';

function currentPeriod() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

export function MissingDocumentsPage() {
  const [params] = useSearchParams();
  const clientView = params.get('view') === 'client';
  const [period, setPeriod] = useState(currentPeriod());
  const [confirmSend, setConfirmSend] = useState(false);
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: ['missing-documents', period],
    queryFn: () => fetchMissingDocuments(period),
  });
  const wa = useMutation({
    mutationFn: () => chaseMissingWhatsApp(period),
    onSuccess: (res) => {
      const link = res.shareLink || res.share_link;
      if (link) {
        try {
          openShareUrl(String(link));
        } catch {
          /* invoice share recovery */
        }
      }
      void qc.invalidateQueries({ queryKey: ['missing-documents', period] });
    },
  });
  const photo = useMutation({
    mutationFn: ({ id, file }: { id: number; file: File }) => chaseMissingPhoto(id, file),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['missing-documents', period] }),
  });

  if (query.isLoading) return <LoadingState />;
  if (query.isError) {
    return (
      <ErrorState
        message={getErrorMessage(query.error)}
        error={query.error}
        onRetry={() => void query.refetch()}
      />
    );
  }

  const items = query.data?.items ?? [];

  return (
    <Stack spacing={2}>
      <PageHeader
        title={clientView ? t('chase.clientTitle') : t('chase.title')}
        actions={
          <Button
            variant="contained"
            onClick={() => setConfirmSend(true)}
            disabled={wa.isPending || items.length === 0}
          >
            {t('chase.sendWhatsApp')}
          </Button>
        }
      />
      <ConfirmDialog
        open={confirmSend}
        title={t('chase.sendWhatsApp')}
        body={`This sends a WhatsApp chase message to ${items.length} supplier(s) with a missing document for ${period}.`}
        confirmLabel={t('chase.sendWhatsApp')}
        confirming={wa.isPending}
        onClose={() => setConfirmSend(false)}
        onConfirm={() => {
          setConfirmSend(false);
          wa.mutate();
        }}
      />
      <Alert severity="info">{clientView ? t('chase.clientHint') : t('chase.caHint')}</Alert>
      <TextField
        type="month"
        label={t('chase.period')}
        size="small"
        value={period}
        onChange={(e) => setPeriod(e.target.value)}
        InputLabelProps={{ shrink: true }}
        sx={{ maxWidth: 180 }}
      />
      {wa.error ? <Alert severity="error">{getErrorMessage(wa.error)}</Alert> : null}
      {photo.error ? <Alert severity="error">{getErrorMessage(photo.error)}</Alert> : null}
      {items.length === 0 ? (
        <EmptyState description={t('chase.empty')} />
      ) : (
        <Paper variant="outlined" sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('chase.supplierGstin')}</TableCell>
                <TableCell>{t('chase.invoiceNumber')}</TableCell>
                <TableCell>{t('chase.date')}</TableCell>
                <TableCell align="right">{t('chase.taxable')}</TableCell>
                <TableCell>{t('chase.status')}</TableCell>
                <TableCell>{t('chase.photo')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {items.map((row) => (
                <TableRow key={String(row.id)}>
                  <TableCell>{String(row.supplierGstin ?? row.supplier_gstin ?? '')}</TableCell>
                  <TableCell>{String(row.invoiceNumber ?? row.invoice_number ?? '')}</TableCell>
                  <TableCell>{String(row.invoiceDate ?? row.invoice_date ?? '')}</TableCell>
                  <TableCell align="right">{String(row.taxableValue ?? row.taxable_value ?? '')}</TableCell>
                  <TableCell>{String(row.status ?? '')}</TableCell>
                  <TableCell>
                    <Button component="label" size="small">
                      {t('chase.upload')}
                      <input
                        type="file"
                        hidden
                        accept="image/*,application/pdf"
                        onChange={(e) => {
                          const file = e.target.files?.[0];
                          if (file) photo.mutate({ id: Number(row.id), file });
                        }}
                      />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      )}
      <Typography variant="caption" color="text.secondary">
        {t('chase.count', { count: String(items.length) })}
      </Typography>
    </Stack>
  );
}
