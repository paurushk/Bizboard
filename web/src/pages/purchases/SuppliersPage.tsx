import { useState } from 'react';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
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
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { createSupplier, getCompany, listSuppliers, updateSupplier, verifySupplierGstin } from '@/api/resources';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { StateSelect } from '@/components/StateSelect';
import { StatusChip } from '@/components/StatusChip';
import { t } from '@/i18n';
import type { Supplier } from '@/types/domain';
import { isValidGstin, isValidIndianPhone } from '@/utils/gst';
import { getStateFromGstin } from '@/utils/indianStates';
import { placeOfSupplyKnown } from '@/utils/tax';
import { formatMoney } from '@/utils/money';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';

const emptyForm = { name: '', phone: '', email: '', gstin: '', state: '', address: '' };

function gstinStatusColor(status?: string): 'default' | 'success' | 'warning' | 'error' {
  switch ((status ?? 'UNVERIFIED').toUpperCase()) {
    case 'VERIFIED':
      return 'success';
    case 'INVALID':
    case 'FAILED':
      return 'error';
    default:
      return 'warning';
  }
}

export function SuppliersPage() {
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ['suppliers'], queryFn: listSuppliers });
  const company = useQuery({ queryKey: ['company'], queryFn: getCompany });
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Supplier | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState<string | null>(null);
  const [nameTouched, setNameTouched] = useState(false);

  // F2-054: mirror CustomersPage — when GST is on and assume-local is off,
  // require a place of supply (State or GSTIN) before a supplier can be saved,
  // otherwise the friction only surfaces later as a blocked purchase Complete.
  const requirePlaceOfSupply =
    !!company.data?.isGstRegistered && !company.data?.assumeLocalStateForBlankParty;
  const placeOfSupplyOk =
    !requirePlaceOfSupply || placeOfSupplyKnown(form.state, form.gstin);
  const canSave = Boolean(form.name.trim()) && placeOfSupplyOk;

  const saveMutation = useMutation({
    mutationFn: async () => {
      const gstin = form.gstin.trim().toUpperCase();
      if (gstin && !isValidGstin(gstin)) {
        throw new Error('Enter a valid 15-character GSTIN.');
      }
      const payload = { ...form, gstin: gstin || form.gstin };
      if (editing) return updateSupplier(editing.id, payload);
      return createSupplier({ ...payload, isActive: true });
    },
    onSuccess: () => {
      setOpen(false);
      setEditing(null);
      setForm(emptyForm);
      setError(null);
      void qc.invalidateQueries({ queryKey: ['suppliers'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const toggleMutation = useMutation({
    mutationFn: (s: Supplier) => updateSupplier(s.id, { isActive: !s.isActive }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['suppliers'] }),
    onError: (err) => setError(getErrorMessage(err)),
  });

  const verifyMutation = useMutation({
    mutationFn: (id: number) => verifySupplierGstin(id),
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
            setNameTouched(false);
            setOpen(true);
          }}
        >
          {t('common.add')}
        </Button>
      </Stack>
      {error ? <HelpErrorAlert message={error} /> : null}
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {query.data?.length === 0 ? (
        <EmptyState
          description="Add suppliers to record purchase bills and track payables."
          action={
            <Button
              variant="contained"
              onClick={() => {
                setEditing(null);
                setForm(emptyForm);
                setNameTouched(false);
                setOpen(true);
              }}
            >
              {t('empty.addSupplier')}
            </Button>
          }
        />
      ) : null}
      {query.data && query.data.length > 0 ? (
        <Paper sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('common.name')}</TableCell>
                <TableCell>{t('common.phone')}</TableCell>
                <TableCell>GSTIN</TableCell>
                <TableCell>GSTIN status</TableCell>
                <TableCell>{t('common.status')}</TableCell>
                <TableCell align="right">Outstanding</TableCell>
                <TableCell />
              </TableRow>
            </TableHead>
            <TableBody>
              {query.data.map((s) => (
                <TableRow key={s.id}>
                  <TableCell
                    sx={{
                      position: { xs: 'sticky', md: 'static' },
                      left: 0,
                      zIndex: 1,
                      bgcolor: 'background.paper',
                      minWidth: 120,
                    }}
                  >
                    {s.name}
                  </TableCell>
                  <TableCell>{s.phone ?? '—'}</TableCell>
                  <TableCell>
                    {s.gstin ?? '—'}
                    {s.gstinLegalName ? (
                      <Typography variant="caption" display="block" color="text.secondary">
                        {s.gstinLegalName}
                      </Typography>
                    ) : null}
                  </TableCell>
                  <TableCell>
                    {s.gstin ? (
                      <Stack direction="row" spacing={0.5} alignItems="center">
                        <Chip
                          size="small"
                          label={
                            (s.gstinVerificationStatus ?? 'UNVERIFIED') === 'UNVERIFIED'
                              ? 'Unverified'
                              : (s.gstinVerificationStatus ?? 'UNVERIFIED')
                          }
                          color={gstinStatusColor(s.gstinVerificationStatus)}
                        />
                        <Button
                          size="small"
                          disabled={verifyMutation.isPending}
                          onClick={() => verifyMutation.mutate(s.id)}
                        >
                          Verify
                        </Button>
                      </Stack>
                    ) : (
                      '—'
                    )}
                  </TableCell>
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
                        setNameTouched(false);
                        setOpen(true);
                      }}
                    >
                      {t('common.edit')}
                    </Button>
                    <Button
                      size="small"
                      disabled={toggleMutation.isPending}
                      onClick={() => toggleMutation.mutate(s)}
                    >
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
            <TextField
              label={t('common.name')}
              required
              value={form.name}
              onBlur={() => setNameTouched(true)}
              error={nameTouched && !form.name.trim()}
              helperText={nameTouched && !form.name.trim() ? 'Supplier name is required' : undefined}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            />
            <TextField
              label={t('common.phone')}
              value={form.phone}
              error={Boolean(form.phone.trim() && !isValidIndianPhone(form.phone))}
              helperText={
                form.phone.trim() && !isValidIndianPhone(form.phone)
                  ? 'Enter a valid 10-digit Indian mobile number'
                  : undefined
              }
              onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))}
            />
            <TextField
              label={t('common.email')}
              value={form.email}
              onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
            />
            <TextField
              label="GSTIN"
              value={form.gstin}
              error={Boolean(form.gstin.trim() && form.gstin.trim().length === 15 && !isValidGstin(form.gstin.trim()))}
              helperText={
                form.gstin.trim() && form.gstin.trim().length === 15 && !isValidGstin(form.gstin.trim())
                  ? 'Invalid 15-digit GSTIN checksum/format'
                  : undefined
              }
              onChange={(e) => {
                const val = e.target.value.toUpperCase().trim();
                const matchedState = getStateFromGstin(val);
                setForm((f) => ({
                  ...f,
                  gstin: val,
                  state: matchedState && !f.state ? matchedState : f.state,
                }));
              }}
            />
            <StateSelect
              value={form.state}
              onChange={(state) => setForm((f) => ({ ...f, state }))}
            />
            <TextField
              label="Address"
              value={form.address}
              onChange={(e) => setForm((f) => ({ ...f, address: e.target.value }))}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>{t('common.cancel')}</Button>
          <Tooltip
            title={
              !form.name.trim()
                ? 'Enter supplier name to save'
                : !placeOfSupplyOk
                  ? 'Enter the supplier State or GSTIN (GST is enabled for this company)'
                  : ''
            }
          >
            <span>
              <Button
                variant="contained"
                disabled={!canSave || saveMutation.isPending}
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
