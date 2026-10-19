import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import TextField from '@mui/material/TextField';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import Typography from '@mui/material/Typography';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { chaseMissingPhoto, chaseMissingWhatsApp, fetchMissingDocuments } from '@/api/gstr2b';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';
import { openShareUrl } from '@/utils/safeUrl';
import { DataTable } from '@/pages/phase/phaseShared';
import { showEmpty } from '@/utils/queryState';
import { PageShell } from '@/pages/phase/phaseShared';

function currentPeriod() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

export function MissingDocumentsPage() {
  const [params, setParams] = useSearchParams();
  const clientView = params.get('view') === 'client';
  const [period, setPeriod] = useState(currentPeriod());
  const [confirmSend, setConfirmSend] = useState(false);
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: ['missing-documents', period],
    queryFn: () => fetchMissingDocuments(period),
    // Keep the month picker and the last list on screen while another month loads.
    placeholderData: keepPreviousData,
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

  // A failed refetch must not keep showing the previous month's list as if it were this month's.
  const items = query.isError ? [] : (query.data?.items ?? []);
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
    <PageShell title={clientView ? t('chase.clientTitle') : t('chase.title')} actions={
          <Button
            variant="contained"
            onClick={() => setConfirmSend(true)}
            disabled={wa.isPending || items.length === 0}
          >
            {t('chase.sendWhatsApp')}
          </Button>
}>      <ConfirmDialog
        open={confirmSend}
        title={t('chase.sendWhatsApp')}
        body={t('chase.sendBody', { count: String(items.length), period })}
        confirmLabel={t('chase.sendWhatsApp')}
        confirming={wa.isPending}
        onClose={() => setConfirmSend(false)}
        onConfirm={() => {
          setConfirmSend(false);
          wa.mutate();
        }}
      />
      <ToggleButtonGroup
        size="small"
        exclusive
        value={clientView ? 'client' : 'ca'}
        onChange={(_e, next) => {
          if (!next) return;
          const nextParams = new URLSearchParams(params);
          if (next === 'client') nextParams.set('view', 'client');
          else nextParams.delete('view');
          setParams(nextParams, { replace: true });
        }}
        aria-label={t('chase.title')}
      >
        <ToggleButton value="ca">{t('chase.viewCa')}</ToggleButton>
        <ToggleButton value="client">{t('chase.viewClient')}</ToggleButton>
      </ToggleButtonGroup>
      <Alert severity="info">{clientView ? t('chase.clientHint') : t('chase.caHint')}</Alert>
      <TextField
        type="month"
        label={t('chase.period')}
        size="small"
        value={period}
        onChange={(e) => { if (e.target.value) setPeriod(e.target.value); }}
        InputLabelProps={{ shrink: true }}
        sx={{ maxWidth: 180 }}
      />
      {wa.error ? <Alert severity="error">{getErrorMessage(wa.error)}</Alert> : null}
      {photo.error ? <Alert severity="error">{getErrorMessage(photo.error)}</Alert> : null}
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {showEmpty(query, items.length) ? <EmptyState description={t('chase.empty')} /> : null}
      {!query.isError && items.length > 0 ? (
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
            { key: 'taxableValue', label: t('chase.taxable'), money: true },
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
      ) : null}
      <Typography variant="caption" color="text.secondary">
        {t('chase.count', { count: String(items.length) })}
      </Typography>
    </PageShell>
  );
}
