import { useState } from 'react';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import * as api from '@/api/resources';
import { todayIso } from '@/components/billing';
import { ErrorState, LoadingState } from '@/components/PageState';
import { asRows, DataTable, PageShell } from '@/pages/phase/phaseShared';
import { t } from '@/i18n';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';

export function FixedAssetsPage() {
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: ['fixed-assets'],
    queryFn: async () => (await api.listFixedAssetsPage()).results,
  });
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [cost, setCost] = useState('');
  const [error, setError] = useState('');
  const create = useMutation({
    mutationFn: () =>
      api.createFixedAsset({
        name,
        acquisitionCost: Number(cost),
        acquisitionDate: todayIso(),
        usefulLifeMonths: 36,
      }),
    onSuccess: () => {
      setOpen(false);
      setError('');
      void qc.invalidateQueries({ queryKey: ['fixed-assets'] });
    },
    onError: (e) => setError(getErrorMessage(e)),
  });
  const dispose = useMutation({
    mutationFn: (id: number) => api.disposeFixedAsset(id),
    onSuccess: () => {
      setError('');
      void qc.invalidateQueries({ queryKey: ['fixed-assets'] });
    },
    onError: (e) => setError(getErrorMessage(e)),
  });
  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  return (
    <PageShell
      title={t('phase.fixedAssets')}
      subtitle={t('phase.fixedAssetsSubtitle')}
      actions={
        <Button variant="contained" onClick={() => setOpen(true)}>
          Add asset
        </Button>
      }
    >
      <DataTable
        rows={asRows(query.data)}
        empty="No fixed assets."
        columns={[
          { key: 'name', label: 'Name' },
          { key: 'acquisitionCost', label: 'Cost', money: true },
          { key: 'acquisitionDate', label: 'Purchased' },
          { key: 'usefulLifeMonths', label: 'Life (mo)' },
          { key: 'status', label: 'Status', status: true },
        ]}
        actions={(row) => row.status === 'ACTIVE' ? (
          <Button size="small" color="error" onClick={() => dispose.mutate(Number(row.id))}>Dispose</Button>
        ) : null}
      />
      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>Fixed asset</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {error ? <HelpErrorAlert message={error} /> : null}
            <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} />
            <TextField label="Acquisition cost" type="number" value={cost} onChange={(e) => setCost(e.target.value)} />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button variant="contained" disabled={!name || !cost || create.isPending} onClick={() => create.mutate()}>
            Save
          </Button>
        </DialogActions>
      </Dialog>
    </PageShell>
  );
}
