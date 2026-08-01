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
import { createSupplier, listSuppliers, updateSupplier } from '@/api/resources';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { StatusChip } from '@/components/StatusChip';
import { t } from '@/i18n';
import type { Supplier } from '@/types/domain';
import { formatMoney } from '@/utils/money';

const emptyForm = { name: '', phone: '', email: '', gstin: '', state: '', address: '' };

export function SuppliersPage() {
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ['suppliers'], queryFn: listSuppliers });
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Supplier | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState<string | null>(null);

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (editing) return updateSupplier(editing.id, form);
      return createSupplier({ ...form, isActive: true });
    },
    onSuccess: () => {
      setOpen(false);
      setEditing(null);
      setForm(emptyForm);
      void qc.invalidateQueries({ queryKey: ['suppliers'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const toggleMutation = useMutation({
    mutationFn: (s: Supplier) => updateSupplier(s.id, { isActive: !s.isActive }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['suppliers'] }),
    onError: (err) => setError(getErrorMessage(err)),
  });

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="h4">{t('nav.suppliers')}</Typography>
        <Button
          variant="contained"
          onClick={() => {
            setEditing(null);
            setForm(emptyForm);
            setOpen(true);
          }}
        >
          {t('common.add')}
        </Button>
      </Stack>
      {error ? <Alert severity="error">{error}</Alert> : null}
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} onRetry={() => void query.refetch()} />
      ) : null}
      {query.data?.length === 0 ? <EmptyState /> : null}
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
              {query.data.map((s) => (
                <TableRow key={s.id}>
                  <TableCell>{s.name}</TableCell>
                  <TableCell>{s.phone ?? '—'}</TableCell>
                  <TableCell>{s.gstin ?? '—'}</TableCell>
                  <TableCell>
                    <StatusChip
                      tone={s.isActive ? 'success' : 'default'}
                      label={s.isActive ? t('status.ACTIVE') : t('status.INACTIVE')}
                    />
                  </TableCell>
                  <TableCell align="right">{formatMoney(s.outstanding ?? 0)}</TableCell>
                  <TableCell align="right">
                    <Button
                      size="small"
                      onClick={() => {
                        setEditing(s);
                        setForm({
                          name: s.name,
                          phone: s.phone ?? '',
                          email: s.email ?? '',
                          gstin: s.gstin ?? '',
                          state: s.state ?? '',
                          address: s.address ?? '',
                        });
                        setOpen(true);
                      }}
                    >
                      {t('common.edit')}
                    </Button>
                    <Button size="small" onClick={() => toggleMutation.mutate(s)}>
                      {s.isActive ? t('common.deactivate') : t('common.activate')}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}

      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editing ? t('common.edit') : t('common.create')} supplier</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {(
              [
                ['name', t('common.name')],
                ['phone', t('common.phone')],
                ['email', t('common.email')],
                ['gstin', 'GSTIN'],
                ['state', t('auth.state')],
                ['address', 'Address'],
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
