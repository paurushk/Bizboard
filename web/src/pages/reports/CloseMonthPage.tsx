import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { getAccountingReport, getGstHealth } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { PageShell } from '@/pages/phase/phaseShared';
import { canViewAccountingReports, canViewGstrReports } from '@/navigation/reportAccess';
import { t } from '@/i18n';

type CheckState = 'ok' | 'warn' | 'error' | 'loading';

function previousMonth(): string {
  const d = new Date();
  d.setDate(1);
  d.setMonth(d.getMonth() - 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

function StateChip({ state, detail }: { state: CheckState; detail?: string }) {
  const color = state === 'ok' ? 'success' : state === 'warn' ? 'warning' : state === 'error' ? 'error' : 'default';
  const label =
    state === 'ok' ? t('closeMonth.stateOk')
      : state === 'warn' ? (detail ?? t('closeMonth.stateWarn'))
        : state === 'error' ? t('closeMonth.stateError')
          : t('common.loading');
  return <Chip size="small" color={color} label={label} variant={state === 'loading' ? 'outlined' : 'filled'} />;
}

function CheckRow({ title, state, detail, to, action }: { title: string; state: CheckState; detail?: string; to: string; action: string }) {
  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} justifyContent="space-between" alignItems={{ sm: 'center' }}>
        <Stack spacing={0.5}>
          <Typography fontWeight={600}>{title}</Typography>
          <StateChip state={state} detail={detail} />
        </Stack>
        <Button component={RouterLink} to={to} variant="outlined" size="small">{action}</Button>
      </Stack>
    </Paper>
  );
}

/** One entry that links books close and GST close. Postings stay separate. */
export function CloseMonthPage() {
  const { user } = useAuth();
  const [period, setPeriod] = useState(previousMonth);
  const booksOn = canViewAccountingReports(user);
  const gstOn = canViewGstrReports(user);

  const booksHealth = useQuery({
    queryKey: ['close-month', 'books-health'],
    queryFn: () => getAccountingReport('books-health'),
    enabled: booksOn,
  });
  const trialBalance = useQuery({
    queryKey: ['close-month', 'trial-balance'],
    queryFn: () => getAccountingReport('trial-balance'),
    enabled: booksOn,
  });
  const gstHealth = useQuery({
    queryKey: ['close-month', 'gst-health', period],
    queryFn: () => getGstHealth({ period }),
    enabled: gstOn && /^\d{4}-\d{2}$/.test(period),
  });

  // A check we could not run is "error", never "ok": a failed load must not read as a clean month.
  const booksState: CheckState = booksHealth.isError ? 'error' : booksHealth.isLoading ? 'loading' : 'ok';
  const alerts = ((booksHealth.data?.alerts as unknown[]) ?? []).length;
  const booksFinal: CheckState = booksState === 'ok' && alerts > 0 ? 'warn' : booksState;

  const tbState: CheckState = trialBalance.isError ? 'error' : trialBalance.isLoading ? 'loading'
    : trialBalance.data?.balanced === true ? 'ok' : 'warn';

  const summary = gstHealth.data?.summary;
  const gstIssues = (summary?.critical ?? 0) + (summary?.warning ?? 0);
  const gstState: CheckState = gstHealth.isError ? 'error' : gstHealth.isLoading ? 'loading' : gstIssues > 0 ? 'warn' : 'ok';

  return (
    <PageShell title={t('cog.closeMonth')}>
      <Typography>{t('cog.closeMonthDisclaimer')}</Typography>
      {gstOn ? (
        <TextField
          type="month"
          size="small"
          label={t('reports.period')}
          InputLabelProps={{ shrink: true }}
          value={period}
          onChange={(e) => setPeriod(e.target.value || previousMonth())}
          sx={{ maxWidth: 200 }}
        />
      ) : null}
      {booksOn ? (
        <>
          <CheckRow
            title={t('closeMonth.checkBooksHealth')}
            state={booksFinal}
            detail={t('closeMonth.issues', { count: alerts })}
            to="/reports/books-health"
            action={t('closeMonth.open')}
          />
          <CheckRow
            title={t('closeMonth.checkTrialBalance')}
            state={tbState}
            detail={t('closeMonth.notBalanced')}
            to="/reports/trial-balance"
            action={t('closeMonth.open')}
          />
        </>
      ) : (
        <Alert severity="info">{t('closeMonth.booksOff')}</Alert>
      )}
      {gstOn ? (
        <CheckRow
          title={t('closeMonth.checkGstHealth')}
          state={gstState}
          detail={t('closeMonth.issues', { count: gstIssues })}
          to="/reports/gst-health"
          action={t('closeMonth.open')}
        />
      ) : null}
      <Button component={RouterLink} to="/accounting/periods" variant="contained">{t('cog.rowBooksClose')}</Button>
      {gstOn ? (
        <>
          <Button component={RouterLink} to="/reports/gstr1" variant="outlined">{t('cog.rowGstClose')}</Button>
          <Button component={RouterLink} to="/reports/gstr3b" variant="text">{t('cog.rowGstClose')} 3B</Button>
        </>
      ) : null}
    </PageShell>
  );
}
