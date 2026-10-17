import { useRef, useState } from 'react';
import Accordion from '@mui/material/Accordion';
import AccordionDetails from '@mui/material/AccordionDetails';
import AccordionSummary from '@mui/material/AccordionSummary';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import FormControlLabel from '@mui/material/FormControlLabel';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TablePagination from '@mui/material/TablePagination';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import {
  createExpense,
  deleteFileAsset,
  downloadFileAsset,
  exportExpenses,
  findExpenseDuplicates,
  getAccountingSettings,
  listAccounts,
  listBankAccounts,
  listCostCenters,
  listExpenseCategoriesPage,
  listExpenseCategoryAccounts,
  listExpensesRegister,
  updateExpense,
  uploadFile,
  voidExpense,
} from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { AccountSelect } from '@/components/accounting/AccountSelect';
import { ErrorState, LoadingState } from '@/components/PageState';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { t } from '@/i18n';
import { PageShell, stackedTableSx } from '@/pages/phase/phaseShared';
import { CategoryDialog, type CategoryRow } from '@/pages/accounting/expenses/CategoryDialog';
import { RecurringDialog } from '@/pages/accounting/expenses/RecurringDialog';
import { todayIso } from '@/components/billing';
import { formatMoney, toNumber } from '@/utils/money';
import { canCreatePayments, isOwner } from '@/utils/permissions';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';

type GstKind = 'NONE' | 'INTRA' | 'INTER';

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
  costCenter: string;
  gstKind: GstKind;
  gstRate: string;
  gstAmount: string;
  itcEligible: boolean;
  supplierGstin: string;
  tdsSection: string;
  tdsAmount: string;
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
    costCenter: '',
    gstKind: 'NONE',
    gstRate: '',
    gstAmount: '',
    itcEligible: false,
    supplierGstin: '',
    tdsSection: '',
    tdsAmount: '',
  };
}

const pad = (n: number) => String(n).padStart(2, '0');
const iso = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

/** Date presets for the register filters. */
function presetRange(kind: 'today' | 'month' | 'lastMonth' | 'fy'): [string, string] {
  const now = new Date();
  if (kind === 'today') return [iso(now), iso(now)];
  if (kind === 'month') return [iso(new Date(now.getFullYear(), now.getMonth(), 1)), iso(new Date(now.getFullYear(), now.getMonth() + 1, 0))];
  if (kind === 'lastMonth') return [iso(new Date(now.getFullYear(), now.getMonth() - 1, 1)), iso(new Date(now.getFullYear(), now.getMonth(), 0))];
  const startYear = now.getMonth() >= 3 ? now.getFullYear() : now.getFullYear() - 1;
  return [iso(new Date(startYear, 3, 1)), iso(new Date(startYear + 1, 2, 31))];
}

function saveBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
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
  const [search, setSearch] = useState('');
  const [modeFilter, setModeFilter] = useState('');
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(50);
  const [selected, setSelected] = useState<number[]>([]);
  const [open, setOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [manageCats, setManageCats] = useState(false);
  const [recurringOpen, setRecurringOpen] = useState(false);
  const [form, setForm] = useState<ExpenseForm>(emptyForm);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [voidId, setVoidId] = useState<number | null>(null);
  const [showVoided, setShowVoided] = useState(false);
  // ACS-16: a likely double entry is shown once; the second click saves anyway.
  const [dupes, setDupes] = useState<Array<{ id: number; number: string }> | null>(null);
  // An upload made in the open dialog that no saved expense points at yet; removed again if the dialog is cancelled.
  const orphan = useRef<number | null>(null);
  const bulkInput = useRef<HTMLInputElement | null>(null);
  const q = useDebouncedValue(search.trim(), 300);

  const filterParams = {
    category: category || undefined,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
    q: q || undefined,
    payment_mode: modeFilter || undefined,
    include_void: showVoided ? '1' : undefined,
  };
  const query = useQuery({
    queryKey: ['expenses', filterParams, page, pageSize],
    queryFn: () => listExpensesRegister({ ...filterParams, page: page + 1, pageSize }),
    placeholderData: keepPreviousData,
  });
  const cats = useQuery({
    queryKey: ['expense-categories'],
    queryFn: async () => (await listExpenseCategoriesPage({ pageSize: 100 })).results,
  });
  const settingsQuery = useQuery({ queryKey: ['accounting-settings'], queryFn: getAccountingSettings, retry: false, staleTime: 30_000 });
  const glActive = Boolean((settingsQuery.data as Record<string, unknown> | undefined)?.expenseGlStartDate);
  const accountsQuery = useQuery({ queryKey: ['accounts'], queryFn: listAccounts, enabled: open, retry: false });
  const banksQuery = useQuery({ queryKey: ['bank-accounts'], queryFn: listBankAccounts, enabled: open, retry: false });
  const costCenters = useQuery({ queryKey: ['cost-centers'], queryFn: listCostCenters, enabled: open, retry: false });
  const mappingQuery = useQuery({ queryKey: ['expense-category-accounts'], queryFn: listExpenseCategoryAccounts, enabled: open, retry: false });
  const mappedAccount = (categoryId: string) => (mappingQuery.data ?? []).find((m) => String(m.category) === categoryId)?.accountName;

  const categoryRows: CategoryRow[] = (cats.data ?? []).map((c) => ({
    id: Number(c.id), name: String(c.name), isActive: c.isActive !== false, sortOrder: Number(c.sortOrder ?? 0),
  }));
  // Only live categories can be picked for a new expense; an old expense keeps showing its own.
  const pickable = categoryRows.filter((c) => c.isActive || String(c.id) === form.category);

  const closeDialog = () => {
    if (orphan.current !== null) {
      // The file was uploaded for an expense that was never saved. Removing it is best effort (owner-only on the server).
      void deleteFileAsset(orphan.current).catch(() => undefined);
      orphan.current = null;
    }
    setOpen(false);
  };

  const save = useMutation({
    mutationFn: () => {
      const gst = Number(form.gstAmount) || 0;
      const payload: Record<string, unknown> = {
        expenseDate: form.expenseDate,
        category: Number(form.category),
        partyName: form.partyName,
        amount: Number(form.amount),
        notes: form.notes,
        paymentMode: form.paymentMode,
        bankAccount: form.paymentMode === 'BANK' && form.bankAccount ? Number(form.bankAccount) : null,
        expenseAccount: form.expenseAccount ? Number(form.expenseAccount) : null,
        costCenter: form.costCenter ? Number(form.costCenter) : null,
        gstRate: Number(form.gstRate) || 0,
        cgstAmount: form.gstKind === 'INTRA' ? gst : 0,
        sgstAmount: form.gstKind === 'INTRA' ? gst : 0,
        igstAmount: form.gstKind === 'INTER' ? gst : 0,
        itcEligible: form.gstKind !== 'NONE' && form.itcEligible,
        supplierGstin: form.supplierGstin.trim().toUpperCase(),
        tdsSection: Number(form.tdsAmount) > 0 ? form.tdsSection.trim().toUpperCase() : '',
        tdsAmount: Number(form.tdsAmount) || 0,
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
      orphan.current = null;
      setOpen(false);
      setEditingId(null);
      setDupes(null);
      setForm(emptyForm());
      setError(null);
      void qc.invalidateQueries({ queryKey: ['expenses'] });
    },
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
  const voidIt = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) => voidExpense(id, reason),
    onSuccess: () => {
      setVoidId(null);
      void qc.invalidateQueries({ queryKey: ['expenses'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const bulkAttach = useMutation({
    mutationFn: async (file: File) => {
      const uploaded = await uploadFile(file, 'ATTACHMENT');
      for (const id of selected) await updateExpense(id, { attachment: uploaded.id });
    },
    onSuccess: () => {
      setSelected([]);
      setError(null);
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
    const igst = toNumber(row.igstAmount as string | number | undefined);
    const cgst = toNumber(row.cgstAmount as string | number | undefined);
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
      costCenter: row.costCenter ? String(row.costCenter) : '',
      gstKind: igst > 0 ? 'INTER' : cgst > 0 ? 'INTRA' : 'NONE',
      gstRate: row.gstRate && toNumber(row.gstRate as string) > 0 ? String(row.gstRate) : '',
      gstAmount: igst > 0 ? String(igst) : cgst > 0 ? String(cgst) : '',
      itcEligible: row.itcEligible === true,
      supplierGstin: String(row.supplierGstin ?? ''),
      tdsSection: String(row.tdsSection ?? ''),
      tdsAmount: toNumber(row.tdsAmount as string | number | undefined) > 0 ? String(row.tdsAmount) : '',
    });
    setDupes(null);
    setOpen(true);
  };
  const applyPreset = (kind: 'today' | 'month' | 'lastMonth' | 'fy') => {
    const [from, to] = presetRange(kind);
    setDateFrom(from);
    setDateTo(to);
    setPage(0);
  };
  const runExport = async (file: 'csv' | 'xlsx') => {
    try {
      saveBlob(await exportExpenses({ ...filterParams }, file), `expenses.${file}`);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };
  const openAttachment = async (id: number, name: string) => {
    try {
      saveBlob(await downloadFileAsset(id), name || `attachment-${id}`);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  if (query.isLoading) return <LoadingState />;
  if (query.isError && !query.data) {
    return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  }
  const rows = query.data?.results ?? [];
  const total = query.data?.count ?? rows.length;
  const gstTotal = Number(form.gstAmount) * (form.gstKind === 'INTRA' ? 2 : 1) || 0;
  const taxError =
    form.gstKind !== 'NONE' && gstTotal > Number(form.amount || 0)
      ? t('expx.gstTooHigh')
      : Number(form.tdsAmount) > 0 && !form.tdsSection.trim()
        ? t('expx.tdsNeedsSection')
        : form.itcEligible && form.gstKind !== 'NONE' && gstTotal > 0 && !form.supplierGstin.trim()
          ? t('expx.itcNeedsGstin')
          : '';
  const allSelected = rows.length > 0 && rows.every((r) => selected.includes(Number(r.id)));

  return (
    <PageShell
      title={t('nav.expenses')}
      subtitle={t('expenses.subtitle')}
      actions={
        <Stack direction="row" spacing={1}>
          <Button component={RouterLink} to="/reports/day-book" variant="outlined">{t('nav.dayBook')}</Button>
          <Button variant="outlined" onClick={() => setRecurringOpen(true)}>{t('expx.recurring')}</Button>
          {canWrite ? <Button variant="contained" onClick={openCreate}>{t('expenses.create')}</Button> : null}
        </Stack>
      }
    >
      {error ? <HelpErrorAlert message={error} onClose={() => setError(null)} /> : null}
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} flexWrap="wrap" useFlexGap>
        <TextField size="small" label={t('expx.search')} value={search} onChange={(e) => { setSearch(e.target.value); setPage(0); }} sx={{ minWidth: 220 }} />
        <TextField select size="small" label={t('expenses.category')} value={category} onChange={(e) => { setCategory(e.target.value); setPage(0); }} sx={{ minWidth: 160 }}>
          <MenuItem value="">{t('common.all')}</MenuItem>
          {categoryRows.map((c) => <MenuItem key={c.id} value={String(c.id)}>{c.name}</MenuItem>)}
        </TextField>
        <TextField select size="small" label={t('expenses.paymentMode')} value={modeFilter} onChange={(e) => { setModeFilter(e.target.value); setPage(0); }} sx={{ minWidth: 130 }}>
          <MenuItem value="">{t('common.all')}</MenuItem>
          <MenuItem value="CASH">{t('expenses.modeCash')}</MenuItem>
          <MenuItem value="BANK">{t('expenses.modeBank')}</MenuItem>
        </TextField>
        <TextField type="date" size="small" label={t('common.from')} InputLabelProps={{ shrink: true }} value={dateFrom} onChange={(e) => { setDateFrom(e.target.value); setPage(0); }} />
        <TextField type="date" size="small" label={t('common.to')} InputLabelProps={{ shrink: true }} value={dateTo} onChange={(e) => { setDateTo(e.target.value); setPage(0); }} />
      </Stack>
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
        <Chip size="small" label={t('expx.presetToday')} onClick={() => applyPreset('today')} />
        <Chip size="small" label={t('expx.presetMonth')} onClick={() => applyPreset('month')} />
        <Chip size="small" label={t('expx.presetLastMonth')} onClick={() => applyPreset('lastMonth')} />
        <Chip size="small" label={t('expx.presetFy')} onClick={() => applyPreset('fy')} />
        <Button size="small" onClick={() => { setDateFrom(''); setDateTo(''); setPage(0); }}>{t('expx.clearDates')}</Button>
        {canManageCategories ? <Button size="small" onClick={() => setManageCats(true)}>{t('expenses.manageCategories')}</Button> : null}
        <FormControlLabel control={<Checkbox size="small" checked={showVoided} onChange={(e) => { setShowVoided(e.target.checked); setPage(0); }} />} label={t('expenses.showVoided')} />
        <Button size="small" onClick={() => void runExport('csv')}>{t('phase.journalExportCsv')}</Button>
        <Button size="small" onClick={() => void runExport('xlsx')}>{t('phase.journalExportXlsx')}</Button>
      </Stack>
      <Typography variant="body2" data-testid="expense-register-total">
        {t('expx.registerTotal', { count: String(total), total: formatMoney(toNumber(query.data?.filteredTotal ?? '0')) })}
      </Typography>
      {canWrite && selected.length > 0 ? (
        <Alert
          severity="info"
          action={
            <Button color="inherit" size="small" disabled={bulkAttach.isPending} onClick={() => bulkInput.current?.click()}>
              {t('expx.attachToSelected', { count: String(selected.length) })}
            </Button>
          }
        >
          {t('expx.selectedCount', { count: String(selected.length) })}
          <input
            ref={bulkInput} type="file" hidden data-testid="bulk-attach-input"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) bulkAttach.mutate(file);
              e.target.value = '';
            }}
          />
        </Alert>
      ) : null}
      <Paper variant="outlined" sx={{ overflowX: 'auto' }}>
        <Table size="small" aria-label={t('nav.expenses')} sx={stackedTableSx}>
          <TableHead>
            <TableRow>
              {canWrite ? (
                <TableCell padding="checkbox">
                  <Checkbox size="small" checked={allSelected} onChange={(e) => setSelected(e.target.checked ? rows.map((r) => Number(r.id)) : [])} inputProps={{ 'aria-label': t('expx.selectAll') }} />
                </TableCell>
              ) : null}
              <TableCell>{t('common.date')}</TableCell>
              <TableCell>{t('common.number')}</TableCell>
              <TableCell>{t('expenses.party')}</TableCell>
              <TableCell>{t('expenses.category')}</TableCell>
              <TableCell align="right">{t('common.total')}</TableCell>
              {glActive ? <TableCell>{t('expenses.inBooks')}</TableCell> : null}
              {showVoided ? <TableCell>{t('common.status')}</TableCell> : null}
              <TableCell>{t('expenses.attachment')}</TableCell>
              <TableCell align="right" />
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.length === 0 ? <TableRow><TableCell colSpan={10}>{t('expenses.empty')}</TableCell></TableRow> : null}
            {rows.map((row) => {
              const id = Number(row.id);
              return (
                <TableRow key={id} hover selected={selected.includes(id)}>
                  {canWrite ? (
                    <TableCell padding="checkbox" data-label="">
                      <Checkbox size="small" checked={selected.includes(id)} onChange={() => setSelected(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id])} inputProps={{ 'aria-label': `${t('phase.reconPick')} ${String(row.number)}` }} />
                    </TableCell>
                  ) : null}
                  <TableCell data-label={t('common.date')}>{String(row.expenseDate)}</TableCell>
                  <TableCell data-label={t('common.number')}>{String(row.number)}</TableCell>
                  <TableCell data-label={t('expenses.party')}>{String(row.partyName ?? '')}</TableCell>
                  <TableCell data-label={t('expenses.category')}>{String(row.categoryName ?? '')}</TableCell>
                  <TableCell align="right" data-label={t('common.total')}>{formatMoney(toNumber(row.amount as string | number))}</TableCell>
                  {glActive ? (
                    <TableCell data-label={t('expenses.inBooks')}>
                      {row.status === 'VOID' ? '—' : (
                        <Chip size="small" variant="outlined" color={row.postedToBooks ? 'success' : 'warning'} label={row.postedToBooks ? t('expenses.postedYes') : t('expenses.postedNo')} />
                      )}
                    </TableCell>
                  ) : null}
                  {showVoided ? <TableCell>{row.status === 'VOID' ? t('status.VOID') : t('chart.active')}</TableCell> : null}
                  <TableCell data-label={t('expenses.attachment')}>
                    {row.attachment ? (
                      <Button size="small" onClick={() => void openAttachment(Number(row.attachment), String(row.attachmentName ?? ''))}>
                        {String(row.attachmentName || t('expx.openAttachment'))}
                      </Button>
                    ) : null}
                  </TableCell>
                  <TableCell align="right" data-label="">
                    {canWrite && row.status !== 'VOID' ? (
                      <Stack direction="row" spacing={1} justifyContent="flex-end">
                        <Button size="small" onClick={() => openEdit(row)}>{t('common.edit')}</Button>
                        <Button size="small" color="error" onClick={() => setVoidId(id)}>{t('expenses.void')}</Button>
                      </Stack>
                    ) : null}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
        <TablePagination
          component="div" count={total} page={page} rowsPerPage={pageSize} rowsPerPageOptions={[25, 50, 100]}
          onPageChange={(_e, p) => setPage(p)} onRowsPerPageChange={(e) => { setPageSize(Number(e.target.value)); setPage(0); }}
        />
      </Paper>

      <Dialog open={open} onClose={closeDialog} fullWidth maxWidth="sm">
        <DialogTitle>{editingId ? t('common.edit') : t('expenses.create')}</DialogTitle>
        <DialogContent>
          <Stack spacing={1.5} sx={{ mt: 1 }}>
            <TextField type="date" size="small" label={t('common.date')} InputLabelProps={{ shrink: true }} value={form.expenseDate} onChange={(e) => { setDupes(null); setForm((f) => ({ ...f, expenseDate: e.target.value })); }} />
            <TextField select size="small" label={t('expenses.category')} value={form.category} onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))}>
              {pickable.map((c) => <MenuItem key={c.id} value={String(c.id)}>{c.name}</MenuItem>)}
            </TextField>
            <TextField size="small" label={t('expenses.party')} value={form.partyName} onChange={(e) => { setDupes(null); setForm((f) => ({ ...f, partyName: e.target.value })); }} />
            <TextField size="small" type="number" label={t('common.total')} value={form.amount} onChange={(e) => { setDupes(null); setForm((f) => ({ ...f, amount: e.target.value })); }} inputProps={{ min: 0.01, step: '0.01' }} />
            <TextField select size="small" label={t('expenses.paymentMode')} value={form.paymentMode} onChange={(e) => setForm((f) => ({ ...f, paymentMode: e.target.value as 'CASH' | 'BANK' }))}>
              <MenuItem value="CASH">{t('expenses.modeCash')}</MenuItem>
              <MenuItem value="BANK">{t('expenses.modeBank')}</MenuItem>
            </TextField>
            {form.paymentMode === 'BANK' ? (
              <TextField select size="small" required label={t('expenses.bankAccount')} value={form.bankAccount} onChange={(e) => setForm((f) => ({ ...f, bankAccount: e.target.value }))}>
                {(banksQuery.data ?? []).map((b) => <MenuItem key={String(b.id)} value={String(b.id)}>{String(b.name)}</MenuItem>)}
              </TextField>
            ) : null}
            <AccountSelect
              size="small"
              accounts={accountsQuery.data}
              types={['EXPENSE']}
              label={t('expenses.expenseAccount')}
              value={form.expenseAccount}
              onChange={(id) => setForm((f) => ({ ...f, expenseAccount: id }))}
              helperText={t('expenses.expenseAccountAuto', { account: mappedAccount(form.category) ?? t('expenses.expenseAccountDefault') })}
            />
            <TextField select size="small" label={t('phase.journalCostCenter')} value={form.costCenter} onChange={(e) => setForm((f) => ({ ...f, costCenter: e.target.value }))}>
              <MenuItem value="">{t('phase.journalNoCostCenter')}</MenuItem>
              {(costCenters.data ?? []).filter((c) => c.isActive !== false).map((c) => (
                <MenuItem key={String(c.id)} value={String(c.id)}>{String(c.code)} · {String(c.name)}</MenuItem>
              ))}
            </TextField>
            <Accordion disableGutters variant="outlined" defaultExpanded={form.gstKind !== 'NONE' || Number(form.tdsAmount) > 0}>
              <AccordionSummary><Typography variant="body2">{t('expx.taxSection')}</Typography></AccordionSummary>
              <AccordionDetails>
                <Stack spacing={1.5}>
                  <TextField select size="small" label={t('expx.gstKind')} value={form.gstKind} onChange={(e) => setForm((f) => ({ ...f, gstKind: e.target.value as GstKind }))}>
                    <MenuItem value="NONE">{t('expx.gstNone')}</MenuItem>
                    <MenuItem value="INTRA">{t('expx.gstIntra')}</MenuItem>
                    <MenuItem value="INTER">{t('expx.gstInter')}</MenuItem>
                  </TextField>
                  {form.gstKind !== 'NONE' ? (
                    <>
                      <Stack direction="row" spacing={1}>
                        <TextField size="small" type="number" label={t('expx.gstRate')} value={form.gstRate} onChange={(e) => setForm((f) => ({ ...f, gstRate: e.target.value }))} />
                        <TextField
                          size="small" type="number" fullWidth
                          label={form.gstKind === 'INTRA' ? t('expx.cgstAmount') : t('expx.igstAmount')}
                          helperText={form.gstKind === 'INTRA' ? t('expx.sgstSame') : undefined}
                          value={form.gstAmount} onChange={(e) => setForm((f) => ({ ...f, gstAmount: e.target.value }))}
                        />
                      </Stack>
                      <TextField size="small" label={t('expx.supplierGstin')} value={form.supplierGstin} onChange={(e) => setForm((f) => ({ ...f, supplierGstin: e.target.value }))} inputProps={{ maxLength: 15 }} />
                      <FormControlLabel control={<Checkbox size="small" checked={form.itcEligible} onChange={(e) => setForm((f) => ({ ...f, itcEligible: e.target.checked }))} />} label={t('expx.itcEligible')} />
                    </>
                  ) : null}
                  <Stack direction="row" spacing={1}>
                    <TextField size="small" label={t('expx.tdsSection')} value={form.tdsSection} onChange={(e) => setForm((f) => ({ ...f, tdsSection: e.target.value }))} />
                    <TextField size="small" type="number" fullWidth label={t('expx.tdsAmount')} value={form.tdsAmount} onChange={(e) => setForm((f) => ({ ...f, tdsAmount: e.target.value }))} />
                  </Stack>
                  {taxError ? <Alert severity="warning">{taxError}</Alert> : null}
                </Stack>
              </AccordionDetails>
            </Accordion>
            <TextField size="small" label={t('common.notes')} value={form.notes} onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))} multiline minRows={2} />
            {dupes && dupes.length > 0 ? (
              <Alert severity="warning">{t('expenses.duplicateWarning', { numbers: dupes.map((d) => d.number || `#${d.id}`).join(', ') })}</Alert>
            ) : null}
            {error ? <HelpErrorAlert message={error} /> : null}
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
                      .then((uploaded) => {
                        // Replacing an upload that was never saved removes the earlier one.
                        if (orphan.current !== null && orphan.current !== uploaded.id) void deleteFileAsset(orphan.current).catch(() => undefined);
                        orphan.current = uploaded.id;
                        setForm((f) => ({ ...f, attachment: uploaded.id }));
                      })
                      .catch((err) => setError(getErrorMessage(err)))
                      .finally(() => setUploading(false));
                  }}
                />
              </Button>
              {form.attachment ? <Typography variant="caption" color="text.secondary">{t('expenses.attachment')} #{form.attachment}</Typography> : null}
            </Stack>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeDialog}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={
              !form.category || !(Number(form.amount) > 0) || save.isPending || uploading || Boolean(taxError) ||
              (form.paymentMode === 'BANK' && !form.bankAccount)
            }
            onClick={() => void trySave()}
          >
            {dupes && dupes.length > 0 ? t('expenses.saveAnyway') : t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>

      <CategoryDialog
        open={manageCats}
        onClose={() => setManageCats(false)}
        categories={categoryRows}
        onAdded={(id) => setForm((f) => ({ ...f, category: String(id) }))}
      />
      <RecurringDialog open={recurringOpen} onClose={() => setRecurringOpen(false)} categories={categoryRows.filter((c) => c.isActive)} canWrite={canWrite} />

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
