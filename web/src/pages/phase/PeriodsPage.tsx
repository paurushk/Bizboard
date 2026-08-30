import { useState } from 'react';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import * as api from '@/api/resources';
import { ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { asRows, DataTable, PageShell } from '@/pages/phase/phaseShared';

export function PeriodsPage() {
  const { writesBlocked } = useSubscriptionGate();
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: ['accounting-periods'],
    queryFn: async () => (await api.listAccountingPeriodsPage()).results,
  });
  const [name, setName] = useState('');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [fyEnd, setFyEnd] = useState('2026-03-31');
  const create = useMutation({
    mutationFn: () => api.createAccountingPeriod({ name, startDate: start, endDate: end }),
    onSuccess: () => { setName(''); setStart(''); setEnd(''); void qc.invalidateQueries({ queryKey: ['accounting-periods'] }); },
  });
  const setStatus = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) => api.updateAccountingPeriod(id, { status }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['accounting-periods'] }),
  });
  const fyClose = useMutation({
    mutationFn: () => {
      if (!window.confirm(t('phase.confirmCloseFy'))) {
        throw new Error('Cancelled');
      }
      return api.closeFinancialYear({ fyEnd, confirm: true });
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['accounting-periods'] }),
  });
  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  return <PageShell title={t('phase.periods')} subtitle={t('phase.periodsSubtitle')}>
    <Stack direction={{ xs: 'column', md: 'row' }} spacing={1}>
      <TextField label="Name" size="small" value={name} onChange={(e) => setName(e.target.value)} />
      <TextField type="date" label="Start" size="small" InputLabelProps={{ shrink: true }} value={start} onChange={(e) => setStart(e.target.value)} />
      <TextField type="date" label="End" size="small" InputLabelProps={{ shrink: true }} value={end} onChange={(e) => setEnd(e.target.value)} />
      <Button variant="contained" disabled={writesBlocked || !name || !start || !end || create.isPending} onClick={() => create.mutate()}>Create</Button>
      <TextField type="date" label="FY end" size="small" InputLabelProps={{ shrink: true }} value={fyEnd} onChange={(e) => setFyEnd(e.target.value)} />
      <Button color="warning" variant="outlined" disabled={writesBlocked || !fyEnd || fyClose.isPending} onClick={() => fyClose.mutate()}>Close FY</Button>
    </Stack>
    <DataTable rows={asRows(query.data)} empty="No periods configured." columns={[
      { key: 'name', label: 'Name' }, { key: 'startDate', label: 'Start' }, { key: 'endDate', label: 'End' }, { key: 'status', label: 'Status', status: true },
    ]} actions={(row) => row.status !== 'CLOSED' ? <Stack direction="row" spacing={1} justifyContent="flex-end">
      {row.status === 'OPEN' ? <Button size="small" disabled={writesBlocked} onClick={() => setStatus.mutate({ id: Number(row.id), status: 'SOFT_CLOSED' })}>Soft-close</Button> : null}
      <Button size="small" color="error" disabled={writesBlocked} onClick={() => setStatus.mutate({ id: Number(row.id), status: 'CLOSED' })}>Close</Button>
    </Stack> : null} />
  </PageShell>;
}
