import { useState } from 'react';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import {
  createCompanyGstin,
  listCompanyGstins,
  updateCompanyGstin,
  type CompanyGstinRow,
} from '@/api/resources';
import { StateSelect } from '@/components/StateSelect';
import { t } from '@/i18n';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { isValidGstin } from '@/utils/gst';

function flag(row: CompanyGstinRow, camel: 'isPrimary' | 'isActive'): boolean {
  if (camel === 'isPrimary') return row.isPrimary ?? row.is_primary ?? false;
  return row.isActive ?? row.is_active ?? true;
}

function legalName(row: CompanyGstinRow): string {
  return row.legalName || row.legal_name || '';
}

export function BranchGstinsPanel() {
  const queryClient = useQueryClient();
  const gstinsQuery = useQuery({ queryKey: ['company-gstins'], queryFn: listCompanyGstins });
  const [branchGstin, setBranchGstin] = useState('');
  const [branchState, setBranchState] = useState('');
  const [branchName, setBranchName] = useState('');
  const [branchError, setBranchError] = useState<string | null>(null);
  const [editing, setEditing] = useState<CompanyGstinRow | null>(null);
  const [editGstin, setEditGstin] = useState('');
  const [editName, setEditName] = useState('');
  const [editState, setEditState] = useState('');

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['company-gstins'] });

  const fail = (err: unknown) => setBranchError(getErrorMessage(err));

  const openEdit = (row: CompanyGstinRow) => {
    setEditing(row);
    setEditGstin(row.gstin);
    setEditName(legalName(row));
    setEditState(row.state || '');
    setBranchError(null);
  };

  return (
    <Paper sx={{ p: 2, maxWidth: 640 }}>
      <Stack spacing={2}>
        <Typography variant="h6">{t('gst.branchTitle')}</Typography>
        {branchError ? <HelpErrorAlert message={branchError} /> : null}
        {(gstinsQuery.data ?? []).map((row) => {
          const primary = flag(row, 'isPrimary');
          const active = flag(row, 'isActive');
          const name = legalName(row);
          return (
            <Stack
              key={row.id}
              direction="row"
              justifyContent="space-between"
              alignItems="center"
              sx={{ borderBottom: 1, borderColor: 'divider', pb: 1 }}
            >
              <Typography>
                {row.gstin}
                {name ? ` (${name})` : ''}
                {primary ? ` — ${t('gst.branchPrimary')}` : ''}
                {active ? '' : ` — ${t('gst.branchInactive')}`}
              </Typography>
              <Stack direction="row" spacing={1}>
                <Button type="button" size="small" disabled={primary} onClick={() => {
                  setBranchError(null);
                  void updateCompanyGstin(row.id, { is_primary: true }).then(refresh).catch(fail);
                }}>
                  {t('gst.branchSetPrimary')}
                </Button>
                <Button type="button" size="small" onClick={() => openEdit(row)}>{t('gst.branchEdit')}</Button>
                <Button type="button" size="small" onClick={() => {
                  setBranchError(null);
                  void updateCompanyGstin(row.id, { is_active: !active }).then(refresh).catch(fail);
                }}>
                  {active ? t('gst.branchDeactivate') : t('gst.branchActivate')}
                </Button>
              </Stack>
            </Stack>
          );
        })}
        <TextField
          label={t('gst.branchGstin')}
          value={branchGstin}
          onChange={(e) => setBranchGstin(e.target.value.toUpperCase())}
        />
        <TextField label={t('gst.branchName')} value={branchName} onChange={(e) => setBranchName(e.target.value)} />
        <StateSelect value={branchState} onChange={(val) => setBranchState(val)} label={t('gst.branchState')} />
        <Button
          type="button"
          variant="outlined"
          disabled={!isValidGstin(branchGstin)}
          onClick={() => {
            setBranchError(null);
            void createCompanyGstin({
              gstin: branchGstin,
              legal_name: branchName,
              state: branchState,
              is_primary: false,
              is_active: true,
            }).then(() => {
              setBranchGstin('');
              setBranchName('');
              setBranchState('');
              return refresh();
            }).catch(fail);
          }}
        >
          {t('gst.branchAdd')}
        </Button>
      </Stack>
      <Dialog open={Boolean(editing)} onClose={() => setEditing(null)} fullWidth maxWidth="sm">
        <DialogTitle>{t('gst.branchEditTitle')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label={t('gst.branchGstin')}
              value={editGstin}
              onChange={(e) => setEditGstin(e.target.value.toUpperCase())}
            />
            <TextField label={t('gst.branchName')} value={editName} onChange={(e) => setEditName(e.target.value)} />
            <StateSelect value={editState} onChange={(val) => setEditState(val)} label={t('gst.branchState')} />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditing(null)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={!editing || !isValidGstin(editGstin)}
            onClick={() => {
              if (!editing) return;
              setBranchError(null);
              void updateCompanyGstin(editing.id, {
                gstin: editGstin,
                legal_name: editName,
                state: editState,
              }).then(() => {
                setEditing(null);
                return refresh();
              }).catch(fail);
            }}
          >
            {t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>
    </Paper>
  );
}
