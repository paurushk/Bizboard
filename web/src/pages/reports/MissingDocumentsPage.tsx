import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
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
import { DataTable } from '@/pages/phase/phaseShared';

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
  // F3-017: normalize the camelCase/snake_case field fallbacks once so
  // DataTable's generic column lookup can key straight into each row.
  const rows = items.map((row) => ({
    ...row,
    supplierGstin: row.supplierGstin ?? row.supplier_gstin ?? '',
    invoiceNumber: row.invoiceNumber ?? row.invoice_number ?? '',
    invoiceDate: row.invoiceDate ?? row.invoice_date ?? '',
    taxableValue: row.taxableValue ?? row.taxable_value ?? '',
  }));

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
        <DataTable
          rows={rows}
          empty={t('chase.empty')}
          // F3-017: window the DOM rows instead of rendering every missing
          // document in the period at once.
          virtualized
          columns={[
            { key: 'supplierGstin', label: t('chase.supplierGstin') },
            { key: 'invoiceNumber', label: t('chase.invoiceNumber') },
            { key: 'invoiceDate', label: t('chase.date') },
            { key: 'taxableValue', label: t('chase.taxable') },
            { key: 'status', label: t('chase.status') },
          ]}
          actions={(row) => (
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
          )}
        />
      )}
      <Typography variant="caption" color="text.secondary">
        {t('chase.count', { count: String(items.length) })}
      </Typography>
    </Stack>
  );
}
