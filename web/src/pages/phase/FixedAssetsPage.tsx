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
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';

const DEFAULT_USEFUL_LIFE_MONTHS = '36';

export function FixedAssetsPage() {
  const { writesBlocked } = useSubscriptionGate();
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: ['fixed-assets'],
    queryFn: () => api.listFixedAssets(),
  });
  const [open, setOpen] = useState(false);
  // F3-024: null = creating a new asset; otherwise the id being edited.
  const [editingId, setEditingId] = useState<number | null>(null);
  const [name, setName] = useState('');
  const [cost, setCost] = useState('');
  const [acquisitionDate, setAcquisitionDate] = useState(todayIso());
  const [usefulLifeMonths, setUsefulLifeMonths] = useState(DEFAULT_USEFUL_LIFE_MONTHS);
  const [depreciatedAmount, setDepreciatedAmount] = useState(0);
  const [error, setError] = useState('');

  const resetForm = () => {
    setEditingId(null);
    setName('');
    setCost('');
    setAcquisitionDate(todayIso());
    setUsefulLifeMonths(DEFAULT_USEFUL_LIFE_MONTHS);
    setDepreciatedAmount(0);
  };

  const openCreate = () => {
    resetForm();
    setOpen(true);
  };

  const openEdit = (row: Record<string, unknown>) => {
    setEditingId(Number(row.id));
    setName(String(row.name ?? ''));
    setCost(String(row.acquisitionCost ?? ''));
    setAcquisitionDate(String(row.acquisitionDate ?? todayIso()).slice(0, 10));
    setUsefulLifeMonths(String(row.usefulLifeMonths ?? DEFAULT_USEFUL_LIFE_MONTHS));
    setDepreciatedAmount(Number(row.depreciatedAmount ?? 0));
    setOpen(true);
  };

  const create = useMutation({
    mutationFn: () => {
      const payload = {
        name,
        acquisitionDate,
        usefulLifeMonths: Number(usefulLifeMonths),
      };
      if (editingId != null) {
        // Depreciation already posted against the old schedule -- the cost
        // basis and schedule inputs are frozen; only the name can still be
        // corrected. (A schedule change after posting needs a real
        // recompute/catch-up, out of scope here.)
        return depreciatedAmount > 0
          ? api.updateFixedAsset(editingId, { name })
          : api.updateFixedAsset(editingId, payload);
      }
      return api.createFixedAsset({ ...payload, acquisitionCost: Number(cost) });
    },
    onSuccess: () => {
      setOpen(false);
      setError('');
      resetForm();
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
        <Button variant="contained" onClick={openCreate} disabled={writesBlocked}>
          {t('phase.addAsset')}
        </Button>
      }
    >
      <DataTable
        rows={asRows(query.data)}
        empty={t('phase.noFixedAssets')}
        columns={[
          { key: 'name', label: t('common.name') },
          { key: 'acquisitionCost', label: t('phase.assetCost'), money: true },
          { key: 'acquisitionDate', label: t('phase.assetPurchased') },
          { key: 'usefulLifeMonths', label: t('phase.assetLife') },
          { key: 'status', label: t('common.status'), status: true },
        ]}
        actions={(row) => (
          <Stack direction="row" spacing={1}>
            {row.status === 'ACTIVE' ? (
              <Button size="small" disabled={writesBlocked} onClick={() => openEdit(row)}>{t('common.edit')}</Button>
            ) : null}
            {row.status === 'ACTIVE' ? (
              <Button size="small" color="error" disabled={writesBlocked} onClick={() => dispose.mutate(Number(row.id))}>{t('phase.assetDispose')}</Button>
            ) : null}
          </Stack>
        )}
      />
      <Dialog
        open={open}
        onClose={() => {
          setOpen(false);
          resetForm();
        }}
        fullWidth
        maxWidth="xs"
      >
        <DialogTitle>{editingId != null ? t('phase.editFixedAsset') : t('phase.fixedAsset')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {error ? <HelpErrorAlert message={error} /> : null}
            <TextField label={t('common.name')} value={name} onChange={(e) => setName(e.target.value)} />
            <TextField
              label={t('phase.acquisitionCost')}
              type="number"
              value={cost}
              onChange={(e) => setCost(e.target.value)}
              disabled={editingId != null}
              helperText={editingId != null ? t('phase.assetCostFixed') : undefined}
            />
            <TextField
              label={t('phase.acquisitionDate')}
              type="date"
              value={acquisitionDate}
              onChange={(e) => setAcquisitionDate(e.target.value)}
              InputLabelProps={{ shrink: true }}
              disabled={editingId != null && depreciatedAmount > 0}
            />
            <TextField
              label={t('phase.usefulLifeMonths')}
              type="number"
              value={usefulLifeMonths}
              onChange={(e) => setUsefulLifeMonths(e.target.value)}
              disabled={editingId != null && depreciatedAmount > 0}
              helperText={
                editingId != null && depreciatedAmount > 0
                  ? t('phase.assetScheduleFrozen')
                  : undefined
              }
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => {
              setOpen(false);
              resetForm();
            }}
          >
            {t('common.cancel')}
          </Button>
          <Button variant="contained" disabled={writesBlocked || !name || !cost || create.isPending} onClick={() => create.mutate()}>
            {t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>
    </PageShell>
  );
}
