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
import * as api from '@/api/resources';
import type { CompanyStatutoryLicenceRow } from '@/api/legacy/company';
import Chip from '@mui/material/Chip';
import Typography from '@mui/material/Typography';
import { SettingsPage, type SettingsBanner } from '@/components/settings/SettingsPage';
import { useAuth } from '@/auth/AuthContext';
import { ErrorState, LoadingState } from '@/components/PageState';
import { StateSelect } from '@/components/StateSelect';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { ForbiddenPage } from '@/pages/ForbiddenPage';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { asRows, DataTable } from '@/pages/phase/phaseShared';
import { t } from '@/i18n';
import { canManageGst } from '@/utils/permissions';
import { settingsErrorText } from '@/utils/settingsErrors';

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
  const status = useQuery({
    queryKey: ['company-statutory-licences-status'],
    queryFn: () => api.getStatutoryLicenceStatus(),
  });
  const [open, setOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [replacing, setReplacing] = useState<Record<string, unknown> | null>(null);
  const [newNumber, setNewNumber] = useState('');
  const [newFrom, setNewFrom] = useState('');
  const [newUpto, setNewUpto] = useState('');
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

  // A renewal usually keeps the number, so the new record starts from the current one.
  const openReplace = (row: Record<string, unknown>) => {
    setReplacing(row);
    setNewNumber(String(row.licenceNumber ?? row.licence_number ?? ''));
    setNewFrom('');
    setNewUpto('');
    setError('');
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
      void qc.invalidateQueries({ queryKey: ['company-statutory-licences-status'] });
    },
    onError: (e) => setError(settingsErrorText(e)),
  });

  const replace = useMutation({
    mutationFn: () =>
      api.replaceCompanyStatutoryLicence(Number(replacing?.id), {
        licence_number: newNumber,
        valid_from: newFrom || null,
        valid_upto: newUpto || null,
      }),
    onSuccess: () => {
      setReplacing(null);
      setNewNumber('');
      setNewFrom('');
      setNewUpto('');
      setError('');
      void qc.invalidateQueries({ queryKey: ['company-statutory-licences'] });
      void qc.invalidateQueries({ queryKey: ['company-statutory-licences-status'] });
    },
    onError: (e) => setError(settingsErrorText(e)),
  });

  const toggleActive = useMutation({
    mutationFn: (row: Record<string, unknown>) =>
      api.updateCompanyStatutoryLicence(Number(row.id), { is_active: !isActiveRow(row) }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['company-statutory-licences'] });
      void qc.invalidateQueries({ queryKey: ['company-statutory-licences-status'] });
    },
    onError: (e) => setError(settingsErrorText(e)),
  });

  const banners: SettingsBanner[] = [];
  if (status.data) {
    const s = status.data;
    if (s.expired > 0) banners.push({ severity: 'warning', text: t('licences.expired', { count: String(s.expired) }) });
    if (s.expiringSoon > 0) {
      banners.push({ severity: 'info', text: t('licences.expiringSoon', { count: String(s.expiringSoon) }) });
    }
    if (s.enforcement) banners.push({ severity: 'success', text: t('licences.enforcementOn') });
    else if (s.regulatedProducts > 0) {
      banners.push({
        severity: 'warning',
        text: t('licences.enforcementOffRegulated', { count: String(s.regulatedProducts) }),
      });
    } else banners.push({ severity: 'info', text: t('licences.enforcementOff') });
  } else if (status.isError) {
    banners.push({ severity: 'warning', text: t('licences.statusUnavailable') });
  }

  if (!canManageGst(user)) return <ForbiddenPage />;
  if (query.isLoading) return <LoadingState />;
  if (query.isError) {
    return (
      <ErrorState message={settingsErrorText(query.error)} error={query.error} onRetry={() => void query.refetch()} />
    );
  }

  return (
    <SettingsPage
      title={t('phase.statutoryLicences')}
      purpose={t('phase.statutoryLicencesSubtitle')}
      banner={banners}
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
          {
            key: 'isLocked',
            label: '',
            render: (row) =>
              row.isLocked ?? row.is_locked ? <Chip size="small" variant="outlined" label={t('licences.locked')} /> : null,
          },
        ]}
        actions={(row) => (
          <Stack direction="row" spacing={1}>
            {row.isLocked ?? row.is_locked ? null : (
              <Button size="small" disabled={writesBlocked} onClick={() => openEdit(row)}>
                {t('common.edit')}
              </Button>
            )}
            {isActiveRow(row) ? (
              <Button size="small" disabled={writesBlocked} onClick={() => openReplace(row)}>
                {t('licences.replace')}
              </Button>
            ) : null}
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
      <Dialog open={replacing !== null} onClose={() => setReplacing(null)} fullWidth maxWidth="xs">
        <DialogTitle>{t('licences.replaceTitle')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Typography variant="body2" color="text.secondary">
              {t('licences.replaceHelp')}
            </Typography>
            {error ? <HelpErrorAlert message={error} /> : null}
            <TextField
              label={t('licences.newNumber')}
              value={newNumber}
              onChange={(e) => setNewNumber(e.target.value)}
            />
            <TextField
              label={t('licences.validFrom')}
              type="date"
              value={newFrom}
              onChange={(e) => setNewFrom(e.target.value)}
              InputLabelProps={{ shrink: true }}
            />
            <TextField
              label={t('phase.licenceValidUpto')}
              type="date"
              value={newUpto}
              onChange={(e) => setNewUpto(e.target.value)}
              InputLabelProps={{ shrink: true }}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setReplacing(null)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={writesBlocked || !newNumber || replace.isPending}
            onClick={() => replace.mutate()}
          >
            {t('licences.replace')}
          </Button>
        </DialogActions>
      </Dialog>
    </SettingsPage>
  );
}
