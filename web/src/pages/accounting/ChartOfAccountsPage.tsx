import { useMemo, useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import FormControlLabel from '@mui/material/FormControlLabel';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import * as api from '@/api/resources';
import type { ChartAccount } from '@/api/resources';
import { AccountSelect } from '@/components/accounting/AccountSelect';
import { toTree } from '@/components/accounting/chartTree';
import { AccountingBackfillBanner } from '@/components/AccountingBackfillBanner';
import { ErrorState, LoadingState } from '@/components/PageState';
import { useAuth } from '@/auth/AuthContext';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { PageShell } from '@/pages/phase/phaseShared';
import { t } from '@/i18n';
import { canPostJournals } from '@/utils/permissions';
import { formatMoney, toNumber } from '@/utils/money';

const TYPES = ['ASSET', 'LIABILITY', 'EQUITY', 'INCOME', 'EXPENSE'];

type Form = { id: number | null; code: string; name: string; type: string; parent: string; isActive: boolean };
const blank: Form = { id: null, code: '', name: '', type: 'EXPENSE', parent: '', isActive: true };

function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export function ChartOfAccountsPage() {
  const { user } = useAuth();
  const { writesBlocked: subscriptionBlocked } = useSubscriptionGate();
  const writesBlocked = subscriptionBlocked || !canPostJournals(user);
  const qc = useQueryClient();
  const [search, setSearch] = useState('');
  const [type, setType] = useState('');
  const [showInactive, setShowInactive] = useState(false);
  const [asOf, setAsOf] = useState('');
  const q = useDebouncedValue(search.trim(), 300);
  const params = useMemo(() => {
    const p: Record<string, string> = {};
    if (q) p.q = q;
    if (type) p.type = type;
    if (!showInactive) p.active = 'true';
    if (asOf) p.as_of = asOf;
    return p;
  }, [q, type, showInactive, asOf]);
  const query = useQuery({ queryKey: ['chart', params], queryFn: () => api.listChartAccounts(params) });
  const all = useQuery({ queryKey: ['accounts'], queryFn: api.listAccounts });
  const [form, setForm] = useState<Form | null>(null);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [moveFor, setMoveFor] = useState<ChartAccount | null>(null);
  const [moveTo, setMoveTo] = useState('');

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['chart'] });
    void qc.invalidateQueries({ queryKey: ['accounts'] });
  };
  const save = useMutation({
    mutationFn: (f: Form) => {
      const body = { code: f.code.trim(), name: f.name.trim(), type: f.type, parent: f.parent ? Number(f.parent) : null, isActive: f.isActive };
      return f.id === null ? api.createAccount(body) : api.updateAccount(f.id, body);
    },
    onSuccess: () => { setForm(null); setError(''); refresh(); },
    onError: (e) => setError(getErrorMessage(e)),
  });
  const toggle = useMutation({
    mutationFn: (a: ChartAccount) => api.updateAccount(a.id, { isActive: !a.isActive }),
    onSuccess: () => { setError(''); refresh(); },
    onError: (e, a) => {
      setError(getErrorMessage(e));
      if (a.isActive && toNumber(a.balance ?? 0) !== 0) setMoveFor(a);
    },
  });
  const move = useMutation({
    mutationFn: () => api.transferAccountBalance(moveFor!.id, { toAccount: Number(moveTo) }),
    onSuccess: (data) => {
      setMoveFor(null);
      setMoveTo('');
      setError('');
      setInfo(t('chart.transferDrafted', { number: data.number }));
    },
    onError: (e) => setError(getErrorMessage(e)),
  });
  const runExport = async (file: 'csv' | 'xlsx') => {
    try {
      download(await api.exportChartAccounts(params, file), `chart-of-accounts.${file}`);
    } catch (e) {
      setError(getErrorMessage(e));
    }
  };

  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  const rows = toTree(query.data ?? []);
  const editing = form !== null && form.id !== null ? (query.data ?? []).find((a) => a.id === form.id) : undefined;
  const frozen = Boolean(editing?.hasPostings);

  return (
    <PageShell
      title={t('phase.chartOfAccounts')}
      subtitle={t('phase.chartOfAccountsSubtitle')}
      actions={
        <Stack direction="row" spacing={1}>
          <Button onClick={() => void runExport('csv')}>{t('phase.journalExportCsv')}</Button>
          <Button onClick={() => void runExport('xlsx')}>{t('phase.journalExportXlsx')}</Button>
          <Button variant="contained" disabled={writesBlocked} onClick={() => { setError(''); setForm(blank); }}>
            {t('chart.addAccount')}
          </Button>
        </Stack>
      }
    >
      <AccountingBackfillBanner suppressNoChart />
      {error && !form ? <HelpErrorAlert message={error} /> : null}
      {info ? (
        <Alert severity="success" onClose={() => setInfo('')} action={<Button size="small" component={RouterLink} to="/accounting/journals">{t('chart.openJournals')}</Button>}>
          {info}
        </Alert>
      ) : null}
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1}>
        <TextField size="small" label={t('chart.search')} value={search} onChange={(e) => setSearch(e.target.value)} sx={{ flex: 1 }} />
        <TextField select size="small" label={t('common.type')} value={type} onChange={(e) => setType(e.target.value)} sx={{ minWidth: 160 }}>
          <MenuItem value="">{t('chart.allTypes')}</MenuItem>
          {TYPES.map((x) => <MenuItem key={x} value={x}>{t(`chart.type_${x}`)}</MenuItem>)}
        </TextField>
        <TextField size="small" type="date" label={t('chart.balanceAsAt')} value={asOf} onChange={(e) => setAsOf(e.target.value)} InputLabelProps={{ shrink: true }} />
        <FormControlLabel control={<Switch checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} />} label={t('chart.showInactive')} />
      </Stack>
      <Paper variant="outlined" sx={{ overflowX: 'auto' }}>
        <Table size="small" aria-label={t('phase.chartOfAccounts')}>
          <TableHead>
            <TableRow>
              <TableCell>{t('sweep.code')}</TableCell>
              <TableCell>{t('sweep.name')}</TableCell>
              <TableCell>{t('common.type')}</TableCell>
              <TableCell align="right">{t('chart.balance')}</TableCell>
              <TableCell>{t('common.status')}</TableCell>
              <TableCell align="right" />
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.length === 0 ? <TableRow><TableCell colSpan={6}>{t('phase.chartEmpty')}</TableCell></TableRow> : null}
            {rows.map((a) => {
              const bal = toNumber(a.balance ?? 0);
              return (
                <TableRow key={a.id} hover sx={a.isActive ? undefined : { opacity: 0.6 }}>
                  <TableCell>{a.code}</TableCell>
                  <TableCell sx={{ pl: 1 + a.depth * 3 }}>
                    {a.name}
                    {a.isSystem ? <Chip size="small" variant="outlined" label={t('chart.system')} sx={{ ml: 1 }} /> : null}
                  </TableCell>
                  <TableCell>{t(`chart.type_${a.type}`)}</TableCell>
                  <TableCell align="right">
                    {a.balance === null ? '—' : `${formatMoney(Math.abs(bal))} ${bal === 0 ? '' : bal > 0 ? t('chart.dr') : t('chart.cr')}`}
                  </TableCell>
                  <TableCell>{a.isActive ? t('chart.active') : t('chart.inactive')}</TableCell>
                  <TableCell align="right">
                    <Stack direction="row" spacing={0.5} justifyContent="flex-end">
                      <Button size="small" component={RouterLink} to={`/reports/day-book?account=${a.id}`} aria-label={`${t('chart.viewLedger')} ${a.code}`}>
                        {t('chart.viewLedger')}
                      </Button>
                      {!a.isSystem ? (
                        <>
                          <Button size="small" disabled={writesBlocked} onClick={() => { setError(''); setForm({ id: a.id, code: a.code, name: a.name, type: a.type, parent: a.parent ? String(a.parent) : '', isActive: a.isActive }); }}>
                            {t('common.edit')}
                          </Button>
                          <Button size="small" color={a.isActive ? 'warning' : 'primary'} disabled={writesBlocked || toggle.isPending} onClick={() => toggle.mutate(a)}>
                            {a.isActive ? t('chart.deactivate') : t('chart.reactivate')}
                          </Button>
                        </>
                      ) : null}
                    </Stack>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </Paper>

      <Dialog open={form !== null} onClose={() => setForm(null)} fullWidth maxWidth="sm">
        <DialogTitle>{form?.id === null ? t('chart.addAccount') : t('chart.editAccount')}</DialogTitle>
        <DialogContent>
          {form ? (
            <Stack spacing={2} sx={{ mt: 1 }}>
              {frozen ? <Alert severity="info">{t('chart.frozenNote')}</Alert> : null}
              <TextField size="small" required label={t('sweep.code')} value={form.code} disabled={frozen} onChange={(e) => setForm({ ...form, code: e.target.value })} />
              <TextField size="small" required label={t('sweep.name')} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              <TextField select size="small" label={t('common.type')} value={form.type} disabled={frozen} onChange={(e) => setForm({ ...form, type: e.target.value, parent: '' })}>
                {TYPES.map((x) => <MenuItem key={x} value={x}>{t(`chart.type_${x}`)}</MenuItem>)}
              </TextField>
              <AccountSelect
                accounts={(all.data ?? []).filter((a) => a.id !== form.id)}
                types={[form.type]}
                label={t('chart.parent')}
                value={form.parent}
                onChange={(id) => setForm({ ...form, parent: id })}
                size="small"
              />
              {error ? <HelpErrorAlert message={error} /> : null}
            </Stack>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setForm(null)}>{t('common.cancel')}</Button>
          <Button variant="contained" disabled={!form || !form.code.trim() || !form.name.trim() || save.isPending} onClick={() => form && save.mutate(form)}>
            {t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={moveFor !== null} onClose={() => setMoveFor(null)} fullWidth maxWidth="sm">
        <DialogTitle>{t('chart.moveBalanceTitle', { name: moveFor?.name ?? '' })}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Typography variant="body2">{t('chart.moveBalanceBody')}</Typography>
            <AccountSelect
              accounts={(all.data ?? []).filter((a) => a.id !== moveFor?.id)}
              label={t('chart.moveTo')}
              value={moveTo}
              onChange={setMoveTo}
              size="small"
            />
            {error ? <HelpErrorAlert message={error} /> : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setMoveFor(null)}>{t('common.cancel')}</Button>
          <Button variant="contained" disabled={!moveTo || move.isPending} onClick={() => move.mutate()}>{t('chart.draftTransfer')}</Button>
        </DialogActions>
      </Dialog>
    </PageShell>
  );
}
