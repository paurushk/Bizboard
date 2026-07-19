import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
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
import { createCustomer, listCustomers, updateCustomer } from '@/api/resources';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { StatusChip } from '@/components/StatusChip';
import { t } from '@/i18n';
import type { Customer } from '@/types/domain';
import { formatMoney } from '@/utils/money';
import { customerStatusTone, statusLabelKey } from '@/utils/status';

const emptyForm = { name: '', phone: '', email: '', gstin: '', state: '', billingAddress: '' };

export function CustomersPage() {
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ['customers'], queryFn: () => listCustomers() });
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Customer | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState<string | null>(null);

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (editing) return updateCustomer(editing.id, form);
      return createCustomer({ ...form, status: 'ACTIVE' });
    },
    onSuccess: () => {
      setOpen(false);
      setEditing(null);
      setForm(emptyForm);
      void qc.invalidateQueries({ queryKey: ['customers'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const toggleMutation = useMutation({
    mutationFn: (c: Customer) =>
      updateCustomer(c.id, { status: c.status === 'ACTIVE' ? 'BLOCKED' : 'ACTIVE' }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['customers'] }),
    onError: (err) => setError(getErrorMessage(err)),
  });

  const openCreate = () => {
    setEditing(null);
    setForm(emptyForm);
    setOpen(true);
  };

  const openEdit = (c: Customer) => {
    setEditing(c);
    setForm({
      name: c.name,
      phone: c.phone ?? '',
      email: c.email ?? '',
      gstin: c.gstin ?? '',
      state: c.state ?? '',
      billingAddress: c.billingAddress ?? '',
    });
    setOpen(true);
  };

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="h4">{t('nav.customers')}</Typography>
        <Button variant="contained" onClick={openCreate}>
          {t('common.add')}
        </Button>
      </Stack>
      {error ? <Alert severity="error">{error}</Alert> : null}
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={query.error.message} onRetry={() => void query.refetch()} />
      ) : null}
      {query.data?.length === 0 ? <EmptyState description={t('empty.customers')} /> : null}
      {query.data && query.data.length > 0 ? (
        <Paper sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('common.name')}</TableCell>
                <TableCell>{t('common.phone')}</TableCell>
                <TableCell>GSTIN</TableCell>
                <TableCell>{t('common.status')}</TableCell>
                <TableCell align="right">Outstanding</TableCell>
                <TableCell />
              </TableRow>
            </TableHead>
            <TableBody>
              {query.data.map((c) => (
                <TableRow key={c.id}>
                  <TableCell>{c.name}</TableCell>
                  <TableCell>{c.phone ?? '—'}</TableCell>
                  <TableCell>{c.gstin ?? '—'}</TableCell>
                  <TableCell>
                    <StatusChip
                      tone={customerStatusTone(c.status)}
                      labelKey={statusLabelKey(c.status)}
                    />
                  </TableCell>
                  <TableCell align="right">{formatMoney(c.outstanding ?? 0)}</TableCell>
                  <TableCell align="right">
                    <Button size="small" onClick={() => openEdit(c)}>
                      {t('common.edit')}
                    </Button>
                    <Button size="small" onClick={() => toggleMutation.mutate(c)}>
                      {c.status === 'ACTIVE' ? t('common.block') : t('common.unblock')}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}

      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editing ? t('common.edit') : t('common.create')} customer</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {(
              [
                ['name', t('common.name')],
                ['phone', t('common.phone')],
                ['email', t('common.email')],
                ['gstin', 'GSTIN'],
                ['state', t('auth.state')],
                ['billingAddress', 'Billing address'],
              ] as const
            ).map(([key, label]) => (
              <TextField
                key={key}
                label={label}
                required={key === 'name'}
                value={form[key]}
                onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
              />
            ))}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={!form.name || saveMutation.isPending}
            onClick={() => saveMutation.mutate()}
          >
            {t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
