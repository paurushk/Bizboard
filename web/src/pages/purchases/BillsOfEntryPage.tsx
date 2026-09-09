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
import { t } from '@/i18n';
import { asRows, DataTable, PageShell } from '@/pages/phase/phaseShared';
import { canCancelDocuments, canCreatePurchases } from '@/utils/permissions';

function localToday() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

export function BillsOfEntryPage() {
  const { user } = useAuth();
  const { writesBlocked } = useSubscriptionGate();
  const canWrite = canCreatePurchases(user) && !writesBlocked;
  const canCancel = canCancelDocuments(user) && !writesBlocked;
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: ['bills-of-entry'],
    queryFn: async () => (await api.listBillsOfEntryPage({ pageSize: 100 })).results,
  });
  const suppliers = useQuery({
    queryKey: ['suppliers-mini'],
    queryFn: async () => (await api.listSuppliersPage({ pageSize: 100 })).results,
  });
  const [supplier, setSupplier] = useState('');
  const [boeNumber, setBoeNumber] = useState('');
  const [boeDate, setBoeDate] = useState(localToday);
  const [portCode, setPortCode] = useState('');
  const [assessableValue, setAssessableValue] = useState('');
  const [bcdAmount, setBcdAmount] = useState('');
  const [igstAmount, setIgstAmount] = useState('');
  const [cessAmount, setCessAmount] = useState('');
  const [itcEligibility, setItcEligibility] = useState('ELIGIBLE');
  const [icegateVerified, setIcegateVerified] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmCancel, setConfirmCancel] = useState<number | null>(null);
  const [pendingId, setPendingId] = useState<number | null>(null);

  const create = useMutation({
    mutationFn: () =>
      api.createBillOfEntry({
        supplier: supplier ? Number(supplier) : null,
        boeNumber,
        boeDate,
        portCode,
        assessableValue: assessableValue === '' ? 0 : Number(assessableValue),
        bcdAmount: bcdAmount === '' ? 0 : Number(bcdAmount),
        igstAmount: igstAmount === '' ? 0 : Number(igstAmount),
        cessAmount: cessAmount === '' ? 0 : Number(cessAmount),
        itcEligibility,
        icegateVerified,
      }),
    onSuccess: () => {
      setBoeNumber('');
      setPortCode('');
      setAssessableValue('');
      setBcdAmount('');
      setIgstAmount('');
      setCessAmount('');
      setError(null);
      void qc.invalidateQueries({ queryKey: ['bills-of-entry'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const complete = useMutation({
    mutationFn: (id: number) => api.completeBillOfEntry(id),
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries({ queryKey: ['bills-of-entry'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
    onSettled: () => setPendingId(null),
  });
  const cancel = useMutation({
    mutationFn: (id: number) => api.cancelBillOfEntry(id),
    onSuccess: () => {
      setError(null);
      setConfirmCancel(null);
      void qc.invalidateQueries({ queryKey: ['bills-of-entry'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
    onSettled: () => setPendingId(null),
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

  return (
    <PageShell title={t('nav.billsOfEntry')} subtitle={t('boe.subtitle')}>
      <Alert severity="info">{t('boe.linkHint')}</Alert>
      {error ? <Typography color="error" variant="body2">{error}</Typography> : null}
      {canWrite ? (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} flexWrap="wrap">
            <TextField
              select
              size="small"
              label={t('billing.supplier')}
              value={supplier}
              onChange={(e) => setSupplier(e.target.value)}
              sx={{ minWidth: 180 }}
            >
              <MenuItem value="">{t('boe.none')}</MenuItem>
              {(suppliers.data ?? []).map((s) => (
                <MenuItem key={s.id} value={s.id}>{s.name}</MenuItem>
              ))}
            </TextField>
            <TextField
              size="small"
              label={t('boe.boeNumber')}
              value={boeNumber}
              onChange={(e) => setBoeNumber(e.target.value)}
            />
            <TextField
              size="small"
              type="date"
              label={t('boe.boeDate')}
              InputLabelProps={{ shrink: true }}
              value={boeDate}
              onChange={(e) => setBoeDate(e.target.value)}
            />
            <TextField
              size="small"
              label={t('boe.portCode')}
              value={portCode}
              onChange={(e) => setPortCode(e.target.value)}
              sx={{ width: 120 }}
            />
            <TextField
              size="small"
              type="number"
              label={t('boe.assessableValue')}
              value={assessableValue}
              onChange={(e) => setAssessableValue(e.target.value)}
              inputProps={{ min: 0, step: 'any', inputMode: 'decimal' }}
              sx={{ width: 140 }}
            />
            <TextField
              size="small"
              type="number"
              label={t('boe.bcd')}
              value={bcdAmount}
              onChange={(e) => setBcdAmount(e.target.value)}
              inputProps={{ min: 0, step: 'any', inputMode: 'decimal' }}
              sx={{ width: 110 }}
            />
            <TextField
              size="small"
              type="number"
              label={t('boe.igst')}
              value={igstAmount}
              onChange={(e) => setIgstAmount(e.target.value)}
              inputProps={{ min: 0, step: 'any', inputMode: 'decimal' }}
              sx={{ width: 110 }}
            />
            <TextField
              size="small"
              type="number"
              label={t('boe.cess')}
              value={cessAmount}
              onChange={(e) => setCessAmount(e.target.value)}
              inputProps={{ min: 0, step: 'any', inputMode: 'decimal' }}
              sx={{ width: 110 }}
            />
            <TextField
              select
              size="small"
              label={t('boe.itcEligibility')}
              value={itcEligibility}
              onChange={(e) => setItcEligibility(e.target.value)}
              sx={{ minWidth: 140 }}
            >
              <MenuItem value="ELIGIBLE">{t('boe.eligible')}</MenuItem>
              <MenuItem value="INELIGIBLE">{t('boe.ineligible')}</MenuItem>
            </TextField>
            <TextField
              select
              size="small"
              label={t('boe.icegateVerified')}
              value={icegateVerified ? 'yes' : 'no'}
              onChange={(e) => setIcegateVerified(e.target.value === 'yes')}
              sx={{ minWidth: 160 }}
            >
              <MenuItem value="no">{t('common.no')}</MenuItem>
              <MenuItem value="yes">{t('common.yes')}</MenuItem>
            </TextField>
            <Button
              variant="contained"
              disabled={!boeNumber.trim() || !boeDate || create.isPending}
              onClick={() => create.mutate()}
            >
              {t('boe.create')}
            </Button>
          </Stack>
        </Paper>
      ) : null}
      <DataTable
        rows={asRows(query.data)}
        empty={t('boe.empty')}
        columns={[
          { key: 'boeNumber', label: t('boe.boeNumber') },
          { key: 'boeDate', label: t('boe.boeDate') },
          { key: 'supplierName', label: t('billing.supplier') },
          { key: 'igstAmount', label: t('boe.igst'), money: true },
          { key: 'status', label: t('common.status'), status: true },
        ]}
        actions={(row) => (
          <Stack direction="row" spacing={1} justifyContent="flex-end">
            {row.status === 'DRAFT' && canWrite ? (
              <Button
                size="small"
                disabled={pendingId !== null}
                onClick={() => {
                  setPendingId(Number(row.id));
                  complete.mutate(Number(row.id));
                }}
              >
                {pendingId === Number(row.id) && complete.isPending
                  ? t('common.loading')
                  : t('common.complete')}
              </Button>
            ) : null}
            {row.status !== 'CANCELLED' && canCancel ? (
              <Button
                size="small"
                color="warning"
                disabled={pendingId !== null}
                onClick={() => setConfirmCancel(Number(row.id))}
              >
                {t('common.cancel')}
              </Button>
            ) : null}
          </Stack>
        )}
      />
      <ConfirmDialog
        open={confirmCancel !== null}
        title={t('common.cancel')}
        body={t('boe.cancelConfirm')}
        confirmLabel={t('common.cancel')}
        confirmColor="warning"
        confirming={cancel.isPending}
        onClose={() => setConfirmCancel(null)}
        onConfirm={() => {
          const id = confirmCancel;
          if (id != null) {
            setPendingId(id);
            cancel.mutate(id);
          }
        }}
      />
    </PageShell>
  );
}
