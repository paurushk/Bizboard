import { useState } from 'react';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import MenuItem from '@mui/material/MenuItem';
import FormControlLabel from '@mui/material/FormControlLabel';
import Checkbox from '@mui/material/Checkbox';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import {
  createExpense,
  createExpenseCategory,
  findExpenseDuplicates,
  getAccountingSettings,
  listAccounts,
  listBankAccounts,
  listExpenseCategoryAccounts,
  setExpenseCategoryAccount,
  listExpenseCategoriesPage,
  listExpensesPage,
  updateExpense,
  uploadFile,
  voidExpense,
} from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { AccountSelect } from '@/components/accounting/AccountSelect';
import Alert from '@mui/material/Alert';
import Chip from '@mui/material/Chip';
import { ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';
import { asRows, DataTable, PageShell } from '@/pages/phase/phaseShared';
import { todayIso } from '@/components/billing';
import { formatMoney, toNumber } from '@/utils/money';
import { canCreatePayments, isOwner } from '@/utils/permissions';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';

type ExpenseForm = {
  expenseDate: string;
  category: string;
  partyName: string;
  amount: string;
  notes: string;
  attachment: number | null;
  paymentMode: 'CASH' | 'BANK';
  bankAccount: string;
  expenseAccount: string;
};

const LAST_BANK_KEY = 'bizboard.expenses.lastBank';

function lastBank(): string {
  try {
    return window.localStorage.getItem(LAST_BANK_KEY) ?? '';
  } catch {
    return '';
  }
}

function emptyForm(): ExpenseForm {
  return {
    expenseDate: todayIso(),
    category: '',
    partyName: '',
    amount: '',
    notes: '',
    attachment: null,
    paymentMode: 'CASH',
    bankAccount: '',
    expenseAccount: '',
  };
}

export function ExpensesPage() {
  const { user } = useAuth();
  const canWrite = canCreatePayments(user);
  // The server lets only an owner add or change expense categories (ACS-14 review R19).
  const canManageCategories = !!user && isOwner(user.role);
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
  const [voidId, setVoidId] = useState<number | null>(null);
  const [showVoided, setShowVoided] = useState(false);
  // ACS-16: a likely double entry is shown once; the second click saves anyway.
  const [dupes, setDupes] = useState<Array<{ id: number; number: string }> | null>(null);

  const query = useQuery({
    queryKey: ['expenses', category, dateFrom, dateTo, showVoided],
    queryFn: async () =>
      (
        await listExpensesPage({
          pageSize: 100,
          category: category || undefined,
          date_from: dateFrom || undefined,
          date_to: dateTo || undefined,
          include_void: showVoided ? '1' : undefined,
        })
      ).results,
  });
  const cats = useQuery({
    queryKey: ['expense-categories'],
    queryFn: async () => (await listExpenseCategoriesPage({ pageSize: 100 })).results,
  });

  const settingsQuery = useQuery({
    queryKey: ['accounting-settings'],
    queryFn: getAccountingSettings,
    retry: false,
    staleTime: 30_000,
  });
  const glActive = Boolean(
    (settingsQuery.data as Record<string, unknown> | undefined)?.expenseGlStartDate,
  );
  const formOpen = open || manageCats;
  const accountsQuery = useQuery({ queryKey: ['accounts'], queryFn: listAccounts, enabled: formOpen, retry: false });
  const banksQuery = useQuery({ queryKey: ['bank-accounts'], queryFn: listBankAccounts, enabled: open, retry: false });
  const mappingQuery = useQuery({
    queryKey: ['expense-category-accounts'],
    queryFn: listExpenseCategoryAccounts,
    enabled: formOpen,
    retry: false,
  });
  const mappedAccount = (categoryId: string) =>
    (mappingQuery.data ?? []).find((m) => String(m.category) === categoryId)?.accountName;
  const setMapping = useMutation({
    mutationFn: (input: { category: number; account: number }) => setExpenseCategoryAccount(input),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['expense-category-accounts'] }),
    onError: (err) => setError(getErrorMessage(err)),
  });
  const trySave = async () => {
    if (dupes === null) {
      try {
        const found = await findExpenseDuplicates({
          date: form.expenseDate,
          amount: Number(form.amount).toFixed(2),
          party: form.partyName.trim(),
          exclude: editingId ?? undefined,
        });
        if (found.count > 0) {
          setDupes(found.results);
          return;
        }
      } catch {
        // The check is a courtesy; never block saving because it failed.
      }
    }
    save.mutate();
  };

  const save = useMutation({
    mutationFn: () => {
      const payload: Record<string, unknown> = {
        expenseDate: form.expenseDate,
        category: Number(form.category),
        partyName: form.partyName,
        amount: Number(form.amount),
        notes: form.notes,
        paymentMode: form.paymentMode,
        bankAccount: form.paymentMode === 'BANK' && form.bankAccount ? Number(form.bankAccount) : null,
        expenseAccount: form.expenseAccount ? Number(form.expenseAccount) : null,
      };
      if (form.attachment) payload.attachment = form.attachment;
      return editingId ? updateExpense(editingId, payload) : createExpense(payload);
    },
    onSuccess: () => {
      if (form.paymentMode === 'BANK' && form.bankAccount) {
        try {
          window.localStorage.setItem(LAST_BANK_KEY, form.bankAccount);
        } catch {
          // remembering the bank is a convenience only
        }
      }
      setOpen(false);
      setEditingId(null);
      setDupes(null);
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
  const voidIt = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) => voidExpense(id, reason),
    onSuccess: () => {
      setVoidId(null);
      void qc.invalidateQueries({ queryKey: ['expenses'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const openCreate = () => {
    setEditingId(null);
    setDupes(null);
    setForm({ ...emptyForm(), bankAccount: lastBank() });
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
      paymentMode: row.paymentMode === 'BANK' ? 'BANK' : 'CASH',
      bankAccount: row.bankAccount ? String(row.bankAccount) : '',
      expenseAccount: row.expenseAccount ? String(row.expenseAccount) : '',
    });
    setDupes(null);
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
        {canManageCategories ? (
          <Button size="small" onClick={() => setManageCats(true)}>
            {t('expenses.manageCategories')}
          </Button>
        ) : null}
        <FormControlLabel
          control={<Checkbox size="small" checked={showVoided} onChange={(e) => setShowVoided(e.target.checked)} />}
          label={t('expenses.showVoided')}
        />
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
          ...(glActive
            ? [{
                key: 'postedToBooks',
                label: t('expenses.inBooks'),
                render: (row: Record<string, unknown>) =>
                  row.status === 'VOID' ? '—' : (
                    <Chip
                      size="small"
                      variant="outlined"
                      color={row.postedToBooks ? 'success' : 'warning'}
                      label={row.postedToBooks ? t('expenses.postedYes') : t('expenses.postedNo')}
                    />
                  ),
              }]
            : []),
          ...(showVoided ? [{ key: 'status', label: t('common.status'), status: true }] : []),
        ]}
        actions={
          canWrite
            ? (row) =>
                row.status === 'VOID' ? null : (
                  <Stack direction="row" spacing={1} justifyContent="flex-end">
                    <Button size="small" onClick={() => openEdit(row)}>
                      {t('common.edit')}
                    </Button>
                    <Button size="small" color="error" onClick={() => setVoidId(Number(row.id))}>
                      {t('expenses.void')}
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
            <TextField type="date" size="small" label={t('common.date')} InputLabelProps={{ shrink: true }} value={form.expenseDate} onChange={(e) => { setDupes(null); setForm((f) => ({ ...f, expenseDate: e.target.value })); }} />
            <TextField select size="small" label={t('expenses.category')} value={form.category} onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))}>
              {(cats.data ?? []).map((c) => (
                <MenuItem key={String(c.id)} value={String(c.id)}>
                  {String(c.name)}
                </MenuItem>
              ))}
            </TextField>
            <TextField size="small" label={t('expenses.party')} value={form.partyName} onChange={(e) => { setDupes(null); setForm((f) => ({ ...f, partyName: e.target.value })); }} />
            <TextField size="small" type="number" label={t('common.total')} value={form.amount} onChange={(e) => { setDupes(null); setForm((f) => ({ ...f, amount: e.target.value })); }} inputProps={{ min: 0.01, step: '0.01' }} />
            <TextField select size="small" label={t('expenses.paymentMode')} value={form.paymentMode} onChange={(e) => setForm((f) => ({ ...f, paymentMode: e.target.value as 'CASH' | 'BANK' }))}>
              <MenuItem value="CASH">{t('expenses.modeCash')}</MenuItem>
              <MenuItem value="BANK">{t('expenses.modeBank')}</MenuItem>
            </TextField>
            {form.paymentMode === 'BANK' ? (
              <TextField select size="small" required label={t('expenses.bankAccount')} value={form.bankAccount} onChange={(e) => setForm((f) => ({ ...f, bankAccount: e.target.value }))}>
                {(banksQuery.data ?? []).map((b) => (
                  <MenuItem key={String(b.id)} value={String(b.id)}>
                    {String(b.name)}
                  </MenuItem>
                ))}
              </TextField>
            ) : null}
            <AccountSelect
              size="small"
              accounts={accountsQuery.data}
              types={['EXPENSE']}
              label={t('expenses.expenseAccount')}
              value={form.expenseAccount}
              onChange={(id) => setForm((f) => ({ ...f, expenseAccount: id }))}
              helperText={t('expenses.expenseAccountAuto', {
                account: mappedAccount(form.category) ?? t('expenses.expenseAccountDefault'),
              })}
            />
            <TextField size="small" label={t('common.notes')} value={form.notes} onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))} multiline minRows={2} />
            {dupes && dupes.length > 0 ? (
              <Alert severity="warning">
                {t('expenses.duplicateWarning', { numbers: dupes.map((d) => d.number || `#${d.id}`).join(', ') })}
              </Alert>
            ) : null}
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
            disabled={
              !form.category || !(Number(form.amount) > 0) || save.isPending || uploading ||
              (form.paymentMode === 'BANK' && !form.bankAccount)
            }
            onClick={() => void trySave()}
          >
            {dupes && dupes.length > 0 ? t('expenses.saveAnyway') : t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={manageCats} onClose={() => setManageCats(false)} fullWidth maxWidth="xs">
        <DialogTitle>{t('expenses.manageCategories')}</DialogTitle>
        <DialogContent>
          <Stack spacing={1} sx={{ mt: 1 }}>
            {(cats.data ?? []).map((c) => (
              <Stack key={String(c.id)} spacing={0.5}>
                <TextField size="small" value={String(c.name)} InputProps={{ readOnly: true }} />
                <AccountSelect
                  size="small"
                  accounts={accountsQuery.data}
                  types={['EXPENSE']}
                  label={t('expenses.categoryLedger')}
                  value={String((mappingQuery.data ?? []).find((m) => m.category === Number(c.id))?.account ?? '')}
                  onChange={(id) => id && setMapping.mutate({ category: Number(c.id), account: Number(id) })}
                  helperText={mappedAccount(String(c.id)) ? undefined : t('expenses.categoryLedgerNone')}
                />
              </Stack>
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
        open={voidId !== null}
        title={t('expenses.voidTitle')}
        body={t('expenses.voidBody')}
        confirmLabel={t('expenses.voidConfirm')}
        confirmColor="error"
        confirming={voidIt.isPending}
        requireReason={{ label: t('expenses.voidReason') }}
        onClose={() => setVoidId(null)}
        onConfirm={(reason) => voidId && voidIt.mutate({ id: voidId, reason })}
      />
    </PageShell>
  );
}
