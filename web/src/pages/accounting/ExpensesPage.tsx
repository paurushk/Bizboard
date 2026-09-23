import { useState } from 'react';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import {
  createExpense,
  createExpenseCategory,
  deleteExpense,
  listExpenseCategoriesPage,
  listExpensesPage,
  updateExpense,
  uploadFile,
} from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';
import { asRows, DataTable, PageShell } from '@/pages/phase/phaseShared';
import { todayIso } from '@/components/billing';
import { formatMoney, toNumber } from '@/utils/money';
import { canCreatePayments } from '@/utils/permissions';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';

type ExpenseForm = {
  expenseDate: string;
  category: string;
  partyName: string;
  amount: string;
  notes: string;
  attachment: number | null;
};

function emptyForm(): ExpenseForm {
  return {
    expenseDate: todayIso(),
    category: '',
    partyName: '',
    amount: '',
    notes: '',
    attachment: null,
  };
}

export function ExpensesPage() {
  const { user } = useAuth();
  const canWrite = canCreatePayments(user);
  const qc = useQueryClient();
  const [category, setCategory] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [open, setOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [manageCats, setManageCats] = useState(false);
  const [newCatName, setNewCatName] = useState('');
  const [form, setForm] = useState<ExpenseForm>(emptyForm);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deleteId, setDeleteId] = useState<number | null>(null);

  const query = useQuery({
    queryKey: ['expenses', category, dateFrom, dateTo],
    queryFn: async () =>
      (
        await listExpensesPage({
          pageSize: 100,
          category: category || undefined,
          date_from: dateFrom || undefined,
          date_to: dateTo || undefined,
        })
      ).results,
  });
  const cats = useQuery({
    queryKey: ['expense-categories'],
    queryFn: async () => (await listExpenseCategoriesPage({ pageSize: 100 })).results,
  });

  const save = useMutation({
    mutationFn: () => {
      const payload: Record<string, unknown> = {
        expenseDate: form.expenseDate,
        category: Number(form.category),
        partyName: form.partyName,
        amount: Number(form.amount),
        notes: form.notes,
      };
      if (form.attachment) payload.attachment = form.attachment;
      return editingId ? updateExpense(editingId, payload) : createExpense(payload);
    },
    onSuccess: () => {
      setOpen(false);
      setEditingId(null);
      setForm(emptyForm());
      setError(null);
      void qc.invalidateQueries({ queryKey: ['expenses'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const addCat = useMutation({
    mutationFn: () => createExpenseCategory({ name: newCatName.trim() }),
    onSuccess: (row) => {
      setNewCatName('');
      void qc.invalidateQueries({ queryKey: ['expense-categories'] });
      if (row.id) setForm((f) => ({ ...f, category: String(row.id) }));
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const remove = useMutation({
    mutationFn: (id: number) => deleteExpense(id),
    onSuccess: () => {
      setDeleteId(null);
      void qc.invalidateQueries({ queryKey: ['expenses'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const openCreate = () => {
    setEditingId(null);
    setForm(emptyForm());
    setOpen(true);
  };
  const openEdit = (row: Record<string, unknown>) => {
    setEditingId(Number(row.id));
    setForm({
      expenseDate: String(row.expenseDate ?? todayIso()).slice(0, 10),
      category: String(row.category ?? ''),
      partyName: String(row.partyName ?? ''),
      amount: String(row.amount ?? ''),
      notes: String(row.notes ?? ''),
      attachment: typeof row.attachment === 'number' ? row.attachment : null,
    });
    setOpen(true);
  };

  if (query.isLoading) return <LoadingState />;
  if (query.isError) {
    return (
      <ErrorState
        message={getErrorMessage(query.error)}
        error={query.error}
        onRetry={() => void query.refetch()}
      />
    );
  }

  return (
    <PageShell
      title={t('nav.expenses')}
      subtitle={t('expenses.subtitle')}
      actions={
        <Stack direction="row" spacing={1}>
          <Button component={RouterLink} to="/reports/day-book" variant="outlined">
            {t('nav.dayBook')}
          </Button>
          {canWrite ? (
            <Button variant="contained" onClick={openCreate}>
              {t('expenses.create')}
            </Button>
          ) : null}
        </Stack>
      }
    >
      {error ? <HelpErrorAlert message={error} onClose={() => setError(null)} /> : null}
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} flexWrap="wrap" useFlexGap>
        <TextField
          select
          size="small"
          label={t('expenses.category')}
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          sx={{ minWidth: 180 }}
        >
          <MenuItem value="">{t('common.all')}</MenuItem>
          {(cats.data ?? []).map((c) => (
            <MenuItem key={String(c.id)} value={String(c.id)}>
              {String(c.name)}
            </MenuItem>
          ))}
        </TextField>
        <TextField type="date" size="small" label={t('common.from')} InputLabelProps={{ shrink: true }} value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
        <TextField type="date" size="small" label={t('common.to')} InputLabelProps={{ shrink: true }} value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
        {canWrite ? (
          <Button size="small" onClick={() => setManageCats(true)}>
            {t('expenses.manageCategories')}
          </Button>
        ) : null}
      </Stack>
      <DataTable
        rows={asRows(query.data)}
        empty={t('expenses.empty')}
        columns={[
          { key: 'expenseDate', label: t('common.date') },
          { key: 'number', label: t('common.number') },
          { key: 'partyName', label: t('expenses.party') },
          { key: 'categoryName', label: t('expenses.category') },
          { key: 'amount', label: t('common.total'), render: (row) => formatMoney(toNumber(row.amount as string | number)) },
        ]}
        actions={
          canWrite
            ? (row) => (
                <Stack direction="row" spacing={1} justifyContent="flex-end">
                  <Button size="small" onClick={() => openEdit(row)}>
                    {t('common.edit')}
                  </Button>
                  <Button size="small" color="error" onClick={() => setDeleteId(Number(row.id))}>
                    {t('common.delete')}
                  </Button>
                </Stack>
              )
            : undefined
        }
      />

      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editingId ? t('common.edit') : t('expenses.create')}</DialogTitle>
        <DialogContent>
          <Stack spacing={1.5} sx={{ mt: 1 }}>
            <TextField type="date" size="small" label={t('common.date')} InputLabelProps={{ shrink: true }} value={form.expenseDate} onChange={(e) => setForm((f) => ({ ...f, expenseDate: e.target.value }))} />
            <TextField select size="small" label={t('expenses.category')} value={form.category} onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))}>
              {(cats.data ?? []).map((c) => (
                <MenuItem key={String(c.id)} value={String(c.id)}>
                  {String(c.name)}
                </MenuItem>
              ))}
            </TextField>
            <TextField size="small" label={t('expenses.party')} value={form.partyName} onChange={(e) => setForm((f) => ({ ...f, partyName: e.target.value }))} />
            <TextField size="small" type="number" label={t('common.total')} value={form.amount} onChange={(e) => setForm((f) => ({ ...f, amount: e.target.value }))} inputProps={{ min: 0.01, step: '0.01' }} />
            <TextField size="small" label={t('common.notes')} value={form.notes} onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))} multiline minRows={2} />
            <Stack direction="row" spacing={1} alignItems="center">
              <Button component="label" size="small" variant="outlined" disabled={uploading}>
                {t('expenses.attachment')}
                <input
                  type="file"
                  hidden
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (!file) return;
                    setUploading(true);
                    void uploadFile(file, 'ATTACHMENT')
                      .then((uploaded) => setForm((f) => ({ ...f, attachment: uploaded.id })))
                      .catch((err) => setError(getErrorMessage(err)))
                      .finally(() => setUploading(false));
                  }}
                />
              </Button>
              {form.attachment ? (
                <Typography variant="caption" color="text.secondary">
                  {t('expenses.attachment')} #{form.attachment}
                </Typography>
              ) : null}
            </Stack>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={!form.category || !(Number(form.amount) > 0) || save.isPending || uploading}
            onClick={() => save.mutate()}
          >
            {t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={manageCats} onClose={() => setManageCats(false)} fullWidth maxWidth="xs">
        <DialogTitle>{t('expenses.manageCategories')}</DialogTitle>
        <DialogContent>
          <Stack spacing={1} sx={{ mt: 1 }}>
            {(cats.data ?? []).map((c) => (
              <TextField key={String(c.id)} size="small" value={String(c.name)} InputProps={{ readOnly: true }} />
            ))}
            <Stack direction="row" spacing={1}>
              <TextField size="small" fullWidth label={t('expenses.newCategory')} value={newCatName} onChange={(e) => setNewCatName(e.target.value)} />
              <Button disabled={!newCatName.trim() || addCat.isPending} onClick={() => addCat.mutate()}>
                {t('common.add')}
              </Button>
            </Stack>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setManageCats(false)}>{t('common.close')}</Button>
        </DialogActions>
      </Dialog>

      <ConfirmDialog
        open={deleteId !== null}
        title={t('common.delete')}
        body={t('expenses.confirmDelete')}
        confirmLabel={t('common.delete')}
        confirmColor="error"
        confirming={remove.isPending}
        onClose={() => setDeleteId(null)}
        onConfirm={() => deleteId && remove.mutate(deleteId)}
      />
    </PageShell>
  );
}
