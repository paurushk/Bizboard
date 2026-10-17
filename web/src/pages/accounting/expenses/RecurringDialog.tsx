import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import MenuItem from '@mui/material/MenuItem';
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
  createDueRecurringExpenses,
  createRecurringExpense,
  deleteRecurringExpense,
  listBankAccounts,
  listRecurringExpenses,
  updateRecurringExpense,
} from '@/api/resources';
import { LoadingState } from '@/components/PageState';
import { todayIso } from '@/components/billing';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { t } from '@/i18n';
import { formatMoney, toNumber } from '@/utils/money';

type Cat = { id: number; name: string };

/** Templates for expenses that repeat, and the one-click "create what is due". */
export function RecurringDialog({ open, onClose, categories, canWrite }: { open: boolean; onClose: () => void; categories: Cat[]; canWrite: boolean }) {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ['recurring-expenses'], queryFn: listRecurringExpenses, enabled: open });
  const banks = useQuery({ queryKey: ['bank-accounts'], queryFn: listBankAccounts, enabled: open });
  const [category, setCategory] = useState('');
  const [party, setParty] = useState('');
  const [amount, setAmount] = useState('');
  const [frequency, setFrequency] = useState('MONTHLY');
  const [nextDate, setNextDate] = useState(todayIso());
  const [mode, setMode] = useState<'CASH' | 'BANK'>('CASH');
  const [bank, setBank] = useState('');
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const today = todayIso();
  const due = (list.data ?? []).filter((r) => r.isActive && r.nextDate <= today);

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['recurring-expenses'] });
    void qc.invalidateQueries({ queryKey: ['expenses'] });
  };
  const add = useMutation({
    mutationFn: () =>
      createRecurringExpense({
        category: Number(category), partyName: party, amount: Number(amount), frequency, nextDate, paymentMode: mode,
        bankAccount: mode === 'BANK' && bank ? Number(bank) : null,
      }),
    onSuccess: () => { setParty(''); setAmount(''); setError(''); refresh(); },
    onError: (e) => setError(getErrorMessage(e)),
  });
  const toggle = useMutation({
    mutationFn: ({ id, isActive }: { id: number; isActive: boolean }) => updateRecurringExpense(id, { isActive }),
    onSuccess: () => { setError(''); refresh(); },
    onError: (e) => setError(getErrorMessage(e)),
  });
  const remove = useMutation({
    mutationFn: (id: number) => deleteRecurringExpense(id),
    onSuccess: () => { setError(''); refresh(); },
    onError: (e) => setError(getErrorMessage(e)),
  });
  const createDue = useMutation({
    mutationFn: () => createDueRecurringExpenses(due.map((d) => d.id)),
    onSuccess: (data) => {
      setError('');
      setInfo(t('expx.createdDue', { count: String(data.created.length), skipped: String(data.skipped.length) }));
      refresh();
    },
    onError: (e) => setError(getErrorMessage(e)),
  });

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>{t('expx.recurring')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {error ? <HelpErrorAlert message={error} /> : null}
          {info ? <Alert severity="success" onClose={() => setInfo('')}>{info}</Alert> : null}
          {due.length > 0 ? (
            <Alert
              severity="warning"
              action={canWrite ? <Button color="inherit" size="small" disabled={createDue.isPending} onClick={() => createDue.mutate()}>{t('expx.createDue', { count: String(due.length) })}</Button> : undefined}
            >
              {t('expx.dueList', { list: due.map((d) => `${d.partyName || d.categoryName} ${formatMoney(toNumber(d.amount))} (${d.nextDate})`).join('; ') })}
            </Alert>
          ) : null}
          {list.isLoading ? <LoadingState /> : (
            <Table size="small" aria-label={t('expx.recurring')}>
              <TableHead>
                <TableRow>
                  <TableCell>{t('expenses.category')}</TableCell>
                  <TableCell>{t('expenses.party')}</TableCell>
                  <TableCell align="right">{t('common.total')}</TableCell>
                  <TableCell>{t('expx.frequency')}</TableCell>
                  <TableCell>{t('expx.nextDate')}</TableCell>
                  <TableCell align="right" />
                </TableRow>
              </TableHead>
              <TableBody>
                {(list.data ?? []).length === 0 ? <TableRow><TableCell colSpan={6}>{t('expx.noRecurring')}</TableCell></TableRow> : null}
                {(list.data ?? []).map((r) => (
                  <TableRow key={r.id} sx={r.isActive ? undefined : { opacity: 0.6 }}>
                    <TableCell>{r.categoryName}</TableCell>
                    <TableCell>{r.partyName}</TableCell>
                    <TableCell align="right">{formatMoney(toNumber(r.amount))}</TableCell>
                    <TableCell>{t(`expx.freq_${r.frequency}`)}</TableCell>
                    <TableCell>{r.nextDate}</TableCell>
                    <TableCell align="right">
                      {canWrite ? (
                        <Stack direction="row" spacing={0.5} justifyContent="flex-end">
                          <Button size="small" onClick={() => toggle.mutate({ id: r.id, isActive: !r.isActive })}>
                            {r.isActive ? t('expx.pause') : t('expx.resume')}
                          </Button>
                          <Button size="small" color="error" onClick={() => remove.mutate(r.id)}>{t('common.delete')}</Button>
                        </Stack>
                      ) : null}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
          {canWrite ? (
            <Stack spacing={1}>
              <Typography variant="subtitle2">{t('expx.addRecurring')}</Typography>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
                <TextField select size="small" label={t('expenses.category')} value={category} onChange={(e) => setCategory(e.target.value)} sx={{ minWidth: 160 }}>
                  {categories.map((c) => <MenuItem key={c.id} value={String(c.id)}>{c.name}</MenuItem>)}
                </TextField>
                <TextField size="small" label={t('expenses.party')} value={party} onChange={(e) => setParty(e.target.value)} />
                <TextField size="small" type="number" label={t('common.total')} value={amount} onChange={(e) => setAmount(e.target.value)} inputProps={{ min: 0.01, step: '0.01' }} />
              </Stack>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
                <TextField select size="small" label={t('expx.frequency')} value={frequency} onChange={(e) => setFrequency(e.target.value)} sx={{ minWidth: 140 }}>
                  {['MONTHLY', 'QUARTERLY', 'YEARLY'].map((f) => <MenuItem key={f} value={f}>{t(`expx.freq_${f}`)}</MenuItem>)}
                </TextField>
                <TextField size="small" type="date" label={t('expx.nextDate')} InputLabelProps={{ shrink: true }} value={nextDate} onChange={(e) => setNextDate(e.target.value)} />
                <TextField select size="small" label={t('expenses.paymentMode')} value={mode} onChange={(e) => setMode(e.target.value as 'CASH' | 'BANK')} sx={{ minWidth: 120 }}>
                  <MenuItem value="CASH">{t('expenses.modeCash')}</MenuItem>
                  <MenuItem value="BANK">{t('expenses.modeBank')}</MenuItem>
                </TextField>
                {mode === 'BANK' ? (
                  <TextField select size="small" label={t('expenses.bankAccount')} value={bank} onChange={(e) => setBank(e.target.value)} sx={{ minWidth: 160 }}>
                    {(banks.data ?? []).map((b) => <MenuItem key={String(b.id)} value={String(b.id)}>{String(b.name)}</MenuItem>)}
                  </TextField>
                ) : null}
                <Button variant="contained" disabled={!category || !(Number(amount) > 0) || (mode === 'BANK' && !bank) || add.isPending} onClick={() => add.mutate()}>
                  {t('common.add')}
                </Button>
              </Stack>
            </Stack>
          ) : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.close')}</Button>
      </DialogActions>
    </Dialog>
  );
}
