import { useState } from 'react';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import Alert from '@mui/material/Alert';
import TextField from '@mui/material/TextField';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import * as api from '@/api/resources';
import { todayIso } from '@/components/billing';
import { ErrorState, LoadingState } from '@/components/PageState';
import { asRows, DataTable, PageShell, type Row } from '@/pages/phase/phaseShared';
import { formatMoney, toNumber } from '@/utils/money';
import { t } from '@/i18n';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { useAuth } from '@/auth/AuthContext';
import { canPostJournals } from '@/utils/permissions';

const DEFAULT_USEFUL_LIFE_MONTHS = '36';

type DisposeTarget = { id: number; name: string; cost: number; depreciated: number; acquisitionDate: string };

export function FixedAssetsPage() {
  const { writesBlocked: subscriptionBlocked } = useSubscriptionGate();
  const { user } = useAuth();
  const writesBlocked = subscriptionBlocked || !canPostJournals(user);
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
  // ACS-12: disposal needs a date, the money received and where it went -- not a bare confirm.
  const [disposeTarget, setDisposeTarget] = useState<DisposeTarget | null>(null);
  const [disposalDate, setDisposalDate] = useState(todayIso());
  const [disposalProceeds, setDisposalProceeds] = useState('');
  const [receivedIn, setReceivedIn] = useState('CASH');
  const [typedName, setTypedName] = useState('');
  const banks = useQuery({ queryKey: ['bank-accounts'], queryFn: api.listBankAccounts, enabled: disposeTarget !== null });

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
    mutationFn: (target: DisposeTarget) => {
      const proceeds = Number(disposalProceeds) || 0;
      const payload: Record<string, unknown> = { confirm: true, proceeds, disposalDate };
      if (proceeds > 0) {
        if (receivedIn === 'BANK_AGGREGATE') payload.cashAccountCode = '1500';
        else if (receivedIn !== 'CASH') payload.bankAccount = Number(receivedIn);
      }
      return api.disposeFixedAsset(target.id, payload);
    },
    onSuccess: () => {
      setError('');
      setDisposeTarget(null);
      void qc.invalidateQueries({ queryKey: ['fixed-assets'] });
    },
    onError: (e) => setError(getErrorMessage(e)),
  });
  const openDispose = (row: Row) => {
    const num = (value: unknown) => toNumber(value as string | number | null | undefined);
    setDisposeTarget({
      id: Number(row.id),
      name: String(row.name ?? ''),
      cost: num(row.acquisitionCost),
      depreciated: num(row.depreciatedAmount),
      acquisitionDate: String(row.acquisitionDate ?? '').slice(0, 10),
    });
    setDisposalDate(todayIso());
    setDisposalProceeds('');
    setReceivedIn('CASH');
    setTypedName('');
    setError('');
  };
  const nbv = disposeTarget ? Math.max(0, disposeTarget.cost - disposeTarget.depreciated) : 0;
  const proceedsNumber = Number(disposalProceeds) || 0;
  const gainOrLoss = proceedsNumber - nbv;
  const disposalDateError = !disposeTarget
    ? ''
    : disposalDate > todayIso()
      ? t('phase.disposalDateFuture')
      : disposeTarget.acquisitionDate && disposalDate < disposeTarget.acquisitionDate
        ? t('phase.disposalDateBeforePurchase')
        : '';
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
      {error && !open && !disposeTarget ? <HelpErrorAlert message={error} /> : null}
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
              <Button size="small" color="error" disabled={writesBlocked} onClick={() => openDispose(row)}>
                {t('phase.assetDispose')}
              </Button>
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
          <Button variant="contained" disabled={writesBlocked || !name || !(Number(cost) > 0) || !(Number(usefulLifeMonths) >= 1) || create.isPending} onClick={() => create.mutate()}>
            {t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog open={disposeTarget !== null} onClose={() => setDisposeTarget(null)} fullWidth maxWidth="xs">
        <DialogTitle>{t('phase.disposeAssetTitle')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {disposeTarget ? (
              <Alert severity="info">{t('phase.disposeAssetBody', { name: disposeTarget.name })}</Alert>
            ) : null}
            {error ? <HelpErrorAlert message={error} /> : null}
            <TextField
              type="date"
              label={t('phase.disposalDate')}
              value={disposalDate}
              onChange={(e) => setDisposalDate(e.target.value)}
              InputLabelProps={{ shrink: true }}
              error={Boolean(disposalDateError)}
              helperText={disposalDateError || undefined}
            />
            <TextField
              type="number"
              label={t('phase.disposalProceeds')}
              value={disposalProceeds}
              onChange={(e) => setDisposalProceeds(e.target.value)}
              inputProps={{ min: 0, step: 0.01 }}
            />
            {proceedsNumber > 0 ? (
              <TextField select label={t('phase.disposalReceivedIn')} value={receivedIn} onChange={(e) => setReceivedIn(e.target.value)}>
                <MenuItem value="CASH">{t('phase.disposalCashInHand')}</MenuItem>
                <MenuItem value="BANK_AGGREGATE">{t('phase.disposalBankAggregate')}</MenuItem>
                {(banks.data ?? []).map((b) => (
                  <MenuItem key={String(b.id)} value={String(b.id)}>
                    {String(b.name)}
                  </MenuItem>
                ))}
              </TextField>
            ) : null}
            <Alert severity={gainOrLoss < 0 ? 'warning' : 'success'}>
              {t('phase.disposalNbv', { amount: formatMoney(nbv) })} ·{' '}
              {gainOrLoss > 0.004
                ? t('phase.disposalGain', { amount: formatMoney(gainOrLoss) })
                : gainOrLoss < -0.004
                  ? t('phase.disposalLoss', { amount: formatMoney(-gainOrLoss) })
                  : t('phase.disposalBreakEven')}
            </Alert>
            <TextField
              label={t('phase.disposalTypeName')}
              value={typedName}
              onChange={(e) => setTypedName(e.target.value)}
              helperText={disposeTarget?.name}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDisposeTarget(null)} disabled={dispose.isPending}>{t('common.cancel')}</Button>
          <Button
            color="error"
            variant="contained"
            disabled={
              writesBlocked || dispose.isPending || !disposeTarget || Boolean(disposalDateError) ||
              proceedsNumber < 0 || typedName.trim() !== disposeTarget.name
            }
            onClick={() => disposeTarget && dispose.mutate(disposeTarget)}
          >
            {t('phase.disposeAssetConfirm')}
          </Button>
        </DialogActions>
      </Dialog>
    </PageShell>
  );
}
