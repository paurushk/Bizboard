import { useState } from 'react';
import Alert from '@mui/material/Alert';
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
import { Link as RouterLink } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { getCompany, createCustomer, listCustomersPage, updateCustomer, verifyCustomerGstin } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { StateSelect } from '@/components/StateSelect';
import { StatusChip } from '@/components/StatusChip';
import { t } from '@/i18n';
import type { Customer } from '@/types/domain';
import { isValidGstin, isValidIndianPhone } from '@/utils/gst';
import { getStateFromGstin } from '@/utils/indianStates';
import { formatMoney } from '@/utils/money';
import { isViewer } from '@/utils/permissions';
import { placeOfSupplyKnown } from '@/utils/tax';
import { customerStatusTone, statusLabelKey } from '@/utils/status';

const emptyForm = { name: '', phone: '', email: '', gstin: '', state: '', billingAddress: '' };
const PAGE_SIZE = 50;

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

export function CustomersPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const query = useQuery({
    queryKey: ['customers', page],
    queryFn: () => listCustomersPage({ page, pageSize: PAGE_SIZE }),
  });
  const company = useQuery({ queryKey: ['company'], queryFn: getCompany });
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Customer | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState<string | null>(null);
  const [nameTouched, setNameTouched] = useState(false);
  const rows = query.data?.results ?? [];
  const canMutate = !!user && !isViewer(user.role);
  // UXW2-003: when GST is on and assume-local is off, require State or GSTIN on create.
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
      if (editing) return updateCustomer(editing.id, payload);
      return createCustomer({ ...payload, status: 'ACTIVE' });
    },
    onSuccess: () => {
      setOpen(false);
      setEditing(null);
      setForm(emptyForm);
      setError(null);
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

  const verifyMutation = useMutation({
    mutationFn: (id: number) => verifyCustomerGstin(id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['customers'] }),
    onError: (err) => setError(getErrorMessage(err)),
  });

  const openCreate = () => {
    setEditing(null);
    setForm(emptyForm);
    setNameTouched(false);
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
    setNameTouched(false);
    setOpen(true);
  };

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="h4">{t('nav.customers')}</Typography>
        {canMutate ? (
          <Button variant="contained" onClick={openCreate}>
            {t('common.add')}
          </Button>
        ) : null}
      </Stack>
      {error ? <Alert severity="error">{error}</Alert> : null}
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} onRetry={() => void query.refetch()} />
      ) : null}
      {rows.length === 0 && !query.isLoading && !query.isError ? (
        <EmptyState
          description={t('empty.customers')}
          action={
            canMutate ? (
              <Button variant="contained" onClick={openCreate}>
                {t('common.add')} {t('nav.customers')}
              </Button>
            ) : null
          }
        />
      ) : null}
      {rows.length > 0 ? (
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
              {rows.map((c) => (
                <TableRow key={c.id}>
                  <TableCell
                    sx={{
                      position: { xs: 'sticky', md: 'static' },
                      left: 0,
                      zIndex: 1,
                      bgcolor: 'background.paper',
                      minWidth: 120,
                    }}
                  >
                    {c.name}
                  </TableCell>
                  <TableCell>{c.phone ?? '—'}</TableCell>
                  <TableCell>
                    {c.gstin ?? '—'}
                    {c.gstinLegalName ? (
                      <Typography variant="caption" display="block" color="text.secondary">
                        {c.gstinLegalName}
                      </Typography>
                    ) : null}
                  </TableCell>
                  <TableCell>
                    {c.gstin ? (
                      <Stack direction="row" spacing={0.5} alignItems="center">
                        <Chip
                          size="small"
                          label={
                            (c.gstinVerificationStatus ?? 'UNVERIFIED') === 'UNVERIFIED'
                              ? 'Unverified'
                              : (c.gstinVerificationStatus ?? 'UNVERIFIED')
                          }
                          color={gstinStatusColor(c.gstinVerificationStatus)}
                        />
                        {canMutate ? (
                          <Button
                            size="small"
                            disabled={verifyMutation.isPending}
                            onClick={() => verifyMutation.mutate(c.id)}
                          >
                            Verify
                          </Button>
                        ) : null}
                      </Stack>
                    ) : (
                      '—'
                    )}
                  </TableCell>
                  <TableCell>
                    <StatusChip
                      tone={customerStatusTone(c.status)}
                      labelKey={statusLabelKey(c.status)}
                    />
                  </TableCell>
                  <TableCell align="right">{formatMoney(c.outstanding ?? 0)}</TableCell>
                  <TableCell align="right">
                    <Stack direction="row" spacing={0.5} justifyContent="flex-end">
                      <Button
                        size="small"
                        component={RouterLink}
                        to={`/reports/customer-ledger?customerId=${c.id}`}
                      >
                        {t('billing.viewLedger')}
                      </Button>
                      {canMutate ? (
                        <>
                          <Button size="small" onClick={() => openEdit(c)}>
                            {t('common.edit')}
                          </Button>
                          <Button size="small" onClick={() => toggleMutation.mutate(c)}>
                            {c.status === 'ACTIVE' ? t('common.block') : t('common.unblock')}
                          </Button>
                        </>
                      ) : null}
                    </Stack>
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
            {query.data.count ? ` / ${Math.max(1, Math.ceil(query.data.count / PAGE_SIZE))}` : ''}
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
        <DialogTitle>{editing ? t('common.edit') : t('common.create')} customer</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label={t('common.name')}
              required
              value={form.name}
              onBlur={() => setNameTouched(true)}
              error={nameTouched && !form.name.trim()}
              helperText={nameTouched && !form.name.trim() ? 'Customer name is required' : undefined}
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
              required={requirePlaceOfSupply}
              error={requirePlaceOfSupply && !placeOfSupplyOk}
              helperText={
                requirePlaceOfSupply && !placeOfSupplyOk
                  ? 'State or GSTIN is required for GST invoices'
                  : undefined
              }
            />
            <TextField
              label="Billing address"
              value={form.billingAddress}
              onChange={(e) => setForm((f) => ({ ...f, billingAddress: e.target.value }))}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>{t('common.cancel')}</Button>
          <Tooltip
            title={
              !form.name.trim()
                ? 'Enter customer name to save'
                : !placeOfSupplyOk
                  ? 'Add State or GSTIN for GST invoices (or enable assume-local in GST settings)'
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
