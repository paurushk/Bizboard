import { useState } from 'react';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import FormControlLabel from '@mui/material/FormControlLabel';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import Tab from '@mui/material/Tab';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Tabs from '@mui/material/Tabs';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import * as api from '@/api/resources';
import type { CostCenterRow } from '@/api/resources';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { ErrorState, LoadingState } from '@/components/PageState';
import { useAuth } from '@/auth/AuthContext';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { PageShell } from '@/pages/phase/phaseShared';
import { codeFromName } from '@/utils/codeGen';
import { t } from '@/i18n';
import { canPostJournals } from '@/utils/permissions';
import { formatMoney, toNumber } from '@/utils/money';

type Form = { id: number | null; name: string; code: string; parent: string; isActive: boolean };
const blank: Form = { id: null, name: '', code: '', parent: '', isActive: true };

export function CostCentersPage() {
  const { user } = useAuth();
  const { writesBlocked: subscriptionBlocked } = useSubscriptionGate();
  const writesBlocked = subscriptionBlocked || !canPostJournals(user);
  const qc = useQueryClient();
  const [tab, setTab] = useState<'centres' | 'report'>('centres');
  const query = useQuery({ queryKey: ['cost-centers', 'full'], queryFn: api.listCostCentersFull });
  const [form, setForm] = useState<Form | null>(null);
  const [error, setError] = useState('');
  const [removing, setRemoving] = useState<CostCenterRow | null>(null);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const report = useQuery({
    queryKey: ['cost-centers', 'report', dateFrom, dateTo],
    queryFn: () => api.getCostCenterReport({ dateFrom, dateTo }),
    enabled: tab === 'report',
  });

  const refresh = () => void qc.invalidateQueries({ queryKey: ['cost-centers'] });
  const save = useMutation({
    mutationFn: (f: Form) => {
      const body = { name: f.name.trim(), code: (f.code || codeFromName(f.name)).trim(), parent: f.parent ? Number(f.parent) : null, isActive: f.isActive };
      return f.id === null ? api.createCostCenter(body) : api.updateCostCenter(f.id, body);
    },
    onSuccess: () => { setForm(null); setError(''); refresh(); },
    // The dialog stays open with the server's message, so a duplicate code is never a silent no-op.
    onError: (e) => setError(getErrorMessage(e)),
  });
  const toggle = useMutation({
    mutationFn: (c: CostCenterRow) => api.updateCostCenter(c.id, { isActive: !c.isActive }),
    onSuccess: () => { setError(''); refresh(); },
    onError: (e) => setError(getErrorMessage(e)),
  });
  const remove = useMutation({
    mutationFn: (c: CostCenterRow) => api.deleteCostCenter(c.id),
    onSuccess: () => { setRemoving(null); setError(''); refresh(); },
    onError: (e) => { setRemoving(null); setError(getErrorMessage(e)); },
  });

  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  const rows = query.data ?? [];
  const used = (c: CostCenterRow) => c.usage.journalLines + c.usage.invoices + c.usage.expenses;

  return (
    <PageShell
      title={t('phase.costCenters')}
      subtitle={t('phase.costCentersSubtitle')}
      actions={
        <Button variant="contained" onClick={() => { setError(''); setForm(blank); }} disabled={writesBlocked}>
          {t('sweep2.add')}
        </Button>
      }
    >
      <Tabs value={tab} onChange={(_e, v) => setTab(v)} aria-label={t('phase.costCenters')}>
        <Tab value="centres" label={t('costCentres.tabCentres')} />
        <Tab value="report" label={t('costCentres.tabReport')} />
      </Tabs>
      {error && !form ? <HelpErrorAlert message={error} /> : null}

      {tab === 'centres' ? (
        <Paper variant="outlined" sx={{ overflowX: 'auto' }}>
          <Table size="small" aria-label={t('phase.costCenters')}>
            <TableHead>
              <TableRow>
                <TableCell>{t('sweep.code')}</TableCell>
                <TableCell>{t('sweep.name')}</TableCell>
                <TableCell>{t('chart.parent')}</TableCell>
                <TableCell align="right">{t('costCentres.usage')}</TableCell>
                <TableCell>{t('common.status')}</TableCell>
                <TableCell align="right" />
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.length === 0 ? <TableRow><TableCell colSpan={6}>{t('costCentres.empty')}</TableCell></TableRow> : null}
              {rows.map((c) => (
                <TableRow key={c.id} hover sx={c.isActive ? undefined : { opacity: 0.6 }}>
                  <TableCell>{c.code}</TableCell>
                  <TableCell>{c.name}</TableCell>
                  <TableCell>{c.parentName}</TableCell>
                  <TableCell align="right">
                    {t('costCentres.usageText', { lines: String(c.usage.journalLines), invoices: String(c.usage.invoices), expenses: String(c.usage.expenses) })}
                  </TableCell>
                  <TableCell>{c.isActive ? t('chart.active') : t('chart.inactive')}</TableCell>
                  <TableCell align="right">
                    <Stack direction="row" spacing={0.5} justifyContent="flex-end">
                      <Button size="small" disabled={writesBlocked} onClick={() => { setError(''); setForm({ id: c.id, name: c.name, code: c.code, parent: c.parent ? String(c.parent) : '', isActive: c.isActive }); }}>
                        {t('common.edit')}
                      </Button>
                      <Button size="small" disabled={writesBlocked || toggle.isPending} onClick={() => toggle.mutate(c)}>
                        {c.isActive ? t('chart.deactivate') : t('chart.reactivate')}
                      </Button>
                      <Button size="small" color="error" disabled={writesBlocked || used(c) > 0} onClick={() => setRemoving(c)}>
                        {t('common.delete')}
                      </Button>
                    </Stack>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : (
        <Stack spacing={2}>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
            <TextField size="small" type="date" label={t('phase.journalFrom')} value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} InputLabelProps={{ shrink: true }} />
            <TextField size="small" type="date" label={t('phase.journalTo')} value={dateTo} onChange={(e) => setDateTo(e.target.value)} InputLabelProps={{ shrink: true }} />
          </Stack>
          {report.isLoading ? <LoadingState /> : null}
          {report.isError ? <HelpErrorAlert message={getErrorMessage(report.error)} /> : null}
          {report.data ? (
            <Paper variant="outlined" sx={{ overflowX: 'auto' }}>
              <Table size="small" aria-label={t('costCentres.tabReport')}>
                <TableHead>
                  <TableRow>
                    <TableCell>{t('phase.periodName')}</TableCell>
                    <TableCell align="right">{t('phase.fyIncome')}</TableCell>
                    <TableCell align="right">{t('phase.fyExpense')}</TableCell>
                    <TableCell align="right">{t('phase.fyNetProfit')}</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {report.data.results.map((r) => (
                    <TableRow key={String(r.costCenter)}>
                      <TableCell>{r.costCenter === null ? t('costCentres.unallocated') : `${r.code} · ${r.name}`}</TableCell>
                      <TableCell align="right">{formatMoney(toNumber(r.income))}</TableCell>
                      <TableCell align="right">{formatMoney(toNumber(r.expense))}</TableCell>
                      <TableCell align="right">{formatMoney(toNumber(r.net))}</TableCell>
                    </TableRow>
                  ))}
                  <TableRow>
                    <TableCell><strong>{t('phase.journalTotal')}</strong></TableCell>
                    <TableCell align="right"><strong>{formatMoney(toNumber(report.data.totals.income))}</strong></TableCell>
                    <TableCell align="right"><strong>{formatMoney(toNumber(report.data.totals.expense))}</strong></TableCell>
                    <TableCell align="right"><strong>{formatMoney(toNumber(report.data.totals.net))}</strong></TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </Paper>
          ) : null}
          <Typography variant="caption" color="text.secondary">{t('costCentres.reportNote')}</Typography>
        </Stack>
      )}

      <Dialog open={form !== null} onClose={() => setForm(null)} fullWidth maxWidth="xs">
        <DialogTitle>{t('sweep2.costCenter')}</DialogTitle>
        <DialogContent>
          {form ? (
            <Stack spacing={2} sx={{ mt: 1 }}>
              <TextField size="small" required label={t('sweep.name')} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              <TextField size="small" label={t('sweep.code')} value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} helperText={t('costCentres.codeHint')} />
              <TextField select size="small" label={t('chart.parent')} value={form.parent} onChange={(e) => setForm({ ...form, parent: e.target.value })}>
                <MenuItem value="">{t('costCentres.noParent')}</MenuItem>
                {rows.filter((r) => r.id !== form.id && r.isActive).map((r) => (
                  <MenuItem key={r.id} value={String(r.id)}>{r.code} · {r.name}</MenuItem>
                ))}
              </TextField>
              {form.id !== null ? (
                <FormControlLabel control={<Switch checked={form.isActive} onChange={(e) => setForm({ ...form, isActive: e.target.checked })} />} label={t('chart.active')} />
              ) : null}
              {error ? <HelpErrorAlert message={error} /> : null}
            </Stack>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setForm(null)}>{t('sweep2.cancel')}</Button>
          <Button variant="contained" disabled={writesBlocked || !form?.name.trim() || save.isPending} onClick={() => form && save.mutate(form)}>
            {t('sweep2.save')}
          </Button>
        </DialogActions>
      </Dialog>

      <ConfirmDialog
        open={removing !== null}
        title={t('costCentres.deleteTitle', { name: removing?.name ?? '' })}
        body={t('costCentres.deleteBody')}
        confirmLabel={t('common.delete')}
        confirmColor="error"
        confirming={remove.isPending}
        onClose={() => setRemoving(null)}
        onConfirm={() => removing && remove.mutate(removing)}
      />
    </PageShell>
  );
}
