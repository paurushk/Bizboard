import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import * as api from '@/api/resources';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { ErrorState, LoadingState } from '@/components/PageState';
import { useAuth } from '@/auth/AuthContext';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { useProductCfFilters } from '@/hooks/useProductCfFilters';
import { t } from '@/i18n';
import { asRows, DataTable, PageShell } from '@/pages/phase/phaseShared';
import { canCreateSales } from '@/utils/permissions';

export function RecurringInvoicesPage() {
  const { user } = useAuth();
  const { writesBlocked } = useSubscriptionGate();
  const canWrite = canCreateSales(user) && !writesBlocked;
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: ['recurring-schedules'],
    queryFn: async () => (await api.listRecurringSchedulesPage()).results,
  });
  const customers = useQuery({ queryKey: ['customers-mini'], queryFn: async () => (await api.listCustomersPage({ pageSize: 100 })).results });
  const cf = useProductCfFilters();
  const products = useQuery({ queryKey: ['products-mini', cf.cfFilters], queryFn: () => api.searchProducts('', { cf: cf.cfFilters }) });
  const [customer, setCustomer] = useState('');
  const [cadence, setCadence] = useState('MONTHLY');
  const [nextRunAt, setNextRunAt] = useState('');
  const [stopStage, setStopStage] = useState('INVOICE');
  const [lines, setLines] = useState([{ productId: '', qty: '1', price: '' }]);
  const [error, setError] = useState<string | null>(null);
  const [confirmRun, setConfirmRun] = useState<number | null>(null);
  // F2-043: remember which schedule's "Run now" is in flight so only that row's
  // button shows the pending state instead of disabling every row at once.
  const [runningId, setRunningId] = useState<number | null>(null);
  const create = useMutation({
    mutationFn: () =>
      api.createRecurringSchedule({
        customer: Number(customer),
        cadence,
        nextRunAt,
        isActive: true,
        lineTemplate: {
          items: lines
            .filter((l) => l.productId && Number(l.qty) > 0)
            .map((l) => ({
              product: Number(l.productId),
              quantity: Number(l.qty),
              unitPrice: l.price === '' ? undefined : Number(l.price),
            })),
        },
        stopStage,
      }),
    onSuccess: () => {
      setCustomer('');
      setLines([{ productId: '', qty: '1', price: '' }]);
      setError(null);
      void qc.invalidateQueries({ queryKey: ['recurring-schedules'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const runNow = useMutation({
    mutationFn: (id: number) => api.runRecurringScheduleNow(id),
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries({ queryKey: ['recurring-schedules'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
    onSettled: () => setRunningId(null),
  });
  const deactivate = useMutation({
    mutationFn: (id: number) => api.updateRecurringSchedule(id, { isActive: false }),
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries({ queryKey: ['recurring-schedules'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  return (
    <PageShell title={t('nav.recurringInvoices')} subtitle={t('recurring.subtitle')}>
      <Alert severity="info">{t('recurring.draftOnlyBanner')}</Alert>
      {error ? <Typography color="error" variant="body2" sx={{ mb: 1 }}>{error}</Typography> : null}
      {canWrite ? (
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} flexWrap="wrap">
          <TextField select size="small" label={t('billing.customer')} value={customer} onChange={(e) => setCustomer(e.target.value)} sx={{ minWidth: 180 }}>
            {(customers.data ?? []).map((c) => (
              <MenuItem key={c.id} value={c.id}>{c.name}</MenuItem>
            ))}
          </TextField>
          <TextField select size="small" label={t('recurring.cadence')} value={cadence} onChange={(e) => setCadence(e.target.value)} sx={{ minWidth: 140 }}>
            <MenuItem value="MONTHLY">{t('recurring.monthly')}</MenuItem>
            <MenuItem value="WEEKLY">{t('recurring.weekly')}</MenuItem>
          </TextField>
          <TextField size="small" type="datetime-local" label={t('recurring.nextRun')} InputLabelProps={{ shrink: true }} value={nextRunAt} onChange={(e) => setNextRunAt(e.target.value)} />
          <TextField select size="small" label={t('recurring.stopStage')} value={stopStage} onChange={(e) => setStopStage(e.target.value)} sx={{ minWidth: 180 }}>
            <MenuItem value="INVOICE">{t('recurring.stopInvoice')}</MenuItem>
            <MenuItem value="SALES_ORDER">{t('recurring.stopSalesOrder')}</MenuItem>
            <MenuItem value="DELIVERY_CHALLAN">{t('recurring.stopDeliveryChallan')}</MenuItem>
          </TextField>
          {cf.filterBar}
          {lines.map((line, idx) => (
            <Stack key={idx} direction="row" spacing={1} alignItems="center">
          <TextField select size="small" label={t('common.product')} value={line.productId} onChange={(e) => setLines((prev) => prev.map((row, i) => i === idx ? { ...row, productId: e.target.value } : row))} sx={{ minWidth: 180 }}>
            {(products.data ?? []).slice(0, 50).map((p) => (
              <MenuItem key={p.id} value={p.id}>{p.name}</MenuItem>
            ))}
          </TextField>
          <TextField
            size="small"
            type="number"
            label={t('common.qty')}
            value={line.qty}
            onChange={(e) => setLines((prev) => prev.map((row, i) => i === idx ? { ...row, qty: e.target.value } : row))}
            inputProps={{ min: 0.001, step: 'any', inputMode: 'decimal' }}
            error={line.qty !== '' && !(Number(line.qty) > 0)}
            sx={{ width: 90 }}
          />
          <TextField
            size="small"
            type="number"
            label={t('billing.priceShort')}
            value={line.price}
            onChange={(e) => setLines((prev) => prev.map((row, i) => i === idx ? { ...row, price: e.target.value } : row))}
            inputProps={{ min: 0, step: 'any', inputMode: 'decimal' }}
            error={line.price !== '' && Number(line.price) < 0}
            sx={{ width: 110 }}
          />
            {idx === 0 ? (
              <Button size="small" onClick={() => setLines((prev) => [...prev, { productId: '', qty: '1', price: '' }])}>{t('common.add')}</Button>
            ) : (
              <Button size="small" color="inherit" onClick={() => setLines((prev) => prev.filter((_, i) => i !== idx))}>{t('common.remove')}</Button>
            )}
            </Stack>
          ))}
          <Button
            variant="contained"
            disabled={
              !customer ||
              !nextRunAt ||
              !lines.some((l) => l.productId && Number(l.qty) > 0) ||
              lines.some((l) => l.price !== '' && Number(l.price) < 0) ||
              create.isPending
            }
            onClick={() => create.mutate()}
          >
            {t('recurring.saveTemplate')}
          </Button>
        </Stack>
        {create.isError ? <Typography color="error" variant="body2" sx={{ mt: 1 }}>{getErrorMessage(create.error)}</Typography> : null}
      </Paper>
      ) : null}
      <DataTable
        rows={asRows(query.data)}
        empty={t('recurring.empty')}
        columns={[
          { key: 'customerName', label: t('billing.customer') },
          { key: 'cadence', label: t('recurring.cadence') },
          { key: 'stopStage', label: t('recurring.stopStage') },
          { key: 'nextRunAt', label: t('recurring.nextRun') },
          { key: 'isActive', label: t('status.ACTIVE') },
        ]}
        actions={(row) => (
          <Stack direction="row" spacing={1} justifyContent="flex-end">
            <Button
              size="small"
              disabled={!canWrite || runningId !== null}
              onClick={() => setConfirmRun(Number(row.id))}
            >
              {runningId === Number(row.id) ? t('common.loading') : t('recurring.runNow')}
            </Button>
            {row.isActive !== false && canWrite ? (
              <Button size="small" color="warning" onClick={() => deactivate.mutate(Number(row.id))}>{t('recurring.deactivate')}</Button>
            ) : null}
          </Stack>
        )}
      />
      <ConfirmDialog
        open={confirmRun !== null}
        title={t('recurring.runNow')}
        body={t('recurring.runNowConfirm')}
        confirmLabel={t('recurring.runNow')}
        confirming={runNow.isPending}
        onClose={() => setConfirmRun(null)}
        onConfirm={() => {
          const id = confirmRun;
          setConfirmRun(null);
          if (id != null) {
            setRunningId(id);
            runNow.mutate(id);
          }
        }}
      />
    </PageShell>
  );
}
