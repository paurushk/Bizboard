import { useState } from 'react';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import FormControlLabel from '@mui/material/FormControlLabel';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import TextField from '@mui/material/TextField';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import {
  createExpenseCategory,
  listAccounts,
  listExpenseCategoryAccounts,
  setExpenseCategoryAccount,
  updateExpenseCategory,
} from '@/api/resources';
import { AccountSelect } from '@/components/accounting/AccountSelect';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { t } from '@/i18n';

export type CategoryRow = { id: number; name: string; isActive: boolean; sortOrder: number };

/** Owner-only: rename, deactivate, reorder and map each expense category to its ledger. */
export function CategoryDialog({ open, onClose, categories, onAdded }: { open: boolean; onClose: () => void; categories: CategoryRow[]; onAdded: (id: number) => void }) {
  const qc = useQueryClient();
  const accounts = useQuery({ queryKey: ['accounts'], queryFn: listAccounts, enabled: open, retry: false });
  const mapping = useQuery({ queryKey: ['expense-category-accounts'], queryFn: listExpenseCategoryAccounts, enabled: open, retry: false });
  const [error, setError] = useState('');
  const [newName, setNewName] = useState('');
  const [names, setNames] = useState<Record<number, string>>({});
  const refresh = () => void qc.invalidateQueries({ queryKey: ['expense-categories'] });
  const mappedName = (id: number) => (mapping.data ?? []).find((m) => m.category === id)?.accountName;

  const setMap = useMutation({
    mutationFn: (input: { category: number; account: number }) => setExpenseCategoryAccount(input),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['expense-category-accounts'] }),
    onError: (e) => setError(getErrorMessage(e)),
  });
  const patch = useMutation({
    mutationFn: ({ id, body }: { id: number; body: { name?: string; isActive?: boolean; sortOrder?: number } }) => updateExpenseCategory(id, body),
    onSuccess: () => { setError(''); refresh(); },
    onError: (e) => setError(getErrorMessage(e)),
  });
  const add = useMutation({
    mutationFn: () => createExpenseCategory({ name: newName.trim() }),
    onSuccess: (row) => {
      setNewName('');
      refresh();
      if (row.id) onAdded(Number(row.id));
    },
    onError: (e) => setError(getErrorMessage(e)),
  });
  // Moving a category swaps its place with its neighbour; positions are rewritten so ties never happen.
  const move = (index: number, delta: -1 | 1) => {
    const other = index + delta;
    if (other < 0 || other >= categories.length) return;
    const order = categories.map((c) => c.id);
    [order[index], order[other]] = [order[other], order[index]];
    order.forEach((id, pos) => {
      const current = categories.find((c) => c.id === id)!;
      if (current.sortOrder !== pos + 1) patch.mutate({ id, body: { sortOrder: pos + 1 } });
    });
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{t('expenses.manageCategories')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {error ? <HelpErrorAlert message={error} /> : null}
          {categories.map((c, index) => {
            const name = names[c.id] ?? c.name;
            return (
              <Stack key={c.id} spacing={0.5} sx={c.isActive ? undefined : { opacity: 0.6 }}>
                <Stack direction="row" spacing={1} alignItems="center">
                  <TextField
                    size="small" fullWidth value={name} inputProps={{ 'aria-label': `${t('expx.categoryName')} ${c.name}` }}
                    onChange={(e) => setNames({ ...names, [c.id]: e.target.value })}
                  />
                  <Button size="small" disabled={!name.trim() || name.trim() === c.name || patch.isPending} onClick={() => patch.mutate({ id: c.id, body: { name: name.trim() } })}>
                    {t('common.save')}
                  </Button>
                  <Button size="small" aria-label={`${t('expx.moveUp')} ${c.name}`} disabled={index === 0} onClick={() => move(index, -1)}>▲</Button>
                  <Button size="small" aria-label={`${t('expx.moveDown')} ${c.name}`} disabled={index === categories.length - 1} onClick={() => move(index, 1)}>▼</Button>
                </Stack>
                <Stack direction="row" spacing={1} alignItems="center">
                  <AccountSelect
                    size="small"
                    accounts={accounts.data}
                    types={['EXPENSE']}
                    label={t('expenses.categoryLedger')}
                    value={String((mapping.data ?? []).find((m) => m.category === c.id)?.account ?? '')}
                    onChange={(id) => id && setMap.mutate({ category: c.id, account: Number(id) })}
                    helperText={mappedName(c.id) ? undefined : t('expenses.categoryLedgerNone')}
                    sx={{ flex: 1 }}
                  />
                  <FormControlLabel
                    control={<Switch size="small" checked={c.isActive} onChange={(e) => patch.mutate({ id: c.id, body: { isActive: e.target.checked } })} />}
                    label={t('chart.active')}
                  />
                </Stack>
              </Stack>
            );
          })}
          <Stack direction="row" spacing={1}>
            <TextField size="small" fullWidth label={t('expenses.newCategory')} value={newName} onChange={(e) => setNewName(e.target.value)} />
            <Button disabled={!newName.trim() || add.isPending} onClick={() => add.mutate()}>{t('common.add')}</Button>
          </Stack>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.close')}</Button>
      </DialogActions>
    </Dialog>
  );
}
