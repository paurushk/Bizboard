import { useState } from 'react';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
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
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import {
  createEmployee,
  listEmployeesPage,
  updateEmployee,
  type Employee,
} from '@/api/payroll';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { StatusChip } from '@/components/StatusChip';
import { t } from '@/i18n';
import { ModuleGate, MvpModuleBanner } from '@/pages/erp/erpShared';
import { formatMoney } from '@/utils/money';
import { customerStatusTone, statusLabelKey } from '@/utils/status';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';

const PAGE_SIZE = 50;
const EMP_STATUSES = ['ACTIVE', 'INACTIVE'] as const;

const emptyForm = {
  name: '',
  code: '',
  salary: '',
  basic: '',
  da: '',
  tdsRate: '',
  status: 'ACTIVE',
  pfApplicable: false,
  pfWageCeiling: '15000.00',
  esiApplicable: false,
  ptState: '',
};

export function EmployeesPage() {
  return (
    <ModuleGate module="payroll" title={t('nav.employees')}>
      <EmployeesPageInner />
    </ModuleGate>
  );
}

function EmployeesPageInner() {
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Employee | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ['employees', page],
    queryFn: () => listEmployeesPage({ page, pageSize: PAGE_SIZE }),
  });

  const rows = query.data?.results ?? [];

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        name: form.name,
        code: form.code,
        salary: form.salary,
        basic: form.basic || '0',
        da: form.da || '0',
        tdsRate: form.tdsRate || '0',
        status: form.status,
        pfApplicable: form.pfApplicable,
        pfWageCeiling: form.pfWageCeiling || '15000.00',
        esiApplicable: form.esiApplicable,
        ptState: form.ptState,
      };
      if (editing) return updateEmployee(editing.id, payload);
      return createEmployee(payload);
    },
    onSuccess: () => {
      setOpen(false);
      setEditing(null);
      setForm(emptyForm);
      void qc.invalidateQueries({ queryKey: ['employees'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const toggleMutation = useMutation({
    mutationFn: (emp: Employee) =>
      updateEmployee(emp.id, { status: emp.status === 'ACTIVE' ? 'INACTIVE' : 'ACTIVE' }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['employees'] }),
    onError: (err) => setError(getErrorMessage(err)),
  });

  const openCreate = () => {
    setEditing(null);
    setForm(emptyForm);
    setOpen(true);
  };

  const openEdit = (emp: Employee) => {
    setEditing(emp);
    setForm({
      name: emp.name,
      code: emp.code,
      salary: emp.salary,
      basic: emp.basic ?? '',
      da: emp.da ?? '',
      tdsRate: emp.tdsRate ?? '',
      status: emp.status,
      pfApplicable: Boolean(emp.pfApplicable),
      pfWageCeiling: emp.pfWageCeiling || '15000.00',
      esiApplicable: Boolean(emp.esiApplicable),
      ptState: emp.ptState ?? '',
    });
    setOpen(true);
  };

  return (
    <Stack spacing={2}>
      <MvpModuleBanner module="payroll" />
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="h4">{t('nav.employees')}</Typography>
        <Button variant="contained" onClick={openCreate}>
          {t('common.add')}
        </Button>
      </Stack>
      {error ? <HelpErrorAlert message={error} /> : null}
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {rows.length === 0 && !query.isLoading && !query.isError ? (
        <EmptyState description={t('empty.employees')} />
      ) : null}
      {rows.length > 0 ? (
        <Paper sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('common.name')}</TableCell>
                <TableCell>{t('erp.employeeCode')}</TableCell>
                <TableCell align="right">{t('erp.salary')}</TableCell>
                <TableCell>{t('common.status')}</TableCell>
                <TableCell align="right">{t('common.actions')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((emp) => (
                <TableRow key={emp.id}>
                  <TableCell>{emp.name}</TableCell>
                  <TableCell>{emp.code}</TableCell>
                  <TableCell align="right">{formatMoney(emp.salary)}</TableCell>
                  <TableCell>
                    <StatusChip
                      tone={customerStatusTone(emp.status)}
                      labelKey={statusLabelKey(emp.status)}
                    />
                  </TableCell>
                  <TableCell align="right">
                    <Button size="small" onClick={() => openEdit(emp)}>
                      {t('common.edit')}
                    </Button>
                    <Button
                      size="small"
                      onClick={() => {
                        const ok = window.confirm(
                          emp.status === 'ACTIVE' ? t('common.confirmDeactivate') : t('common.confirmActivate'),
                        );
                        if (!ok) return;
                        toggleMutation.mutate(emp);
                      }}
                    >
                      {emp.status === 'ACTIVE' ? t('common.deactivate') : t('common.activate')}
                    </Button>
                  </TableCell>
                </TableRow>
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

      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editing ? t('common.edit') : t('common.create')} employee</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label={t('common.name')}
              required
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            />
            <TextField
              label={t('erp.employeeCode')}
              required
              value={form.code}
              onChange={(e) => setForm((f) => ({ ...f, code: e.target.value }))}
            />
            <TextField
              label={t('erp.salary')}
              type="number"
              required
              value={form.salary}
              onChange={(e) => setForm((f) => ({ ...f, salary: e.target.value }))}
            />
            <TextField
              label={t('erp.basic')}
              type="number"
              value={form.basic}
              onChange={(e) => setForm((f) => ({ ...f, basic: e.target.value }))}
            />
            <TextField
              label={t('erp.da')}
              type="number"
              value={form.da}
              onChange={(e) => setForm((f) => ({ ...f, da: e.target.value }))}
            />
            <TextField
              label={t('erp.tdsRate')}
              type="number"
              value={form.tdsRate}
              onChange={(e) => setForm((f) => ({ ...f, tdsRate: e.target.value }))}
            />
            <TextField
              select
              label={t('common.status')}
              value={form.status}
              onChange={(e) => setForm((f) => ({ ...f, status: e.target.value }))}
            >
              {EMP_STATUSES.map((s) => (
                <MenuItem key={s} value={s}>
                  {t(statusLabelKey(s))}
                </MenuItem>
              ))}
            </TextField>
            <FormControlLabel
              control={
                <Checkbox
                  checked={form.pfApplicable}
                  onChange={(e) => setForm((f) => ({ ...f, pfApplicable: e.target.checked }))}
                />
              }
              label={t('erp.pfApplicable')}
            />
            <TextField
              label={t('erp.pfWageCeiling')}
              type="number"
              value={form.pfWageCeiling}
              onChange={(e) => setForm((f) => ({ ...f, pfWageCeiling: e.target.value }))}
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={form.esiApplicable}
                  onChange={(e) => setForm((f) => ({ ...f, esiApplicable: e.target.checked }))}
                />
              }
              label={t('erp.esiApplicable')}
            />
            <TextField
              label={t('erp.ptState')}
              value={form.ptState}
              onChange={(e) => setForm((f) => ({ ...f, ptState: e.target.value }))}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={!form.name || !form.code || !form.salary || saveMutation.isPending}
            onClick={() => saveMutation.mutate()}
          >
            {t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
