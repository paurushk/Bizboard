import { Fragment, useState } from 'react';
import Accordion from '@mui/material/Accordion';
import AccordionDetails from '@mui/material/AccordionDetails';
import AccordionSummary from '@mui/material/AccordionSummary';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import * as api from '@/api/resources';
import type { CloseSummaryRow } from '@/api/resources';
import { ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';
import { useAuth } from '@/auth/AuthContext';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { isOwner } from '@/utils/permissions';
import { isGstrReportsEnabled } from '@/config/features';
import { nextIndianFyEnd } from '@/utils/fy';
import { formatMoney } from '@/utils/money';
import { PageShell, StatusChip } from '@/pages/phase/phaseShared';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { ConfirmDialog } from '@/components/ConfirmDialog';

function warningCodes(payload: unknown): string[] {
  if (!payload || typeof payload !== 'object') return [];
  const warnings = (payload as { warnings?: Array<{ code?: string }> }).warnings;
  if (!Array.isArray(warnings)) return [];
  return warnings.map((w) => String(w?.code ?? '')).filter(Boolean);
}

/** The Indian FY a date falls in, as the year it starts in (April to March). */
function currentFyStartYear(today: Date = new Date()): number {
  return today.getMonth() >= 3 ? today.getFullYear() : today.getFullYear() - 1;
}

type Pending =
  | { kind: 'SOFT_CLOSED' | 'TOGETHER'; id: number }
  | { kind: 'REOPEN'; id: number; name: string }
  | { kind: 'FY_REVERSE' };

export function PeriodsPage() {
  const { user } = useAuth();
  const owner = !!user && isOwner(user.role);
  const { writesBlocked } = useSubscriptionGate();
  const qc = useQueryClient();
  const gstrOn = isGstrReportsEnabled();
  const query = useQuery({ queryKey: ['accounting-periods', 'summary'], queryFn: () => api.getCloseSummary() });
  const [expanded, setExpanded] = useState<number | null>(null);
  const readiness = useQuery({
    queryKey: ['accounting-periods', 'readiness', expanded],
    queryFn: () => api.getCloseReadiness(expanded as number),
    enabled: expanded !== null,
  });
  const [name, setName] = useState('');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [fyYear, setFyYear] = useState(String(currentFyStartYear()));
  const [fyEnd, setFyEnd] = useState(nextIndianFyEnd());
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [warning, setWarning] = useState('');
  const [pending, setPending] = useState<Pending | null>(null);
  const [fyPreviewOpen, setFyPreviewOpen] = useState(false);
  const [typedFy, setTypedFy] = useState('');

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['accounting-periods'] });
    void qc.invalidateQueries({ queryKey: ['books-close'] });
  };
  const onError = (e: unknown) => setError(getErrorMessage(e));

  const create = useMutation({
    mutationFn: () => api.createAccountingPeriod({ name, startDate: start, endDate: end }),
    onSuccess: () => {
      setError('');
      setName('');
      setStart('');
      setEnd('');
      refresh();
    },
    onError,
  });
  const generate = useMutation({
    mutationFn: () => api.generateAccountingYear(Number(fyYear)),
    onSuccess: (data) => {
      setError('');
      setInfo(t('phase.periodsGenerated', { created: String(data.created.length), skipped: String(data.skipped.length) }));
      refresh();
    },
    onError,
  });
  const setStatus = useMutation({
    mutationFn: ({ id }: { id: number }) => api.softCloseAccountingPeriod(id),
    onSuccess: (data) => {
      setError('');
      const codes = warningCodes(data);
      setWarning(codes.includes('gst_period_open') ? t('phase.gstPeriodOpen') : '');
      refresh();
    },
    onError,
  });
  const closeTogether = useMutation({
    mutationFn: (id: number) => api.closeAccountingAndGstPeriod(id),
    onSuccess: () => {
      setError('');
      setWarning('');
      setInfo(t('phase.closedBooksAndGst'));
      refresh();
    },
    onError,
  });
  const reopen = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) => api.reopenAccountingPeriod(id, reason),
    onSuccess: () => {
      setError('');
      setInfo(t('phase.periodReopened'));
      refresh();
    },
    onError,
  });
  const preview = useQuery({
    queryKey: ['accounting-periods', 'fy-preview', fyEnd],
    queryFn: () => api.previewFinancialYearClose(fyEnd),
    enabled: fyPreviewOpen && Boolean(fyEnd),
    retry: false,
  });
  const fyClose = useMutation({
    mutationFn: () => api.closeFinancialYear({ fyEnd, confirm: true }),
    onSuccess: () => {
      setError('');
      setFyPreviewOpen(false);
      setInfo(t('phase.fyClosedDone', { date: fyEnd }));
      refresh();
    },
    onError,
  });
  const fyReverse = useMutation({
    mutationFn: (reason: string) => api.reverseFinancialYearClose({ fyEnd, reason }),
    onSuccess: () => {
      setError('');
      setFyPreviewOpen(false);
      setInfo(t('phase.fyReversedDone', { date: fyEnd }));
      refresh();
    },
    onError,
  });

  const confirmPending = (reason: string) => {
    if (!pending) return;
    if (pending.kind === 'TOGETHER') closeTogether.mutate(pending.id);
    else if (pending.kind === 'SOFT_CLOSED') setStatus.mutate({ id: pending.id });
    else if (pending.kind === 'REOPEN') reopen.mutate({ id: pending.id, reason });
    else fyReverse.mutate(reason);
    setPending(null);
  };
  const pendingCopy = !pending
    ? { title: '', body: '' }
    : pending.kind === 'SOFT_CLOSED'
      ? { title: t('phase.periodConfirmSoftTitle'), body: t('phase.confirmSoftClosePeriod') }
      : pending.kind === 'TOGETHER'
        ? { title: t('phase.periodConfirmCloseTogetherTitle'), body: t('phase.confirmClosePeriodTogether') }
        : pending.kind === 'REOPEN'
          ? { title: t('phase.periodReopenTitle', { name: pending.name }), body: t('phase.periodReopenBody') }
          : { title: t('phase.fyReverseTitle'), body: t('phase.fyReverseBody') };

  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  const rows = query.data ?? [];
  const gstStillOpen = rows.some((r) => (r.status === 'CLOSED' || r.status === 'SOFT_CLOSED') && r.gstStatus === 'OPEN');
  const earlierName = (row: CloseSummaryRow) => {
    const earlier = [...rows].reverse().find((r) => r.status === 'OPEN' && r.endDate < row.startDate);
    return earlier?.name ?? '';
  };
  const actionable = (row: CloseSummaryRow) => row.status !== 'CLOSED' || (gstrOn && row.gstStatus === 'OPEN');
  const blockedReason = (row: CloseSummaryRow): string => {
    if (row.blockedByEarlier) {
      const n = earlierName(row);
      return n ? t('phase.closeFirst', { name: n }) : t('phase.closeEarlierFirst');
    }
    if ((row.blockerCount ?? 0) > 0) return t('phase.blockersCount', { count: String(row.blockerCount) });
    return '';
  };
  const lastClosedId = [...rows].filter((r) => r.status !== 'OPEN').sort((a, b) => (a.startDate < b.startDate ? 1 : -1))[0]?.id;

  return (
    <PageShell title={t('phase.periods')} subtitle={t('phase.periodsSubtitle')}>
      <Alert severity="info">
        <Typography variant="body2">{t('phase.closeEffectSoft')}</Typography>
        <Typography variant="body2">{t('phase.closeEffectHard')}</Typography>
        <Typography variant="body2">{t('phase.closeEffectTogether')}</Typography>
      </Alert>
      {error ? <HelpErrorAlert message={error} /> : null}
      {info ? <Alert severity="success" onClose={() => setInfo('')}>{info}</Alert> : null}
      {warning ? <Alert severity="warning">{warning}</Alert> : null}
      {gstStillOpen ? <Alert severity="warning">{t('phase.gstPeriodOpen')}</Alert> : null}

      {owner ? (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} alignItems={{ md: 'center' }}>
            <Typography variant="subtitle2" sx={{ flex: 1 }}>{t('phase.createFinancialYear')}</Typography>
            <TextField
              select
              size="small"
              label={t('phase.fyStartsIn')}
              value={fyYear}
              onChange={(e) => setFyYear(e.target.value)}
              sx={{ minWidth: 160 }}
            >
              {[-1, 0, 1].map((d) => {
                const y = currentFyStartYear() + d;
                return <MenuItem key={y} value={String(y)}>{`${y}-${String((y + 1) % 100).padStart(2, '0')}`}</MenuItem>;
              })}
            </TextField>
            <Button variant="contained" disabled={writesBlocked || generate.isPending} onClick={() => generate.mutate()}>
              {t('phase.createFinancialYear')}
            </Button>
          </Stack>
        </Paper>
      ) : null}

      <TableContainer component={Paper} variant="outlined">
        <Table size="small" aria-label={t('phase.periods')}>
          <TableHead>
            <TableRow>
              <TableCell>{t('phase.periodName')}</TableCell>
              <TableCell>{t('phase.periodBooks')}</TableCell>
              <TableCell>{t('phase.periodGst')}</TableCell>
              <TableCell>{t('phase.periodReadiness')}</TableCell>
              <TableCell align="right">{t('sweep2.actions')}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.length === 0 ? (
              <TableRow><TableCell colSpan={5}>{t('phase.noPeriods')}</TableCell></TableRow>
            ) : null}
            {rows.map((row) => {
              const reason = blockedReason(row);
              const open = expanded === row.id;
              return (
                <Fragment key={row.id}>
                  <TableRow hover>
                    <TableCell>
                      <Typography variant="body2">{row.name}</Typography>
                      <Typography variant="caption" color="text.secondary">{row.startDate} – {row.endDate}</Typography>
                    </TableCell>
                    <TableCell><StatusChip value={row.status} /></TableCell>
                    <TableCell><StatusChip value={row.gstStatus} /></TableCell>
                    <TableCell>
                      {row.status === 'CLOSED' ? (
                        <Chip size="small" color="success" variant="outlined" label={t('phase.readinessClosed')} />
                      ) : row.blockedByEarlier ? (
                        <Chip size="small" variant="outlined" label={t('phase.readinessWaiting')} />
                      ) : (row.blockerCount ?? 0) > 0 ? (
                        <Button size="small" color="warning" onClick={() => setExpanded(open ? null : row.id)} aria-expanded={open}>
                          {t('phase.blockersCount', { count: String(row.blockerCount) })}
                        </Button>
                      ) : (
                        <Button size="small" color="success" onClick={() => setExpanded(open ? null : row.id)} aria-expanded={open}>
                          {t('phase.readinessReady')}
                        </Button>
                      )}
                    </TableCell>
                    <TableCell align="right">
                      {owner && actionable(row) ? (
                        <Stack direction="row" spacing={1} justifyContent="flex-end" alignItems="center">
                          {reason ? <Typography variant="caption" color="text.secondary">{reason}</Typography> : null}
                          {row.status === 'OPEN' ? (
                            <Button size="small" disabled={writesBlocked || Boolean(reason)} onClick={() => setPending({ kind: 'SOFT_CLOSED', id: row.id })}>
                              {t('phase.softClose')}
                            </Button>
                          ) : null}
                          <Button size="small" color="error" disabled={writesBlocked || closeTogether.isPending || Boolean(reason)} onClick={() => setPending({ kind: 'TOGETHER', id: row.id })}>
                            {t('phase.closePeriodTogether')}
                          </Button>
                        </Stack>
                      ) : null}
                      {owner && row.status !== 'OPEN' && row.id === lastClosedId ? (
                        <Button size="small" disabled={writesBlocked} onClick={() => setPending({ kind: 'REOPEN', id: row.id, name: row.name })}>
                          {t('phase.periodReopen')}
                        </Button>
                      ) : null}
                    </TableCell>
                  </TableRow>
                  {open ? (
                    <TableRow>
                      <TableCell colSpan={5} sx={{ bgcolor: 'action.hover' }}>
                        {readiness.isLoading ? <LoadingState /> : null}
                        {readiness.data ? (
                          <Stack spacing={0.5}>
                            {readiness.data.blockers.length === 0 && readiness.data.advisory.length === 0 ? (
                              <Typography variant="body2">{t('phase.readinessNoBlockers')}</Typography>
                            ) : null}
                            {[...readiness.data.blockers, ...readiness.data.advisory].map((b) => (
                              <Stack key={b.code} direction="row" spacing={1} alignItems="center">
                                <Chip size="small" color={b.severity === 'info' ? 'default' : 'warning'} label={b.severity === 'info' ? t('phase.advisory') : t('phase.blocker')} />
                                <Typography variant="body2" sx={{ flex: 1 }}>{b.message}</Typography>
                                <Button size="small" component={RouterLink} to={b.fixPath}>{t('phase.fix')}</Button>
                              </Stack>
                            ))}
                          </Stack>
                        ) : null}
                      </TableCell>
                    </TableRow>
                  ) : null}
                </Fragment>
              );
            })}
          </TableBody>
        </Table>
      </TableContainer>

      {owner ? (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} alignItems={{ md: 'center' }}>
            <Typography variant="subtitle2" sx={{ flex: 1 }}>{t('phase.fyCloseSection')}</Typography>
            <TextField type="date" label={t('phase.fyEnd')} size="small" InputLabelProps={{ shrink: true }} value={fyEnd} onChange={(e) => setFyEnd(e.target.value)} />
            <Button color="warning" variant="outlined" disabled={writesBlocked || !fyEnd} onClick={() => setFyPreviewOpen(true)}>
              {t('phase.closeFy')}
            </Button>
          </Stack>
        </Paper>
      ) : null}

      {owner ? (
        <Accordion disableGutters variant="outlined">
          <AccordionSummary>
            <Typography variant="body2">{t('phase.addSinglePeriod')}</Typography>
          </AccordionSummary>
          <AccordionDetails>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={1}>
              <TextField label={t('phase.periodName')} size="small" value={name} onChange={(e) => setName(e.target.value)} />
              <TextField type="date" label={t('phase.periodStart')} size="small" InputLabelProps={{ shrink: true }} value={start} onChange={(e) => setStart(e.target.value)} />
              <TextField type="date" label={t('phase.periodEnd')} size="small" InputLabelProps={{ shrink: true }} value={end} onChange={(e) => setEnd(e.target.value)} />
              <Button variant="contained" disabled={writesBlocked || !name || !start || !end || create.isPending} onClick={() => create.mutate()}>
                {t('phase.createPeriod')}
              </Button>
            </Stack>
          </AccordionDetails>
        </Accordion>
      ) : null}

      <ConfirmDialog
        open={pending !== null}
        title={pendingCopy.title}
        body={pendingCopy.body}
        confirmLabel={
          pending?.kind === 'SOFT_CLOSED'
            ? t('phase.softClose')
            : pending?.kind === 'TOGETHER'
              ? t('phase.closePeriodTogether')
              : pending?.kind === 'REOPEN'
                ? t('phase.periodReopen')
                : t('phase.fyReverse')
        }
        confirmColor={pending?.kind === 'SOFT_CLOSED' ? 'warning' : 'error'}
        requireReason={pending?.kind === 'REOPEN' || pending?.kind === 'FY_REVERSE' ? { label: t('phase.reasonLabel'), maxLength: 200 } : undefined}
        confirming={setStatus.isPending || closeTogether.isPending || reopen.isPending || fyReverse.isPending}
        onClose={() => setPending(null)}
        onConfirm={confirmPending}
      />

      <Dialog open={fyPreviewOpen} onClose={() => setFyPreviewOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{t('phase.periodConfirmFyTitle')}</DialogTitle>
        <DialogContent>
          {preview.isLoading ? <LoadingState /> : null}
          {preview.isError ? <HelpErrorAlert message={getErrorMessage(preview.error)} /> : null}
          {preview.data ? (
            <Stack spacing={1} sx={{ mt: 1 }}>
              <Typography variant="body2">{preview.data.fyStart} – {preview.data.fyEnd}</Typography>
              <Typography variant="body2">{t('phase.fyIncome')}: {formatMoney(Number(preview.data.income))}</Typography>
              <Typography variant="body2">{t('phase.fyExpense')}: {formatMoney(Number(preview.data.expense))}</Typography>
              <Typography variant="body2"><strong>{t('phase.fyNetProfit')}: {formatMoney(Number(preview.data.netProfit))}</strong></Typography>
              <Typography variant="body2">{t('phase.fyMovesTo', { account: preview.data.movesToAccount })}</Typography>
              <Typography variant="body2">{t('phase.fyLocks', { count: String(preview.data.periods.length) })}</Typography>
              {preview.data.blockers.map((b) => (
                <Alert key={b} severity="warning">{b}</Alert>
              ))}
              {preview.data.alreadyClosed ? <Alert severity="info">{t('phase.fyAlreadyClosed')}</Alert> : null}
              {!preview.data.alreadyClosed ? (
                <TextField
                  size="small"
                  label={t('phase.periodConfirmFyType')}
                  helperText={fyEnd}
                  value={typedFy}
                  onChange={(e) => setTypedFy(e.target.value)}
                />
              ) : null}
            </Stack>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setFyPreviewOpen(false)}>{t('common.cancel')}</Button>
          {preview.data?.alreadyClosed ? (
            <Button color="error" variant="outlined" disabled={writesBlocked || fyReverse.isPending} onClick={() => setPending({ kind: 'FY_REVERSE' })}>
              {t('phase.fyReverse')}
            </Button>
          ) : (
            <Button
              color="error"
              variant="contained"
              disabled={writesBlocked || !preview.data?.canClose || typedFy.trim() !== fyEnd || fyClose.isPending}
              onClick={() => fyClose.mutate()}
            >
              {t('phase.closeFy')}
            </Button>
          )}
        </DialogActions>
      </Dialog>
    </PageShell>
  );
}
