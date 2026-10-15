import { useState, type ReactNode } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Link from '@mui/material/Link';
import Stack from '@mui/material/Stack';
import IconButton from '@mui/material/IconButton';
import Menu from '@mui/material/Menu';
import Paper from '@mui/material/Paper';
import MenuItem from '@mui/material/MenuItem';
import TextField from '@mui/material/TextField';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import useMediaQuery from '@mui/material/useMediaQuery';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import type { RecurringSchedule } from '@/api/legacy/sales';
import * as api from '@/api/resources';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { ErrorState, LoadingState } from '@/components/PageState';
import { useAuth } from '@/auth/AuthContext';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { t } from '@/i18n';
import { asRows, DataTable, PageShell } from '@/pages/phase/phaseShared';
import { canCreateSales } from '@/utils/permissions';
import { RecurringRunHistoryDialog } from './recurring/RecurringRunHistoryDialog';
import { RecurringScheduleDrawer } from './recurring/RecurringScheduleDrawer';
import {
  cadenceLabel,
  formatWhen,
  fromLocalInput,
  isInFuture,
  runOutcome,
  stopStageLabel,
  toLocalInput,
  type RunOutcome,
} from './recurring/recurringHelpers';

type StatusFilter = 'all' | 'active' | 'paused';

const PAGE_SIZE = 50;

export function RecurringInvoicesPage() {
  const { user } = useAuth();
  const { writesBlocked } = useSubscriptionGate();
  const canWrite = canCreateSales(user) && !writesBlocked;
  const qc = useQueryClient();
  const [filter, setFilter] = useState<StatusFilter>('all');
  const [page, setPage] = useState(1);
  const query = useQuery({
    queryKey: ['recurring-schedules', filter, page],
    queryFn: () =>
      api.listRecurringSchedulesPage({
        page,
        pageSize: PAGE_SIZE,
        ...(filter === 'all' ? {} : { is_active: filter === 'active' ? 'true' : 'false' }),
      }),
    placeholderData: keepPreviousData,
  });
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editing, setEditing] = useState<RecurringSchedule | null>(null);
  const [historyFor, setHistoryFor] = useState<RecurringSchedule | null>(null);
  const [confirmRun, setConfirmRun] = useState<RecurringSchedule | null>(null);
  const [resumeFor, setResumeFor] = useState<RecurringSchedule | null>(null);
  const [resumeAt, setResumeAt] = useState('');
  const [deleteFor, setDeleteFor] = useState<RecurringSchedule | null>(null);
  const [menu, setMenu] = useState<{ anchor: HTMLElement; schedule: RecurringSchedule } | null>(null);
  // On a phone the table keeps Customer and Status; the actions move into a menu.
  const compact = useMediaQuery('(max-width:599.95px)');
  const [error, setError] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<RunOutcome | null>(null);
  // F2-043: remember which schedule's "Run now" is in flight so only that row's
  // button shows the pending state instead of disabling every row at once.
  const [runningId, setRunningId] = useState<number | null>(null);

  const refresh = () => void qc.invalidateQueries({ queryKey: ['recurring-schedules'] });
  const fail = (err: unknown) => setError(getErrorMessage(err));

  const runNow = useMutation({
    mutationFn: (id: number) => api.runRecurringScheduleNow(id),
    onSuccess: (result) => {
      setError(null);
      setOutcome(runOutcome(result));
      refresh();
      void qc.invalidateQueries({ queryKey: ['recurring-runs'] });
    },
    onError: fail,
    onSettled: () => setRunningId(null),
  });
  const setActive = useMutation({
    mutationFn: (vars: { id: number; isActive: boolean; nextRunAt?: string }) =>
      api.updateRecurringSchedule(vars.id, {
        isActive: vars.isActive,
        ...(vars.nextRunAt ? { nextRunAt: vars.nextRunAt } : {}),
      }),
    onSuccess: () => {
      setError(null);
      setResumeFor(null);
      refresh();
    },
    onError: fail,
  });
  const remove = useMutation({
    mutationFn: (id: number) => api.deleteRecurringSchedule(id),
    onSuccess: () => {
      setError(null);
      setDeleteFor(null);
      refresh();
    },
    onError: (err) => {
      setDeleteFor(null);
      fail(err);
    },
  });

  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;

  const shown = query.data?.results ?? [];
  const totalPages = Math.max(1, Math.ceil((query.data?.count ?? 0) / PAGE_SIZE));

  const startResume = (s: RecurringSchedule) => {
    if (isInFuture(s.nextRunAt)) {
      setActive.mutate({ id: s.id, isActive: true });
      return;
    }
    setResumeAt(toLocalInput(s.nextFutureRunAt));
    setResumeFor(s);
  };

  type ActionItem = { key: string; label: string; color?: 'warning' | 'error'; disabled?: boolean; onClick: () => void };
  const actionItems = (s: RecurringSchedule): ActionItem[] => {
    const items: ActionItem[] = [
      {
        key: 'run',
        label: runningId === s.id ? t('common.loading') : t('recurring.runNow'),
        disabled: !canWrite || runningId !== null || !s.isActive,
        onClick: () => setConfirmRun(s),
      },
      { key: 'history', label: t('recurring.history'), onClick: () => setHistoryFor(s) },
    ];
    if (canWrite) items.push({ key: 'edit', label: t('common.edit'), onClick: () => { setEditing(s); setDrawerOpen(true); } });
    if (canWrite && s.isActive) {
      items.push({ key: 'pause', label: t('recurring.deactivate'), color: 'warning', onClick: () => setActive.mutate({ id: s.id, isActive: false }) });
    }
    if (canWrite && !s.isActive) items.push({ key: 'resume', label: t('recurring.resume'), onClick: () => startResume(s) });
    if (canWrite && !s.hasRuns && !s.managedByContract) {
      items.push({ key: 'delete', label: t('recurring.deleteSchedule'), color: 'error', onClick: () => setDeleteFor(s) });
    }
    return items;
  };

  const fullColumns: Array<{ key: string; label: string; render: (row: Record<string, unknown>) => ReactNode }> = [
          {
            key: 'customerName',
            label: t('billing.customer'),
            render: (row) => {
              const s = row as unknown as RecurringSchedule;
              return (
                <Stack spacing={0.5} alignItems="flex-start">
                  <Typography variant="body2">{s.customerName}</Typography>
                  {s.managedByContract ? (
                    <Chip
                      size="small"
                      variant="outlined"
                      component={RouterLink}
                      to="/contracts"
                      clickable
                      label={t('recurring.managedByContract', { number: s.managedByContract.number })}
                    />
                  ) : null}
                  {s.customerStatus !== 'ACTIVE' ? (
                    <Chip size="small" color="warning" label={t('recurring.customerInactive')} />
                  ) : null}
                </Stack>
              );
            },
          },
          { key: 'cadence', label: t('recurring.cadence'), render: (row) => cadenceLabel(String(row.cadence)) },
          { key: 'stopStage', label: t('recurring.stopStage'), render: (row) => stopStageLabel(String(row.stopStage)) },
          { key: 'nextRunAt', label: t('recurring.nextRun'), render: (row) => formatWhen(String(row.nextRunAt)) },
          {
            key: 'totalRunsCount',
            label: t('recurring.history'),
            render: (row) => {
              const s = row as unknown as RecurringSchedule;
              return s.maxOccurrences
                ? t('recurring.runsCountOf', { count: s.totalRunsCount, max: s.maxOccurrences })
                : t('recurring.runsCount', { count: s.totalRunsCount });
            },
          },
          {
            key: 'isActive',
            label: t('common.status'),
            render: (row) => {
              const s = row as unknown as RecurringSchedule;
              return (
                <Stack direction="row" spacing={0.5} alignItems="center">
                  <Chip
                    size="small"
                    color={s.isActive ? 'success' : 'default'}
                    label={
                      s.isActive
                        ? t('recurring.statusActive')
                        : s.pausedReason === 'CONTRACT_ENDED'
                          ? t('recurring.pausedContractEnded')
                          : t('recurring.statusPaused')
                    }
                  />
                  {s.lastError ? (
                    <Tooltip title={t('recurring.lastErrorLabel', { message: s.lastError })}>
                      <WarningAmberIcon color="warning" fontSize="small" role="img" aria-label={t('recurring.lastErrorLabel', { message: s.lastError })} />
                    </Tooltip>
                  ) : null}
                </Stack>
              );
            },
          },
        ];
  return (
    <PageShell
      title={t('nav.recurringInvoices')}
      subtitle={t('recurring.subtitle')}
      actions={
        canWrite ? (
          <Button variant="contained" onClick={() => { setEditing(null); setDrawerOpen(true); }}>
            {t('recurring.newSchedule')}
          </Button>
        ) : undefined
      }
    >
      <Alert severity="info">{t('recurring.draftOnlyBanner')}</Alert>
      {error ? <Alert severity="error" onClose={() => setError(null)}>{error}</Alert> : null}
      {outcome ? (
        <Alert
          severity={outcome.severity}
          onClose={() => setOutcome(null)}
          action={
            outcome.to ? (
              <Button color="inherit" size="small" component={RouterLink} to={outcome.to}>
                {t('recurring.viewDocument')}
              </Button>
            ) : undefined
          }
        >
          {outcome.text}
        </Alert>
      ) : null}
      <ToggleButtonGroup
        size="small"
        exclusive
        value={filter}
        onChange={(_, next: StatusFilter | null) => {
          if (next) {
            setFilter(next);
            setPage(1);
          }
        }}
        aria-label={t('common.status')}
      >
        <ToggleButton value="all">{t('recurring.filterAll')}</ToggleButton>
        <ToggleButton value="active">{t('recurring.filterActive')}</ToggleButton>
        <ToggleButton value="paused">{t('recurring.filterPaused')}</ToggleButton>
      </ToggleButtonGroup>
      {compact ? (
        shown.length ? (
          <Stack spacing={1}>
            {shown.map((s) => (
              <Paper key={s.id} variant="outlined" sx={{ p: 1.5 }}>
                <Stack direction="row" spacing={1} alignItems="flex-start" justifyContent="space-between">
                  <Stack spacing={0.5} alignItems="flex-start" sx={{ minWidth: 0 }}>
                    {fullColumns[0].render(s as unknown as Record<string, unknown>)}
                    <Typography variant="caption" color="text.secondary">
                      {`${cadenceLabel(s.cadence)} · ${formatWhen(s.nextRunAt)}`}
                    </Typography>
                    {fullColumns[fullColumns.length - 1].render(s as unknown as Record<string, unknown>)}
                  </Stack>
                  <IconButton
                    size="small"
                    aria-label={`${t('common.actions')}: ${s.customerName}`}
                    onClick={(e) => setMenu({ anchor: e.currentTarget, schedule: s })}
                  >
                    <MoreVertIcon />
                  </IconButton>
                </Stack>
              </Paper>
            ))}
          </Stack>
        ) : (
          <Typography variant="body2" color="text.secondary">{t('recurring.empty')}</Typography>
        )
      ) : (
        <DataTable
          rows={asRows(shown)}
          empty={t('recurring.empty')}
          columns={fullColumns}
          actions={(row) => {
            const s = row as unknown as RecurringSchedule;
            const items = actionItems(s);
            if (compact) {
              return (
                <IconButton
                  size="small"
                  aria-label={`${t('common.actions')}: ${s.customerName}`}
                  onClick={(e) => setMenu({ anchor: e.currentTarget, schedule: s })}
                >
                  <MoreVertIcon />
                </IconButton>
              );
            }
            return (
              <Stack direction="row" spacing={1} justifyContent="flex-end" flexWrap="wrap">
                {items.map((item) => (
                  <Button key={item.key} size="small" color={item.color} disabled={item.disabled} onClick={item.onClick}>
                    {item.label}
                  </Button>
                ))}
              </Stack>
            );
          }}
        />
      )}
      {totalPages > 1 ? (
        <Stack direction="row" spacing={1} alignItems="center" justifyContent="flex-end">
          <Button size="small" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>{t('common.back')}</Button>
          <Typography variant="body2">{page} / {totalPages}</Typography>
          <Button size="small" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>{t('common.next')}</Button>
        </Stack>
      ) : null}
      <Menu anchorEl={menu?.anchor ?? null} open={menu !== null} onClose={() => setMenu(null)}>
        {(menu ? actionItems(menu.schedule) : []).map((item) => (
          <MenuItem
            key={item.key}
            disabled={item.disabled}
            onClick={() => {
              setMenu(null);
              item.onClick();
            }}
          >
            {item.label}
          </MenuItem>
        ))}
      </Menu>
      <RecurringScheduleDrawer
        open={drawerOpen}
        schedule={editing}
        onClose={() => setDrawerOpen(false)}
        onSaved={() => {
          setDrawerOpen(false);
          refresh();
        }}
      />
      <RecurringRunHistoryDialog schedule={historyFor} onClose={() => setHistoryFor(null)} />
      <ConfirmDialog
        open={confirmRun !== null}
        title={t('recurring.runNow')}
        body={
          confirmRun
            ? `${confirmRun.autoComplete && confirmRun.stopStage === 'INVOICE' ? t('recurring.runNowConfirmAuto') : t('recurring.runNowConfirm')}\n${t('recurring.runNowConfirmPeriod')}`
            : ''
        }
        confirmLabel={t('recurring.runNow')}
        confirming={runNow.isPending}
        onClose={() => setConfirmRun(null)}
        onConfirm={() => {
          const target = confirmRun;
          setConfirmRun(null);
          if (target) {
            setRunningId(target.id);
            setOutcome(null);
            runNow.mutate(target.id);
          }
        }}
      />
      <ConfirmDialog
        open={deleteFor !== null}
        title={t('recurring.deleteTitle')}
        body={t('recurring.deleteBody')}
        confirmLabel={t('recurring.deleteSchedule')}
        confirmColor="error"
        confirming={remove.isPending}
        onClose={() => setDeleteFor(null)}
        onConfirm={() => deleteFor && remove.mutate(deleteFor.id)}
      />
      <Dialog open={resumeFor !== null} onClose={() => setResumeFor(null)} aria-labelledby="recurring-resume-title">
        <DialogTitle id="recurring-resume-title">{t('recurring.resumeTitle')}</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 2 }}>{t('recurring.resumeBody')}</Typography>
          <TextField
            fullWidth
            size="small"
            type="datetime-local"
            label={t('recurring.nextRun')}
            InputLabelProps={{ shrink: true }}
            value={resumeAt}
            onChange={(e) => setResumeAt(e.target.value)}
          />
          {resumeFor?.managedByContract ? (
            <Link component={RouterLink} to="/contracts" variant="body2" sx={{ display: 'block', mt: 1 }}>
              {t('recurring.managedByContract', { number: resumeFor.managedByContract.number })}
            </Link>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setResumeFor(null)} disabled={setActive.isPending}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={!resumeAt || setActive.isPending}
            onClick={() => resumeFor && setActive.mutate({ id: resumeFor.id, isActive: true, nextRunAt: fromLocalInput(resumeAt) })}
          >
            {t('recurring.resumeConfirm')}
          </Button>
        </DialogActions>
      </Dialog>
    </PageShell>
  );
}
