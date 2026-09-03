import { Fragment, useState } from 'react';
import Button from '@mui/material/Button';
import Collapse from '@mui/material/Collapse';
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
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import {
  applyPayRunLop,
  completePayRun,
  cancelPayRun,
  createPayRun,
  listEmployeesPage,
  listPayRunsPage,
  updatePayRun,
  type PayRun,
} from '@/api/payroll';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { StatusChip } from '@/components/StatusChip';
import { t } from '@/i18n';
import { ModuleGate, MvpModuleBanner } from '@/pages/erp/erpShared';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { formatMoney } from '@/utils/money';
import { documentStatusTone, statusLabelKey } from '@/utils/status';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';

const PAGE_SIZE = 50;

function currentPeriod(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

export function PayRunsPage() {
  return (
    <ModuleGate module="payroll" title={t('nav.payRuns')}>
      <PayRunsPageInner />
    </ModuleGate>
  );
}

function PayRunsPageInner() {
  const { writesBlocked } = useSubscriptionGate();
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<PayRun | null>(null);
  const [period, setPeriod] = useState(currentPeriod());
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lopRun, setLopRun] = useState<PayRun | null>(null);
  const [paidDays, setPaidDays] = useState<Record<number, string>>({});

  const query = useQuery({
    queryKey: ['pay-runs', page],
    queryFn: () => listPayRunsPage({ page, pageSize: PAGE_SIZE }),
  });

  const rows = query.data?.results ?? [];

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (editing) return updatePayRun(editing.id, { period });
      return createPayRun({ period });
    },
    onSuccess: () => {
      setOpen(false);
      setEditing(null);
      setPeriod(currentPeriod());
      void qc.invalidateQueries({ queryKey: ['pay-runs'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const completeMutation = useMutation({
    mutationFn: (id: number) => completePayRun(id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['pay-runs'] }),
    onError: (err) => setError(getErrorMessage(err)),
  });

  const employeesQuery = useQuery({
    queryKey: ['employees', 'lop'],
    queryFn: async () => {
      const pageSize = 200;
      const first = await listEmployeesPage({ page: 1, pageSize });
      const total = first.count ?? first.results.length;
      if (total <= pageSize) return first;
      const pages = [first];
      const lastPage = Math.ceil(total / pageSize);
      for (let p = 2; p <= lastPage; p += 1) {
        pages.push(await listEmployeesPage({ page: p, pageSize }));
      }
      return { ...first, results: pages.flatMap((page) => page.results) };
    },
    enabled: lopRun != null,
  });

  const cancelMutation = useMutation({
    mutationFn: (id: number) => cancelPayRun(id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['pay-runs'] }),
    onError: (err) => setError(getErrorMessage(err)),
  });

  const lopMutation = useMutation({
    mutationFn: () => {
      if (!lopRun) throw new Error('no run');
      const entries = Object.entries(paidDays)
        .filter(([, days]) => days.trim() !== '')
        .map(([id, days]) => ({ employee: Number(id), paidDays: days }));
      return applyPayRunLop(lopRun.id, entries);
    },
    onSuccess: () => {
      setLopRun(null);
      setPaidDays({});
      void qc.invalidateQueries({ queryKey: ['pay-runs'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const openCreate = () => {
    setEditing(null);
    setPeriod(currentPeriod());
    setOpen(true);
  };

  const openEdit = (run: PayRun) => {
    if (run.status !== 'DRAFT') return;
    setEditing(run);
    setPeriod(run.period);
    setOpen(true);
  };

  return (
    <Stack spacing={2}>
      <MvpModuleBanner module="payroll" />
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="h4">{t('nav.payRuns')}</Typography>
        <Button variant="contained" onClick={openCreate} disabled={writesBlocked}>
          {t('common.add')}
        </Button>
      </Stack>
      {error ? <HelpErrorAlert message={error} /> : null}
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {rows.length === 0 && !query.isLoading && !query.isError ? (
        <EmptyState description={t('empty.payRuns')} />
      ) : null}
      {rows.length > 0 ? (
        <Paper sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('erp.period')}</TableCell>
                <TableCell>{t('common.status')}</TableCell>
                <TableCell>{t('erp.slips')}</TableCell>
                <TableCell align="right">{t('common.actions')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((run) => (
                <Fragment key={run.id}>
                  <TableRow>
                    <TableCell>{run.period}</TableCell>
                    <TableCell>
                      <StatusChip
                        tone={documentStatusTone(run.status)}
                        labelKey={statusLabelKey(run.status)}
                      />
                    </TableCell>
                    <TableCell>
                      <Button size="small" onClick={() => setExpandedId(expandedId === run.id ? null : run.id)}>
                        {run.slips?.length ?? 0}
                      </Button>
                    </TableCell>
                    <TableCell align="right">
                      {run.status === 'DRAFT' ? (
                        <>
                          <Button size="small" onClick={() => openEdit(run)} disabled={writesBlocked}>
                            {t('common.edit')}
                          </Button>
                          <Button
                            size="small"
                            disabled={writesBlocked}
                            onClick={() => {
                              setLopRun(run);
                              setPaidDays({});
                            }}
                          >
                            {t('payroll.lop')}
                          </Button>
                          <Button
                            size="small"
                            disabled={writesBlocked || completeMutation.isPending}
                            onClick={() => {
                              if (!window.confirm(t('payroll.confirmComplete'))) return;
                              completeMutation.mutate(run.id);
                            }}
                          >
                            {t('common.complete')}
                          </Button>
                        </>
                      ) : null}
                      {run.status === 'COMPLETED' ? (
                        <Button
                          size="small"
                          color="warning"
                          disabled={writesBlocked || cancelMutation.isPending}
                          onClick={() => {
                            if (!window.confirm(t('payroll.confirmCancel'))) return;
                            cancelMutation.mutate(run.id);
                          }}
                        >
                          {t('payroll.cancelPayRun')}
                        </Button>
                      ) : null}
                    </TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell colSpan={4} sx={{ py: 0, border: 0 }}>
                      <Collapse in={expandedId === run.id} unmountOnExit>
                        {run.slips?.length ? (
                          <Table size="small">
                            <TableHead>
                              <TableRow>
                                <TableCell>{t('nav.employees')}</TableCell>
                                <TableCell align="right">{t('erp.gross')}</TableCell>
                                <TableCell align="right">PF</TableCell>
                                <TableCell align="right">ESI</TableCell>
                                <TableCell align="right">PT</TableCell>
                                <TableCell align="right">{t('erp.deductions')}</TableCell>
                                <TableCell align="right">{t('erp.net')}</TableCell>
                              </TableRow>
                            </TableHead>
                            <TableBody>
                              {run.slips.map((s) => (
                                <TableRow key={s.id}>
                                  <TableCell>{s.employeeName}</TableCell>
                                  <TableCell align="right">{formatMoney(s.gross)}</TableCell>
                                  <TableCell align="right">{formatMoney(s.pfEmployee || '0')}</TableCell>
                                  <TableCell align="right">{formatMoney(s.esiEmployee || '0')}</TableCell>
                                  <TableCell align="right">{formatMoney(s.ptAmount || '0')}</TableCell>
                                  <TableCell align="right">{formatMoney(s.deductions)}</TableCell>
                                  <TableCell align="right">{formatMoney(s.net)}</TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        ) : (
                          <Typography variant="body2" color="text.secondary" sx={{ p: 2 }}>
                            {t('erp.slipsOnComplete')}
                          </Typography>
                        )}
                      </Collapse>
                    </TableCell>
                  </TableRow>
                </Fragment>
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}
      {query.data && (query.data.next || page > 1) ? (
        <Stack direction="row" spacing={1} justifyContent="flex-end" alignItems="center">
          <Typography variant="body2" color="text.secondary">
            {t('common.page')} {page}
          </Typography>
          <Button variant="outlined" size="small" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            {t('common.previous')}
          </Button>
          <Button
            variant="outlined"
            size="small"
            disabled={!query.data.next}
            onClick={() => setPage((p) => p + 1)}
          >
            {t('common.next')}
          </Button>
        </Stack>
      ) : null}

      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>
          {editing ? t('common.edit') : t('common.create')} {t('payroll.payRun')}
        </DialogTitle>
        <DialogContent>
          <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
            <TextField
              select
              label={t('payroll.payMonth')}
              fullWidth
              value={period.slice(5, 7) || String(new Date().getMonth() + 1).padStart(2, '0')}
              onChange={(e) => setPeriod(`${period.slice(0, 4) || String(new Date().getFullYear())}-${e.target.value}`)}
            >
              {['01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12'].map((mm) => (
                <MenuItem key={mm} value={mm}>
                  {new Date(2000, Number(mm) - 1, 1).toLocaleString('en', { month: 'long' })}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label={t('payroll.calendarYear')}
              fullWidth
              value={period.slice(0, 4) || String(new Date().getFullYear())}
              onChange={(e) => setPeriod(`${e.target.value}-${period.slice(5, 7) || '01'}`)}
            >
              {Array.from({ length: 6 }, (_, i) => String(new Date().getFullYear() - 2 + i)).map((year) => (
                <MenuItem key={year} value={year}>
                  {year}
                </MenuItem>
              ))}
            </TextField>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={writesBlocked || !period || saveMutation.isPending}
            onClick={() => saveMutation.mutate()}
          >
            {t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={lopRun != null} onClose={() => setLopRun(null)} fullWidth maxWidth="sm">
        <DialogTitle>{t('payroll.lop')}</DialogTitle>
        <DialogContent>
          <Stack spacing={1} sx={{ mt: 1 }}>
            {(employeesQuery.data?.results ?? []).map((emp) => (
              <TextField
                key={emp.id}
                size="small"
                type="number"
                label={`${emp.name} — ${t('payroll.paidDays')}`}
                value={paidDays[emp.id] ?? ''}
                onChange={(e) => setPaidDays((prev) => ({ ...prev, [emp.id]: e.target.value }))}
              />
            ))}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setLopRun(null)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={writesBlocked || lopMutation.isPending}
            onClick={() => lopMutation.mutate()}
          >
            {t('payroll.saveLop')}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
