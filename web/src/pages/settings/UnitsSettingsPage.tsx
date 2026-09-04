import { useState } from 'react';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { createUnit, listUnits, updateUnit } from '@/api/resources';
import { GSTN_UQC_CODES } from '@/constants/uqcCodes';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { ForbiddenPage } from '@/pages/ForbiddenPage';
import { t } from '@/i18n';
import type { Unit } from '@/types/domain';
import { useAuth } from '@/auth/AuthContext';
import { canManageUsers } from '@/utils/permissions';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { UnsavedChangesGuard } from '@/components/UnsavedChangesGuard';

const emptyForm = { name: '', shortName: '', uqcCode: 'PCS' };

export function UnitsSettingsPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ['units'], queryFn: listUnits });
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Unit | null>(null);
  const [form, setForm] = useState(emptyForm);
  // F3-015: JSON-diff baseline for the unsaved-changes guard (no react-hook-form here).
  const [baselineFormJson, setBaselineFormJson] = useState(JSON.stringify(emptyForm));
  const [error, setError] = useState<string | null>(null);

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (editing) {
        return updateUnit(editing.id, {
          name: form.name,
          shortName: form.shortName || form.name,
          uqcCode: form.uqcCode,
        });
      }
      return createUnit({
        name: form.name,
        shortName: form.shortName || form.name,
        uqcCode: form.uqcCode,
      });
    },
    onSuccess: () => {
      setOpen(false);
      setEditing(null);
      setForm(emptyForm);
      setBaselineFormJson(JSON.stringify(emptyForm));
      void qc.invalidateQueries({ queryKey: ['units'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  if (!canManageUsers(user)) return <ForbiddenPage />;
  if (query.isLoading) return <LoadingState />;
  if (query.isError) {
    return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  }

  const dirty = open && JSON.stringify(form) !== baselineFormJson;

  return (
    <Stack spacing={2}>
      <UnsavedChangesGuard when={dirty} />
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="h4">Units</Typography>
        <Button
          variant="contained"
          onClick={() => {
            setEditing(null);
            setForm(emptyForm);
            setBaselineFormJson(JSON.stringify(emptyForm));
            setOpen(true);
          }}
        >
          {t('common.add')}
        </Button>
      </Stack>
      {error ? <HelpErrorAlert message={error} /> : null}
      {query.data?.length === 0 ? <EmptyState description="No units yet" /> : null}
      {query.data && query.data.length > 0 ? (
        <Paper sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('common.name')}</TableCell>
                <TableCell>Short name</TableCell>
                <TableCell>UQC code</TableCell>
                <TableCell />
              </TableRow>
            </TableHead>
            <TableBody>
              {query.data.map((unit) => (
                <TableRow key={unit.id}>
                  <TableCell>{unit.name}</TableCell>
                  <TableCell>{unit.shortName ?? '—'}</TableCell>
                  <TableCell>{unit.uqcCode ?? '—'}</TableCell>
                  <TableCell align="right">
                    <Button
                      size="small"
                      onClick={() => {
                        setEditing(unit);
                        {
                          const next = {
                            name: unit.name,
                            shortName: unit.shortName ?? '',
                            uqcCode: unit.uqcCode ?? 'PCS',
                          };
                          setForm(next);
                          setBaselineFormJson(JSON.stringify(next));
                        }
                        setOpen(true);
                      }}
                    >
                      {t('common.edit')}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}

      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editing ? t('common.edit') : t('common.create')} unit</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label={t('common.name')}
              required
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            />
            <TextField
              label="Short name"
              value={form.shortName}
              onChange={(e) => setForm((f) => ({ ...f, shortName: e.target.value }))}
              helperText="Shown on invoices (e.g. PCS, KG)"
            />
            <TextField
              select
              label="UQC code (GSTN)"
              value={form.uqcCode}
              onChange={(e) => setForm((f) => ({ ...f, uqcCode: e.target.value }))}
            >
              {GSTN_UQC_CODES.map((code) => (
                <MenuItem key={code} value={code}>
                  {code}
                </MenuItem>
              ))}
            </TextField>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>{t('common.cancel')}</Button>
          <Tooltip title={!form.name.trim() ? 'Enter unit name to save' : ''}>
            <span>
              <Button
                variant="contained"
                disabled={!form.name.trim() || saveMutation.isPending}
                onClick={() => saveMutation.mutate()}
              >
                {t('common.save')}
              </Button>
            </span>
          </Tooltip>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
