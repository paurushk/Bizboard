import { useState } from 'react';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { addJobCardLine, convertJobCard, createJobCard, listJobCards } from '@/api/roadmap';
import { isWorkshopEnabled } from '@/config/features';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { PageTitle } from '@/contextHelp';
import { t } from '@/i18n';
import { CustomerField, ProductField } from '@/pages/growth/widgets';
import { PageShell } from '@/pages/phase/phaseShared';
import type { Customer, Product } from '@/types/domain';

function rowsOf(data: unknown): Record<string, unknown>[] {
  if (Array.isArray(data)) return data as Record<string, unknown>[];
  const results = (data as { results?: Record<string, unknown>[] } | null)?.results;
  return results ?? [];
}

export function JobCardsPage() {
  if (!isWorkshopEnabled()) {
    return <PageShell title={t('nav.jobCards')}><Typography>{t('erp.moduleDisabled')}</Typography></PageShell>;
  }
  return <JobCardsInner />;
}

function JobCardsInner() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [complaint, setComplaint] = useState('');
  const [registrationNo, setRegistrationNo] = useState('');
  const [vehicleModel, setVehicleModel] = useState('');
  const [odometer, setOdometer] = useState('');
  const [error, setError] = useState('');
  const [lineProduct, setLineProduct] = useState<Product | null>(null);
  const [lineQty, setLineQty] = useState('1');
  const [linePrice, setLinePrice] = useState('');
  const [lineJobId, setLineJobId] = useState<number | ''>('');
  const list = useQuery({ queryKey: ['job-cards'], queryFn: listJobCards });
  const create = useMutation({
    mutationFn: () => createJobCard({
      customer: customer!.id,
      complaint,
      registration_no: registrationNo,
      vehicle_model: vehicleModel,
      odometer_reading: odometer || undefined,
    }),
    onSuccess: () => {
      setComplaint('');
      setRegistrationNo('');
      setVehicleModel('');
      setOdometer('');
      void qc.invalidateQueries({ queryKey: ['job-cards'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const convert = useMutation({
    mutationFn: (id: number) => convertJobCard(id),
    onSuccess: (row) => {
      const invoiceId = Number(row.salesInvoice ?? row.sales_invoice);
      if (invoiceId) navigate(`/sales/history/${invoiceId}`);
      void qc.invalidateQueries({ queryKey: ['job-cards'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const addLine = useMutation({
    mutationFn: () => addJobCardLine(Number(lineJobId), {
      kind: 'PART',
      product: lineProduct!.id,
      quantity: lineQty || '1',
      unit_price: linePrice || String(lineProduct?.sellingPrice ?? '0'),
    }),
    onSuccess: () => {
      setLineProduct(null);
      setLineQty('1');
      setLinePrice('');
      void qc.invalidateQueries({ queryKey: ['job-cards'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  return (
    <Stack spacing={2}>
      <PageTitle>{t('nav.jobCards')}</PageTitle>
      <Typography variant="body2" color="text.secondary">{t('growth.jobCard')}</Typography>
      {error ? <Typography color="error">{error}</Typography> : null}
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1}>
        <CustomerField value={customer} onChange={setCustomer} />
        <TextField size="small" label={t('growth.complaint')} value={complaint} onChange={(e) => setComplaint(e.target.value)} />
        <TextField size="small" label={t('growth.registrationNo')} value={registrationNo} onChange={(e) => setRegistrationNo(e.target.value)} />
        <TextField size="small" label={t('growth.vehicleModel')} value={vehicleModel} onChange={(e) => setVehicleModel(e.target.value)} />
        <TextField size="small" label={t('growth.odometer')} value={odometer} onChange={(e) => setOdometer(e.target.value)} />
        <Button variant="contained" disabled={!customer || create.isPending} onClick={() => create.mutate()}>{t('growth.createJobCard')}</Button>
      </Stack>
      {list.isLoading ? <LoadingState /> : null}
      {list.isError ? <ErrorState message={getErrorMessage(list.error)} error={list.error} onRetry={() => void list.refetch()} /> : null}
      {!list.isLoading && !list.isError && rowsOf(list.data).length === 0 ? (
        <EmptyState description={t('cog.emptyJobCards')} />
      ) : null}
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} alignItems={{ md: 'center' }}>
        <TextField
          size="small"
          label={t('growth.jobId')}
          value={lineJobId}
          onChange={(e) => setLineJobId(e.target.value ? Number(e.target.value) : '')}
          sx={{ maxWidth: 120 }}
        />
        <ProductField value={lineProduct} onChange={setLineProduct} />
        <TextField size="small" label={t('growth.quantity')} value={lineQty} onChange={(e) => setLineQty(e.target.value)} sx={{ maxWidth: 100 }} />
        <TextField size="small" label={t('growth.unitPrice')} value={linePrice} onChange={(e) => setLinePrice(e.target.value)} sx={{ maxWidth: 120 }} />
        <Button
          variant="outlined"
          disabled={!lineJobId || !lineProduct || addLine.isPending}
          onClick={() => addLine.mutate()}
        >
          {t('growth.addLine')}
        </Button>
      </Stack>
      {rowsOf(list.data).map((row) => {
        const lines = Array.isArray(row.lines) ? row.lines : [];
        const canInvoice = lines.length > 0 && row.status !== 'INVOICED' && row.status !== 'CANCELLED';
        return (
        <Stack key={String(row.id)} direction="row" spacing={1} alignItems="center">
          <Typography>
            {String(row.number)} · {String(row.status)}
            {row.registrationNo || row.registration_no ? ` · ${String(row.registrationNo ?? row.registration_no)}` : ''}
            {row.vehicleModel || row.vehicle_model ? ` · ${String(row.vehicleModel ?? row.vehicle_model)}` : ''}
            {row.odometerReading || row.odometer_reading ? ` · ${String(row.odometerReading ?? row.odometer_reading)}` : ''}
            {` · ${t('growth.lines')}: ${lines.length}`}
          </Typography>
          {Array.isArray(row.serialHistory) && (row.serialHistory as Array<{ serialId?: number; capped?: boolean; jobs?: Array<{ id: number; number: string; status?: string; date?: string }> }>).map((group) => (
            <Typography key={String(group.serialId)} variant="caption">
              {t('growth.serialHistory')}
              {group.capped ? ` · ${t('growth.serialHistoryCapped')}` : ''}
              {(group.jobs ?? []).map((job) => (
                <span key={job.id}>{` ${job.number} · ${t('common.status')}: ${job.status} · ${t('common.date')}: ${job.date}`}</span>
              ))}
            </Typography>
          ))}
          {canInvoice ? (
            <Button size="small" onClick={() => convert.mutate(Number(row.id))}>{t('growth.createDraftInvoice')}</Button>
          ) : null}
        </Stack>
        );
      })}
    </Stack>
  );
}
