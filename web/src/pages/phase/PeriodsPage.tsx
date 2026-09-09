import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import * as api from '@/api/resources';
import { ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { isGstrReportsEnabled } from '@/config/features';
import { nextIndianFyEnd } from '@/utils/fy';
import { asRows, DataTable, PageShell } from '@/pages/phase/phaseShared';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';

function periodMonth(row: Record<string, unknown>): string {
  const raw = String(row.startDate ?? row.start_date ?? '');
  return raw.length >= 7 ? raw.slice(0, 7) : '';
}

function warningCodes(payload: unknown): string[] {
  if (!payload || typeof payload !== 'object') return [];
  const warnings = (payload as { warnings?: Array<{ code?: string }> }).warnings;
  if (!Array.isArray(warnings)) return [];
  return warnings.map((w) => String(w?.code ?? '')).filter(Boolean);
}

export function PeriodsPage() {
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
    mutationFn: ({ id, status }: { id: number; status: string }) => {
      // F3-005: closing/soft-closing a period blocks further postings into
      // it -- same "financial action needs confirmation" treatment as Close FY.
      const message = status === 'CLOSED' ? t('phase.confirmClosePeriod') : t('phase.confirmSoftClosePeriod');
      if (!window.confirm(message)) {
        throw new Error('Cancelled');
      }
      return status === 'CLOSED' ? api.closeAccountingPeriod(id) : api.softCloseAccountingPeriod(id);
    },
    onSuccess: (data) => {
      setError('');
      const codes = warningCodes(data);
      setWarning(codes.includes('gst_period_open') ? t('phase.gstPeriodOpen') : '');
      void qc.invalidateQueries({ queryKey: ['accounting-periods'] });
    },
    onError: (e) => {
      if (getErrorMessage(e) === 'Cancelled') return;
      setError(getErrorMessage(e));
    },
  });
  const gstSoftClose = useMutation({
    mutationFn: (period: string) => {
      if (!window.confirm(t('phase.confirmSoftCloseGst'))) {
        throw new Error('Cancelled');
      }
      return api.softCloseGstPeriod(period);
    },
    onSuccess: (data) => {
      setError('');
      const codes = warningCodes(data);
      setWarning(codes.includes('accounting_period_open') ? t('phase.accountingPeriodOpen') : '');
      void qc.invalidateQueries({ queryKey: ['accounting-periods'] });
    },
    onError: (e) => {
      if (getErrorMessage(e) === 'Cancelled') return;
      setError(getErrorMessage(e));
    },
  });
  const fyClose = useMutation({
    mutationFn: () => {
      if (!window.confirm(t('phase.confirmCloseFy'))) {
        throw new Error('Cancelled');
      }
      return api.closeFinancialYear({ fyEnd, confirm: true });
    },
    onSuccess: () => {
      setError('');
      void qc.invalidateQueries({ queryKey: ['accounting-periods'] });
    },
    onError: (e) => {
      if (getErrorMessage(e) === 'Cancelled') return;
      setError(getErrorMessage(e));
    },
  });
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
      <Button color="warning" variant="outlined" disabled={writesBlocked || !fyEnd || fyClose.isPending} onClick={() => fyClose.mutate()}>{t('phase.closeFy')}</Button>
    </Stack>
    <DataTable rows={rows} empty={t('phase.noPeriods')} columns={[
      { key: 'name', label: t('phase.periodName') }, { key: 'startDate', label: t('phase.periodStart') }, { key: 'endDate', label: t('phase.periodEnd') }, { key: 'status', label: t('phase.periodStatus'), status: true },
    ]} actions={(row) => row.status !== 'CLOSED' || (gstrOn && String(row.gstPeriodStatus ?? row.gst_period_status ?? 'OPEN') === 'OPEN') ? <Stack direction="row" spacing={1} justifyContent="flex-end">
      {row.status === 'OPEN' ? <Button size="small" disabled={writesBlocked} onClick={() => setStatus.mutate({ id: Number(row.id), status: 'SOFT_CLOSED' })}>{t('phase.softClose')}</Button> : null}
      {row.status !== 'CLOSED' ? <Button size="small" color="error" disabled={writesBlocked} onClick={() => setStatus.mutate({ id: Number(row.id), status: 'CLOSED' })}>{t('phase.closePeriod')}</Button> : null}
      {gstrOn && String(row.gstPeriodStatus ?? row.gst_period_status ?? 'OPEN') === 'OPEN' && periodMonth(row) ? (
        <Button size="small" disabled={writesBlocked || gstSoftClose.isPending} onClick={() => gstSoftClose.mutate(periodMonth(row))}>{t('phase.softCloseGst')}</Button>
      ) : null}
    </Stack> : null} />
  </PageShell>;
}
