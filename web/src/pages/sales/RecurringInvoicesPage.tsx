import { useState } from 'react';
import Button from '@mui/material/Button';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import * as api from '@/api/resources';
import { ErrorState, LoadingState } from '@/components/PageState';
import { asRows, DataTable, PageShell } from '@/pages/phase/phaseShared';

export function RecurringInvoicesPage() {
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: ['recurring-schedules'],
    queryFn: async () => (await api.listRecurringSchedulesPage()).results,
  });
  const customers = useQuery({ queryKey: ['customers-mini'], queryFn: async () => (await api.listCustomersPage({ pageSize: 100 })).results });
  const products = useQuery({ queryKey: ['products-mini'], queryFn: () => api.searchProducts('') });
  const [customer, setCustomer] = useState('');
  const [cadence, setCadence] = useState('MONTHLY');
  const [nextRunAt, setNextRunAt] = useState('');
  const [productId, setProductId] = useState('');
  const [qty, setQty] = useState('1');
  const [price, setPrice] = useState('');
  const [error, setError] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: () =>
      api.createRecurringSchedule({
        customer: Number(customer),
        cadence,
        nextRunAt,
        isActive: true,
        lineTemplate: {
          items: [{ product: Number(productId), quantity: qty, unitPrice: price || undefined }],
        },
      }),
    onSuccess: () => {
      setCustomer('');
      setProductId('');
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
  if (query.isError) return <ErrorState message={getErrorMessage(query.error)} onRetry={() => void query.refetch()} />;
  return (
    <PageShell title="Recurring invoices" subtitle="Templates spawn DRAFT sales invoices. Never auto-completes. Skips locked GST/accounting periods.">
      {error ? <Typography color="error" variant="body2" sx={{ mb: 1 }}>{error}</Typography> : null}
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} flexWrap="wrap">
          <TextField select size="small" label="Customer" value={customer} onChange={(e) => setCustomer(e.target.value)} sx={{ minWidth: 180 }}>
            {(customers.data ?? []).map((c) => (
              <MenuItem key={c.id} value={c.id}>{c.name}</MenuItem>
            ))}
          </TextField>
          <TextField select size="small" label="Cadence" value={cadence} onChange={(e) => setCadence(e.target.value)} sx={{ minWidth: 140 }}>
            <MenuItem value="MONTHLY">Monthly</MenuItem>
            <MenuItem value="WEEKLY">Weekly</MenuItem>
          </TextField>
          <TextField size="small" type="datetime-local" label="Next run" InputLabelProps={{ shrink: true }} value={nextRunAt} onChange={(e) => setNextRunAt(e.target.value)} />
          <TextField select size="small" label="Product" value={productId} onChange={(e) => setProductId(e.target.value)} sx={{ minWidth: 180 }}>
            {(products.data ?? []).slice(0, 50).map((p) => (
              <MenuItem key={p.id} value={p.id}>{p.name}</MenuItem>
            ))}
          </TextField>
          <TextField size="small" label="Qty" value={qty} onChange={(e) => setQty(e.target.value)} sx={{ width: 80 }} />
          <TextField size="small" label="Price" value={price} onChange={(e) => setPrice(e.target.value)} sx={{ width: 100 }} />
          <Button variant="contained" disabled={!customer || !productId || !nextRunAt || create.isPending} onClick={() => create.mutate()}>
            Save template
          </Button>
        </Stack>
        {create.isError ? <Typography color="error" variant="body2" sx={{ mt: 1 }}>{getErrorMessage(create.error)}</Typography> : null}
      </Paper>
      <DataTable
        rows={asRows(query.data)}
        empty="No recurring schedules yet."
        columns={[
          { key: 'customerName', label: 'Customer' },
          { key: 'cadence', label: 'Cadence' },
          { key: 'nextRunAt', label: 'Next run' },
          { key: 'isActive', label: 'Active' },
        ]}
        actions={(row) => (
          <Stack direction="row" spacing={1} justifyContent="flex-end">
            <Button size="small" disabled={runNow.isPending} onClick={() => runNow.mutate(Number(row.id))}>Run now</Button>
            {row.isActive !== false ? (
              <Button size="small" color="warning" onClick={() => deactivate.mutate(Number(row.id))}>Deactivate</Button>
            ) : null}
          </Stack>
        )}
      />
    </PageShell>
  );
}
