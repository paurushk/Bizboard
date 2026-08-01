import { useState } from 'react';
import Alert from '@mui/material/Alert';
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
import { inviteCompanyUser, listCompanyUsers, updateCompanyUser } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { StatusChip } from '@/components/StatusChip';
import { ForbiddenPage } from '@/pages/ForbiddenPage';
import { t } from '@/i18n';
import { canManageUsers } from '@/utils/permissions';

export function UsersSettingsPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ['company-users'], queryFn: listCompanyUsers });
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    email: '',
    password: '',
    fullName: '',
    role: 'SALES_STAFF',
    canManageInventory: false,
    canImport: false,
    canCancelDocuments: false,
    canViewFinancialReports: true,
    canExport: false,
  });
  const [error, setError] = useState<string | null>(null);

  const inviteMutation = useMutation({
    mutationFn: () => inviteCompanyUser(form),
    onSuccess: () => {
      setOpen(false);
      void qc.invalidateQueries({ queryKey: ['company-users'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const patchMutation = useMutation({
    mutationFn: ({
      id,
      ...payload
    }: {
      id: number;
      canManageInventory?: boolean;
      canImport?: boolean;
      canCancelDocuments?: boolean;
      canViewFinancialReports?: boolean;
      canExport?: boolean;
      isActive?: boolean;
    }) => updateCompanyUser(id, payload),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['company-users'] }),
    onError: (err) => setError(getErrorMessage(err)),
  });

  if (!canManageUsers(user)) return <ForbiddenPage />;

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="h4">{t('nav.users')}</Typography>
        <Button variant="contained" onClick={() => setOpen(true)}>
          {t('common.invite')}
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
                <TableCell>{t('common.email')}</TableCell>
                <TableCell>Role</TableCell>
                <TableCell>Inventory</TableCell>
                <TableCell>Import</TableCell>
                <TableCell>Cancel</TableCell>
                <TableCell>Reports</TableCell>
                <TableCell>Export</TableCell>
                <TableCell>{t('common.status')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {query.data.map((u) => (
                <TableRow key={u.id}>
                  <TableCell>{u.fullName}</TableCell>
                  <TableCell>{u.email}</TableCell>
                  <TableCell>
                    <StatusChip tone="info" label={u.role.replace(/_/g, ' ')} />
                  </TableCell>
                  <TableCell>
                    <Checkbox
                      checked={u.canManageInventory}
                      disabled={u.role === 'OWNER'}
                      onChange={(e) =>
                        patchMutation.mutate({
                          id: u.id,
                          canManageInventory: e.target.checked,
                        })
                      }
                    />
                  </TableCell>
                  <TableCell>
                    <Checkbox
                      checked={u.canImport}
                      disabled={u.role === 'OWNER'}
                      onChange={(e) =>
                        patchMutation.mutate({ id: u.id, canImport: e.target.checked })
                      }
                    />
                  </TableCell>
                  <TableCell>
                    <Checkbox
                      checked={!!u.canCancelDocuments}
                      disabled={u.role === 'OWNER'}
                      onChange={(e) =>
                        patchMutation.mutate({ id: u.id, canCancelDocuments: e.target.checked })
                      }
                    />
                  </TableCell>
                  <TableCell>
                    <Checkbox
                      checked={u.canViewFinancialReports !== false}
                      disabled={u.role === 'OWNER'}
                      onChange={(e) =>
                        patchMutation.mutate({
                          id: u.id,
                          canViewFinancialReports: e.target.checked,
                        })
                      }
                    />
                  </TableCell>
                  <TableCell>
                    <Checkbox
                      checked={!!u.canExport}
                      disabled={u.role === 'OWNER'}
                      onChange={(e) =>
                        patchMutation.mutate({ id: u.id, canExport: e.target.checked })
                      }
                    />
                  </TableCell>
                  <TableCell>
                    {u.isActive ? t('status.ACTIVE') : t('status.INACTIVE')}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}

      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{t('common.invite')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label={t('common.email')}
              required
              value={form.email}
              onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
            />
            <TextField
              label={t('auth.password')}
              type="password"
              required
              value={form.password}
              onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
            />
            <TextField
              label={t('auth.fullName')}
              value={form.fullName}
              onChange={(e) => setForm((f) => ({ ...f, fullName: e.target.value }))}
            />
            <TextField
              select
              label="Role"
              value={form.role}
              onChange={(e) => setForm((f) => ({ ...f, role: e.target.value }))}
            >
              <MenuItem value="SALES_STAFF">Sales staff</MenuItem>
              <MenuItem value="OWNER">Owner</MenuItem>
            </TextField>
            <FormControlLabel
              control={
                <Checkbox
                  checked={form.canManageInventory}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, canManageInventory: e.target.checked }))
                  }
                />
              }
              label="Can manage inventory"
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={form.canImport}
                  onChange={(e) => setForm((f) => ({ ...f, canImport: e.target.checked }))}
                />
              }
              label="Can import"
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={form.canCancelDocuments}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, canCancelDocuments: e.target.checked }))
                  }
                />
              }
              label="Can cancel documents"
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={form.canViewFinancialReports}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, canViewFinancialReports: e.target.checked }))
                  }
                />
              }
              label="Can view financial reports"
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={form.canExport}
                  onChange={(e) => setForm((f) => ({ ...f, canExport: e.target.checked }))}
                />
              }
              label="Can export"
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={!form.email || !form.password || inviteMutation.isPending}
            onClick={() => inviteMutation.mutate()}
          >
            {t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
