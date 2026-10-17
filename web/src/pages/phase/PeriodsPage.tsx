import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import * as api from '@/api/resources';
import { ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';
import { useAuth } from '@/auth/AuthContext';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { isOwner } from '@/utils/permissions';
import { isGstrReportsEnabled } from '@/config/features';
import { nextIndianFyEnd } from '@/utils/fy';
import { BooksCloseSection } from '@/pages/phase/BooksCloseSection';
import { asRows, DataTable, PageShell } from '@/pages/phase/phaseShared';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { ConfirmDialog } from '@/components/ConfirmDialog';

function warningCodes(payload: unknown): string[] {
  if (!payload || typeof payload !== 'object') return [];
  const warnings = (payload as { warnings?: Array<{ code?: string }> }).warnings;
  if (!Array.isArray(warnings)) return [];
  return warnings.map((w) => String(w?.code ?? '')).filter(Boolean);
}

export function PeriodsPage() {
  const { user } = useAuth();
  const owner = !!user && isOwner(user.role);
  const { writesBlocked } = useSubscriptionGate();
  const qc = useQueryClient();
  const gstrOn = isGstrReportsEnabled();
  const query = useQuery({
    queryKey: ['accounting-periods'],
    queryFn: () => api.listAccountingPeriods(),
  });
  const [name, setName] = useState('');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [fyEnd, setFyEnd] = useState(nextIndianFyEnd());
  const [error, setError] = useState('');
  const [warning, setWarning] = useState('');
  // ACS-00: irreversible closes go through the app's own dialog, not window.confirm.
  type PendingClose =
    | { kind: 'SOFT_CLOSED' | 'CLOSED' | 'TOGETHER'; id: number }
    | { kind: 'FY' };
  const [pending, setPending] = useState<PendingClose | null>(null);
  const create = useMutation({
    mutationFn: () => api.createAccountingPeriod({ name, startDate: start, endDate: end }),
    onSuccess: () => {
      setError('');
      setName('');
      setStart('');
      setEnd('');
      void qc.invalidateQueries({ queryKey: ['accounting-periods'] });
    },
    onError: (e) => setError(getErrorMessage(e)),
  });
  const setStatus = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) =>
      status === 'CLOSED' ? api.closeAccountingPeriod(id) : api.softCloseAccountingPeriod(id),
    onSuccess: (data) => {
      setError('');
      const codes = warningCodes(data);
      setWarning(codes.includes('gst_period_open') ? t('phase.gstPeriodOpen') : '');
      void qc.invalidateQueries({ queryKey: ['accounting-periods'] });
    },
    onError: (e) => setError(getErrorMessage(e)),
  });
  const closeTogether = useMutation({
    mutationFn: (id: number) => api.closeAccountingAndGstPeriod(id),
    onSuccess: () => {
      setError('');
      setWarning('');
      void qc.invalidateQueries({ queryKey: ['accounting-periods'] });
    },
    onError: (e) => setError(getErrorMessage(e)),
  });
  const fyClose = useMutation({
    mutationFn: () => api.closeFinancialYear({ fyEnd, confirm: true }),
    onSuccess: () => {
      setError('');
      void qc.invalidateQueries({ queryKey: ['accounting-periods'] });
    },
    onError: (e) => setError(getErrorMessage(e)),
  });
  const confirmPending = () => {
    if (!pending) return;
    if (pending.kind === 'FY') fyClose.mutate();
    else if (pending.kind === 'TOGETHER') closeTogether.mutate(pending.id);
    else setStatus.mutate({ id: pending.id, status: pending.kind });
    setPending(null);
  };
  const pendingCopy = !pending
    ? { title: '', body: '' }
    : pending.kind === 'SOFT_CLOSED'
      ? { title: t('phase.periodConfirmSoftTitle'), body: t('phase.confirmSoftClosePeriod') }
      : pending.kind === 'CLOSED'
        ? { title: t('phase.periodConfirmCloseTitle'), body: t('phase.confirmClosePeriod') }
        : pending.kind === 'TOGETHER'
          ? { title: t('phase.periodConfirmCloseTogetherTitle'), body: t('phase.confirmClosePeriodTogether') }
          : { title: t('phase.periodConfirmFyTitle'), body: t('phase.confirmCloseFy') };
  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  const rows = asRows(query.data);
  const gstStillOpen = rows.some((row) => {
    const status = String(row.status ?? '');
    const gst = String(row.gstPeriodStatus ?? row.gst_period_status ?? 'OPEN');
    return (status === 'CLOSED' || status === 'SOFT_CLOSED') && gst === 'OPEN';
  });
  const booksStillOpen = rows.some((row) => {
    const status = String(row.status ?? '');
    const gst = String(row.gstPeriodStatus ?? row.gst_period_status ?? '');
    return status === 'OPEN' && (gst === 'SOFT_CLOSED' || gst === 'CLOSED');
  });
  return <PageShell title={t('phase.periods')} subtitle={t('phase.periodsSubtitle')}>
    <BooksCloseSection />
    <Alert severity="info">
      <Typography variant="body2">{t('phase.closeEffectSoft')}</Typography>
      <Typography variant="body2">{t('phase.closeEffectHard')}</Typography>
    </Alert>
    {error ? <HelpErrorAlert message={error} /> : null}
    {warning ? <Alert severity="warning">{warning}</Alert> : null}
    {gstStillOpen ? <Alert severity="warning">{t('phase.gstPeriodOpen')}</Alert> : null}
    {booksStillOpen ? <Alert severity="warning">{t('phase.accountingPeriodOpen')}</Alert> : null}
    <Stack direction={{ xs: 'column', md: 'row' }} spacing={1}>
      <TextField label={t('phase.periodName')} size="small" value={name} onChange={(e) => setName(e.target.value)} />
      <TextField type="date" label={t('phase.periodStart')} size="small" InputLabelProps={{ shrink: true }} value={start} onChange={(e) => setStart(e.target.value)} />
      <TextField type="date" label={t('phase.periodEnd')} size="small" InputLabelProps={{ shrink: true }} value={end} onChange={(e) => setEnd(e.target.value)} />
      <Button variant="contained" disabled={writesBlocked || !name || !start || !end || create.isPending} onClick={() => create.mutate()}>{t('phase.createPeriod')}</Button>
      <TextField type="date" label={t('phase.fyEnd')} size="small" InputLabelProps={{ shrink: true }} value={fyEnd} onChange={(e) => setFyEnd(e.target.value)} />
      {owner ? <Button color="warning" variant="outlined" disabled={writesBlocked || !fyEnd || fyClose.isPending} onClick={() => setPending({ kind: 'FY' })}>{t('phase.closeFy')}</Button> : null}
    </Stack>
    <DataTable rows={rows} empty={t('phase.noPeriods')} columns={[
      { key: 'name', label: t('phase.periodName') }, { key: 'startDate', label: t('phase.periodStart') }, { key: 'endDate', label: t('phase.periodEnd') }, { key: 'status', label: t('phase.periodStatus'), status: true },
    ]} actions={(row) => owner && (row.status !== 'CLOSED' || (gstrOn && String(row.gstPeriodStatus ?? row.gst_period_status ?? 'OPEN') === 'OPEN')) ? <Stack direction="row" spacing={1} justifyContent="flex-end">
      {row.status === 'OPEN' ? <Button size="small" disabled={writesBlocked} onClick={() => setPending({ kind: 'SOFT_CLOSED', id: Number(row.id) })}>{t('phase.softClose')}</Button> : null}
      {row.status !== 'CLOSED' || (gstrOn && String(row.gstPeriodStatus ?? row.gst_period_status ?? 'OPEN') === 'OPEN') ? (
        <Button size="small" color="error" disabled={writesBlocked || closeTogether.isPending} onClick={() => setPending({ kind: 'TOGETHER', id: Number(row.id) })}>{t('phase.closePeriodTogether')}</Button>
      ) : null}
    </Stack> : null} />
  <ConfirmDialog
      open={pending !== null}
      title={pendingCopy.title}
      body={pendingCopy.body}
      confirmLabel={
        pending?.kind === 'SOFT_CLOSED' ? t('phase.softClose') : pending?.kind === 'CLOSED' ? t('phase.closePeriod') : pending?.kind === 'TOGETHER' ? t('phase.closePeriodTogether') : t('phase.closeFy')
      }
      confirmColor={pending?.kind === 'SOFT_CLOSED' ? 'warning' : 'error'}
      requireTyped={pending?.kind === 'FY' ? fyEnd : undefined}
      confirming={setStatus.isPending || closeTogether.isPending || fyClose.isPending}
      onClose={() => setPending(null)}
      onConfirm={confirmPending}
    />
  </PageShell>;
}
