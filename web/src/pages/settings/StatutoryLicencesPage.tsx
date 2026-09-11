import { useState } from 'react';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import * as api from '@/api/resources';
import type { CompanyStatutoryLicenceRow } from '@/api/legacy/company';
import { useAuth } from '@/auth/AuthContext';
import { ErrorState, LoadingState } from '@/components/PageState';
import { StateSelect } from '@/components/StateSelect';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { ForbiddenPage } from '@/pages/ForbiddenPage';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { asRows, DataTable, PageShell } from '@/pages/phase/phaseShared';
import { t } from '@/i18n';
import { canManageGst } from '@/utils/permissions';

const LICENCE_TYPE_OPTIONS: Array<{ value: CompanyStatutoryLicenceRow['licenceType']; label: string }> = [
  { value: 'DRUG_20B', label: 'Drug Licence — Form 20B' },
  { value: 'DRUG_21B', label: 'Drug Licence — Form 21B' },
  { value: 'FSSAI', label: 'FSSAI' },
];

function isActiveRow(row: Record<string, unknown>): boolean {
  return row.isActive !== false && row.is_active !== false;
}

export function StatutoryLicencesPage() {
  const { user } = useAuth();
  const { writesBlocked } = useSubscriptionGate();
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: ['company-statutory-licences'],
    queryFn: () => api.listCompanyStatutoryLicences(),
  });
  const [open, setOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [licenceType, setLicenceType] = useState<CompanyStatutoryLicenceRow['licenceType']>('DRUG_20B');
  const [licenceNumber, setLicenceNumber] = useState('');
  const [premisesState, setPremisesState] = useState('');
  const [validUpto, setValidUpto] = useState('');
  const [error, setError] = useState('');

  const resetForm = () => {
    setEditingId(null);
    setLicenceType('DRUG_20B');
    setLicenceNumber('');
    setPremisesState('');
    setValidUpto('');
  };

  const openCreate = () => {
    resetForm();
    setOpen(true);
  };

  const openEdit = (row: Record<string, unknown>) => {
    setEditingId(Number(row.id));
    setLicenceType((row.licenceType as CompanyStatutoryLicenceRow['licenceType']) ?? 'DRUG_20B');
    setLicenceNumber(String(row.licenceNumber ?? row.licence_number ?? ''));
    setPremisesState(String(row.premisesState ?? row.premises_state ?? ''));
    setValidUpto(String(row.validUpto ?? row.valid_upto ?? '').slice(0, 10));
    setOpen(true);
  };

  const save = useMutation({
    mutationFn: () => {
      const payload = {
        licence_type: licenceType,
        licence_number: licenceNumber,
        premises_state: premisesState,
        valid_upto: validUpto || null,
      };
      return editingId != null
        ? api.updateCompanyStatutoryLicence(editingId, payload)
        : api.createCompanyStatutoryLicence({ ...payload, is_active: true });
    },
    onSuccess: () => {
      setOpen(false);
      setError('');
      resetForm();
      void qc.invalidateQueries({ queryKey: ['company-statutory-licences'] });
    },
    onError: (e) => setError(getErrorMessage(e)),
  });

  const toggleActive = useMutation({
    mutationFn: (row: Record<string, unknown>) =>
      api.updateCompanyStatutoryLicence(Number(row.id), { is_active: !isActiveRow(row) }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['company-statutory-licences'] }),
    onError: (e) => setError(getErrorMessage(e)),
  });

  if (!canManageGst(user)) return <ForbiddenPage />;
  if (query.isLoading) return <LoadingState />;
  if (query.isError) {
    return (
      <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
    );
  }

  return (
    <PageShell
      title={t('phase.statutoryLicences')}
      subtitle={t('phase.statutoryLicencesSubtitle')}
      actions={
        <Button variant="contained" onClick={openCreate} disabled={writesBlocked}>
          {t('phase.addLicence')}
        </Button>
      }
    >
      {error ? <HelpErrorAlert message={error} /> : null}
      <DataTable
        rows={asRows(query.data)}
        empty={t('phase.noStatutoryLicences')}
        columns={[
          {
            key: 'licenceType',
            label: t('phase.licenceType'),
            render: (row) =>
              LICENCE_TYPE_OPTIONS.find((opt) => opt.value === row.licenceType)?.label ??
              String(row.licenceType ?? '—'),
          },
          { key: 'licenceNumber', label: t('phase.licenceNumber') },
          { key: 'premisesState', label: t('phase.premisesState') },
          { key: 'validUpto', label: t('phase.licenceValidUpto') },
          { key: 'isActive', label: t('common.status'), bool: true },
        ]}
        actions={(row) => (
          <Stack direction="row" spacing={1}>
            <Button size="small" disabled={writesBlocked} onClick={() => openEdit(row)}>
              {t('common.edit')}
            </Button>
            <Button
              size="small"
              color={isActiveRow(row) ? 'error' : 'primary'}
              disabled={writesBlocked}
              onClick={() => toggleActive.mutate(row)}
            >
              {isActiveRow(row) ? t('phase.licenceDeactivate') : t('phase.licenceActivate')}
            </Button>
          </Stack>
        )}
      />
      <Dialog
        open={open}
        onClose={() => {
          setOpen(false);
          resetForm();
        }}
        fullWidth
        maxWidth="xs"
      >
        <DialogTitle>{editingId != null ? t('phase.editLicence') : t('phase.licence')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              select
              label={t('phase.licenceType')}
              value={licenceType}
              onChange={(e) => setLicenceType(e.target.value as CompanyStatutoryLicenceRow['licenceType'])}
            >
              {LICENCE_TYPE_OPTIONS.map((opt) => (
                <MenuItem key={opt.value} value={opt.value}>
                  {opt.label}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label={t('phase.licenceNumber')}
              value={licenceNumber}
              onChange={(e) => setLicenceNumber(e.target.value)}
            />
            <StateSelect value={premisesState} onChange={(val) => setPremisesState(val)} label={t('phase.premisesState')} />
            <TextField
              label={t('phase.licenceValidUpto')}
              type="date"
              value={validUpto}
              onChange={(e) => setValidUpto(e.target.value)}
              InputLabelProps={{ shrink: true }}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => {
              setOpen(false);
              resetForm();
            }}
          >
            {t('common.cancel')}
          </Button>
          <Button
            variant="contained"
            disabled={writesBlocked || !licenceNumber || save.isPending}
            onClick={() => save.mutate()}
          >
            {t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>
    </PageShell>
  );
}
