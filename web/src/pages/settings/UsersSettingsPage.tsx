import { useState } from 'react';
import { capsForJobTemplate, type JobTemplate } from '@/cognitive/loadHelpers';
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
import { issueReferralCode } from '@/api/growth';
import { inviteCompanyUser, listCompanyUsers, resendCompanyUserInvite, revokeCompanyUserInvite, updateCompanyUser } from '@/api/resources';
import type { CompanyUser } from '@/types/domain';
import { confirmAction } from '@/utils/confirmBridge';
import { isReferralsEnabled } from '@/config/features';
import { useAuth } from '@/auth/AuthContext';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { StatusChip } from '@/components/StatusChip';
import { TwoStepVerificationPanel } from '@/components/TwoStepVerificationPanel';
import { SignedInDevicesPanel } from '@/components/SignedInDevicesPanel';
import { ForbiddenPage } from '@/pages/ForbiddenPage';
import { PageTitle } from '@/contextHelp';
import { OwnershipTransferDialog } from '@/components/settings/OwnershipTransferDialog';
import { PendingOwnershipNotice } from '@/components/settings/PendingOwnershipNotice';
import { t, useLocale } from '@/i18n';
import { canManageUsers } from '@/utils/permissions';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { useIdempotentSave } from '@/hooks/useIdempotentSave';
import { settingsErrorText } from '@/utils/settingsErrors';

const emptyInviteForm = {
  email: '',
  password: '',
  fullName: '',
  role: 'SALES_STAFF',
  canManageInventory: false,
  canImport: false,
  canCancelDocuments: false,
  canViewFinancialReports: false,
  canExport: false,
  canCreateSales: true,
  canCreatePurchases: false,
  canCreatePayments: true,
  canManagePolicies: false,
};

type InviteForm = typeof emptyInviteForm;

// F3-021: every branch returns the FULL capability set (explicit false where
// off) so `{ ...form, ...capsForRole(role) }` is a complete override — a switch
// from ACCOUNTANT to SALES_STAFF must not silently retain export / financial
// report access from the prior selection.
type RoleCaps = Pick<
  InviteForm,
  | 'canCreateSales'
  | 'canCreatePurchases'
  | 'canCreatePayments'
  | 'canViewFinancialReports'
  | 'canExport'
  | 'canManageInventory'
  | 'canImport'
  | 'canCancelDocuments'
  | 'canManagePolicies'
>;

function capsForRole(role: string): RoleCaps {
  const off: RoleCaps = {
    canCreateSales: false,
    canCreatePurchases: false,
    canCreatePayments: false,
    canViewFinancialReports: false,
    canExport: false,
    canManageInventory: false,
    canImport: false,
    canCancelDocuments: false,
    canManagePolicies: false,
  };
  if (role === 'ACCOUNTANT') {
    return {
      ...off,
      canCreatePurchases: true,
      canCreatePayments: true,
      canViewFinancialReports: true,
      canExport: true,
    };
  }
  if (role === 'VIEWER') {
    return off;
  }
  if (role === 'INVENTORY_STAFF') {
    return {
      ...off,
      canManageInventory: true,
      canCreatePurchases: true,
    };
  }
  if (role === 'AUDITOR') {
    return {
      ...off,
      canViewFinancialReports: true,
      canExport: true,
    };
  }
  if (role === 'POLICY_DESK') {
    return {
      ...off,
      canManagePolicies: true,
    };
  }
  if (role === 'MANAGER') {
    return {
      canCreateSales: true,
      canCreatePurchases: true,
      canCreatePayments: true,
      canViewFinancialReports: true,
      canExport: true,
      canManageInventory: true,
      canImport: true,
      canCancelDocuments: true,
      canManagePolicies: false,
    };
  }
  return { ...off, canCreateSales: true, canCreatePayments: true };
}

function hasAnyWorkCap(form: InviteForm): boolean {
  return (
    form.canCreateSales ||
    form.canCreatePurchases ||
    form.canCreatePayments ||
    form.canManageInventory ||
    form.canImport ||
    form.canCancelDocuments ||
    form.canViewFinancialReports ||
    form.canExport
  );
}

export function UsersSettingsPage() {
  useLocale();
  const { user } = useAuth();
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ['company-users'], queryFn: listCompanyUsers });
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<InviteForm>(emptyInviteForm);
  const [jobTemplate, setJobTemplate] = useState<JobTemplate>('custom');
  const [error, setError] = useState<string | null>(null);
  const [inviteToken, setInviteToken] = useState<string | null>(null);
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);
  const [createdWithPassword, setCreatedWithPassword] = useState(false);
  const [issuedCodes, setIssuedCodes] = useState<Record<number, string>>({});
  const [codeFor, setCodeFor] = useState<number | null>(null);
  // WP-ID1: the member being offered ownership.
  const [ownerFor, setOwnerFor] = useState<CompanyUser | null>(null);
  const [rewardType, setRewardType] = useState('FLAT');
  const [rewardValue, setRewardValue] = useState('0');
  const [issuingCode, setIssuingCode] = useState(false);

  const idem = useIdempotentSave();
  const inviteMutation = useMutation({
    mutationFn: () => inviteCompanyUser(form, idem.headers()),
    onSuccess: (created) => {
      idem.renew();
      const url = (created as { inviteUrl?: string; invite_url?: string }).inviteUrl
        ?? (created as { invite_url?: string }).invite_url
        ?? null;
      const token = (created as { inviteToken?: string; invite_token?: string }).inviteToken
        ?? (created as { invite_token?: string }).invite_token
        ?? null;
      setCreatedWithPassword(Boolean(form.password.trim()));
      setInviteToken(form.password.trim() ? null : token);
      setInviteUrl(form.password.trim() ? null : url);
      void qc.invalidateQueries({ queryKey: ['company-users'] });
    },
    onError: (err) => setError(settingsErrorText(err)),
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
      canCreateSales?: boolean;
      canCreatePurchases?: boolean;
      canCreatePayments?: boolean;
      isActive?: boolean;
    }) => {
      // SET-11b: refused (409) if someone else changed this person since the list was loaded.
      const row = qc.getQueryData<CompanyUser[]>(['company-users'])?.find((u) => u.id === id);
      return updateCompanyUser(id, { ...payload, ...(row?.updatedAt ? { expected_updated_at: row.updatedAt } : {}) });
    },
    onSuccess: (saved) => {
      // The answer carries the new change time; keep it so the next toggle is not seen as stale.
      qc.setQueryData<CompanyUser[]>(['company-users'], (rows) =>
        rows?.map((u) => (u.id === saved.id ? { ...u, ...saved } : u)),
      );
      void qc.invalidateQueries({ queryKey: ['company-users'] });
    },
    onError: (err) => {
      setError(settingsErrorText(err));
      void qc.invalidateQueries({ queryKey: ['company-users'] });
    },
  });

  // F3-022: confirm the high-impact caps; a click no longer silently grants
  // export / cancel / financial-report access with no feedback.
  const SENSITIVE_CAPS: Record<string, string> = {
    canExport: 'cog.capExport',
    canCancelDocuments: 'cog.capCancel',
    canViewFinancialReports: 'cog.capReports',
  };
  const togglePatch = async (id: number, cap: string, checked: boolean) => {
    if (checked && SENSITIVE_CAPS[cap]) {
      if (!(await confirmAction(t('cog.allowCap', { action: t(SENSITIVE_CAPS[cap]) })))) return;
    }
    patchMutation.mutate({ id, [cap]: checked });
  };
  const rowPending = (id: number) =>
    patchMutation.isPending &&
    (patchMutation.variables as { id?: number } | undefined)?.id === id;

  // F3-023: soft-deactivate only — revoke a member's access without a
  // destructive hard-remove. Reactivating needs no confirmation.
  const toggleActive = async (id: number, currentlyActive: boolean) => {
    if (currentlyActive && !(await confirmAction(t('users.deactivateConfirm')))) return;
    patchMutation.mutate({ id, isActive: !currentlyActive });
  };

  const [newLink, setNewLink] = useState<{ name: string; url: string; expires: string } | null>(null);
  const resend = useMutation({
    mutationFn: (m: { id: number; name: string }) => resendCompanyUserInvite(m.id).then((r) => ({ ...r, name: m.name })),
    onSuccess: (r) => {
      setNewLink({
        name: r.name,
        url: r.inviteUrl ?? r.inviteToken ?? '',
        expires: r.inviteExpiresAt ? new Date(r.inviteExpiresAt).toLocaleString() : '',
      });
      void qc.invalidateQueries({ queryKey: ['company-users'] });
    },
    onError: (err) => setError(settingsErrorText(err)),
  });
  const revoke = useMutation({
    mutationFn: (id: number) => revokeCompanyUserInvite(id),
    onSuccess: () => {
      setNewLink(null);
      void qc.invalidateQueries({ queryKey: ['company-users'] });
    },
    onError: (err) => setError(settingsErrorText(err)),
  });
  const askRevoke = async (id: number) => {
    if (await confirmAction(`${t('usersAdmin.revokeTitle')}\n\n${t('usersAdmin.revokeBody')}`)) revoke.mutate(id);
  };

  if (!canManageUsers(user)) return <ForbiddenPage />;

  const submitInvite = async () => {
    if (!hasAnyWorkCap(form) && form.role === 'SALES_STAFF') {
      const ok = await confirmAction(t('cog.noWorkPermissions'));
      if (!ok) return;
    }
    idem.once(inviteMutation.mutate);
  };

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <PageTitle>{t('nav.users')}</PageTitle>
        <Button
          variant="contained"
          onClick={() => {
            setForm(emptyInviteForm);
            setJobTemplate('custom');
            setInviteToken(null);
            setInviteUrl(null);
            setCreatedWithPassword(false);
            idem.renew();
            setOpen(true);
          }}
        >
          {t('common.invite')}
        </Button>
      </Stack>
      <PendingOwnershipNotice />
      <TwoStepVerificationPanel />
      <SignedInDevicesPanel />
      {error ? <HelpErrorAlert message={error} /> : null}
      {newLink ? (
        <Alert severity="success" onClose={() => setNewLink(null)}>
          <Stack spacing={0.5}>
            <span>{t('usersAdmin.newLink', { name: newLink.name, date: newLink.expires })}</span>
            <code style={{ wordBreak: 'break-all' }}>{newLink.url}</code>
            <Button size="small" sx={{ alignSelf: 'flex-start' }} onClick={() => void navigator.clipboard?.writeText(newLink.url)}>
              {t('usersAdmin.copy')}
            </Button>
          </Stack>
        </Alert>
      ) : null}
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={settingsErrorText(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {query.data?.length === 0 ? <EmptyState /> : null}
      {query.data && query.data.length > 0 ? (
        <Paper tabIndex={0} role="region" aria-label={t('common.scrollableTable')} sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('common.name')}</TableCell>
                <TableCell>{t('common.email')}</TableCell>
                <TableCell>{t('sweep2.role')}</TableCell>
                <TableCell>{t('sweep2.sales')}</TableCell>
                <TableCell>{t('sweep2.purchases')}</TableCell>
                <TableCell>{t('sweep2.payments')}</TableCell>
                <TableCell>{t('sweep2.inventory')}</TableCell>
                <TableCell>{t('sweep2.import')}</TableCell>
                <TableCell>{t('sweep2.cancel')}</TableCell>
                <TableCell>{t('sweep2.reports')}</TableCell>
                <TableCell>{t('sweep2.export')}</TableCell>
                <TableCell>{t('common.status')}</TableCell>
                <TableCell>{t('usersAdmin.colLastSignIn')}</TableCell>
                <TableCell align="right">{t('common.actions')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {query.data.map((u) => {
                const isOwner = u.role === 'OWNER';
                return (
                <TableRow key={u.id}>
                  <TableCell>{u.fullName}</TableCell>
                  <TableCell>{u.email}</TableCell>
                  <TableCell>
                    <StatusChip tone="info" label={u.role.replace(/_/g, ' ')} />
                  </TableCell>
                  <TableCell>
                    <Checkbox
                      inputProps={{ 'aria-label': `Sales: ${u.fullName || u.email}` }}
                      checked={!!u.canCreateSales}
                      disabled={isOwner || rowPending(u.id)}
                      onChange={(e) =>
                        togglePatch(u.id, 'canCreateSales', e.target.checked)
                      }
                    />
                  </TableCell>
                  <TableCell>
                    <Checkbox
                      inputProps={{ 'aria-label': `Purchases: ${u.fullName || u.email}` }}
                      checked={!!u.canCreatePurchases}
                      disabled={isOwner || rowPending(u.id)}
                      onChange={(e) =>
                        togglePatch(u.id, 'canCreatePurchases', e.target.checked)
                      }
                    />
                  </TableCell>
                  <TableCell>
                    <Checkbox
                      inputProps={{ 'aria-label': `Payments: ${u.fullName || u.email}` }}
                      checked={!!u.canCreatePayments}
                      disabled={isOwner || rowPending(u.id)}
                      onChange={(e) =>
                        togglePatch(u.id, 'canCreatePayments', e.target.checked)
                      }
                    />
                  </TableCell>
                  <TableCell>
                    <Checkbox
                      inputProps={{ 'aria-label': `Inventory: ${u.fullName || u.email}` }}
                      checked={u.canManageInventory}
                      disabled={isOwner || rowPending(u.id)}
                      onChange={(e) =>
                        togglePatch(u.id, 'canManageInventory', e.target.checked)
                      }
                    />
                  </TableCell>
                  <TableCell>
                    <Checkbox
                      inputProps={{ 'aria-label': `Import: ${u.fullName || u.email}` }}
                      checked={u.canImport}
                      disabled={isOwner || rowPending(u.id)}
                      onChange={(e) =>
                        togglePatch(u.id, 'canImport', e.target.checked)
                      }
                    />
                  </TableCell>
                  <TableCell>
                    <Checkbox
                      inputProps={{ 'aria-label': `Cancel: ${u.fullName || u.email}` }}
                      checked={!!u.canCancelDocuments}
                      disabled={isOwner || rowPending(u.id)}
                      onChange={(e) =>
                        togglePatch(u.id, 'canCancelDocuments', e.target.checked)
                      }
                    />
                  </TableCell>
                  <TableCell>
                    <Checkbox
                      inputProps={{ 'aria-label': `Reports: ${u.fullName || u.email}` }}
                      checked={u.canViewFinancialReports === true}
                      disabled={isOwner || rowPending(u.id)}
                      onChange={(e) =>
                        togglePatch(u.id, 'canViewFinancialReports', e.target.checked)
                      }
                    />
                  </TableCell>
                  <TableCell>
                    <Checkbox
                      inputProps={{ 'aria-label': `Export: ${u.fullName || u.email}` }}
                      checked={!!u.canExport}
                      disabled={isOwner || rowPending(u.id)}
                      onChange={(e) =>
                        togglePatch(u.id, 'canExport', e.target.checked)
                      }
                    />
                  </TableCell>
                  <TableCell>
                    {u.isActive
                      ? t('status.ACTIVE')
                      : u.inviteState === 'pending'
                        ? t('usersAdmin.invitePending', { date: u.inviteExpiresAt ? new Date(u.inviteExpiresAt).toLocaleDateString() : '' })
                        : u.inviteState === 'expired'
                          ? t('usersAdmin.inviteExpired')
                          : t('status.INACTIVE')}
                  </TableCell>
                  <TableCell>{u.lastLogin ? new Date(u.lastLogin).toLocaleString() : t('usersAdmin.never')}</TableCell>
                  <TableCell align="right">
                    {!u.isActive && (u.inviteState === 'pending' || u.inviteState === 'expired') ? (
                      <>
                        <Button
                          size="small"
                          disabled={resend.isPending}
                          onClick={() => resend.mutate({ id: u.id, name: u.fullName || u.email })}
                        >
                          {t('usersAdmin.resend')}
                        </Button>
                        <Button size="small" color="warning" disabled={revoke.isPending} onClick={() => void askRevoke(u.id)}>
                          {t('usersAdmin.revoke')}
                        </Button>
                      </>
                    ) : null}
                    {isReferralsEnabled() ? (
                      <Button
                        size="small"
                        onClick={() => {
                          setCodeFor(u.id);
                          setRewardType('FLAT');
                          setRewardValue('0');
                          setError(null);
                        }}
                      >
                        {t('growth.issueCode')}
                      </Button>
                    ) : null}
                    {issuedCodes[u.id] ? (
                      <Typography variant="caption" display="block">{t('growth.issuedFor')}: {issuedCodes[u.id]}</Typography>
                    ) : null}
                    {!isOwner && u.isActive ? (
                      <Button size="small" onClick={() => setOwnerFor(u)}>
                        {t('ownership.makeOwner')}
                      </Button>
                    ) : null}
                    {isOwner || (!u.isActive && (u.inviteState === 'pending' || u.inviteState === 'expired')) ? null : (
                      <Button
                        size="small"
                        color={u.isActive ? 'warning' : 'primary'}
                        disabled={rowPending(u.id)}
                        onClick={() => toggleActive(u.id, u.isActive !== false)}
                      >
                        {u.isActive ? t('users.deactivate') : t('users.reactivate')}
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </Paper>
      ) : null}

      <Dialog open={codeFor != null} onClose={() => setCodeFor(null)} fullWidth maxWidth="xs">
        <DialogTitle>{t('growth.issueCode')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField select label={t('growth.rewardType')} value={rewardType} onChange={(e) => setRewardType(e.target.value)}>
              <MenuItem value="FLAT">{t('settingsSweep.rewardFlat')}</MenuItem>
              <MenuItem value="PERCENT">{t('settingsSweep.rewardPercent')}</MenuItem>
            </TextField>
            <TextField label={t('growth.rewardValue')} value={rewardValue} onChange={(e) => setRewardValue(e.target.value)} />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCodeFor(null)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={issuingCode || codeFor == null}
            onClick={() => {
              if (codeFor == null) return;
              const userId = codeFor;
              setIssuingCode(true);
              void issueReferralCode({
                referrer_user: userId,
                reward_type: rewardType,
                reward_value: rewardValue || '0',
              }).then((row) => {
                setIssuedCodes((current) => ({ ...current, [userId]: row.code }));
                setCodeFor(null);
                setError(null);
              }).catch((err) => setError(settingsErrorText(err)))
                .finally(() => setIssuingCode(false));
            }}
          >
            {t('growth.issueCode')}
          </Button>
        </DialogActions>
      </Dialog>

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
              value={form.password}
              helperText={t('users.passwordOptional')}
              onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
            />
            <TextField
              label={t('auth.fullName')}
              value={form.fullName}
              onChange={(e) => setForm((f) => ({ ...f, fullName: e.target.value }))}
            />
            <TextField
              select
              label={t('users.role')}
              value={form.role}
              onChange={(e) => {
                const role = e.target.value;
                setJobTemplate('custom'); // the role's own defaults replace a template picked earlier
                setForm((f) => ({ ...f, role, ...capsForRole(role) }));
              }}
            >
              <MenuItem value="SALES_STAFF">{t('users.salesStaff')}</MenuItem>
              <MenuItem value="INVENTORY_STAFF">{t('users.inventoryStaff')}</MenuItem>
              <MenuItem value="ACCOUNTANT">{t('users.accountant')}</MenuItem>
              <MenuItem value="MANAGER">{t('users.manager')}</MenuItem>
              <MenuItem value="AUDITOR">{t('users.auditor')}</MenuItem>
              <MenuItem value="VIEWER">{t('users.viewer')}</MenuItem>
              <MenuItem value="POLICY_DESK">{t('users.policyDesk')}</MenuItem>
            </TextField>
            <TextField
              select
              label={t('cog.jobBrowser')}
              value={jobTemplate}
              onChange={async (e) => {
                const template = e.target.value as JobTemplate;
                const caps = capsForJobTemplate(template);
                // A template can grant export, cancel and financial-report rights in one pick:
                // ask for the same confirmation as ticking those boxes one by one.
                if (caps) {
                  const sensitive = Object.keys(SENSITIVE_CAPS).filter(
                    (cap) => (caps as Record<string, unknown>)[cap] === true && !(form as Record<string, unknown>)[cap],
                  );
                  if (sensitive.length > 0) {
                    const actions = sensitive.map((cap) => t(SENSITIVE_CAPS[cap])).join(', ');
                    if (!(await confirmAction(t('cog.allowCap', { action: actions })))) return;
                  }
                }
                setJobTemplate(template);
                if (caps) setForm((f) => ({ ...f, ...caps }));
              }}
            >
              <MenuItem value="cashier">{t('cog.jobCashier')}</MenuItem>
              <MenuItem value="store">{t('cog.jobStore')}</MenuItem>
              <MenuItem value="bookkeeper">{t('cog.jobBookkeeper')}</MenuItem>
              <MenuItem value="owner">{t('cog.jobOwner')}</MenuItem>
              <MenuItem value="custom">{t('cog.jobCustom')}</MenuItem>
            </TextField>
            <Typography variant="caption" color="text.secondary">{t('cog.jobBrowser')}</Typography>
            <FormControlLabel
              control={
                <Checkbox
                  checked={form.canCreateSales}
                  onChange={(e) => setForm((f) => ({ ...f, canCreateSales: e.target.checked }))}
                />
              }
              label={t('users.canCreateSales')}
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={form.canCreatePurchases}
                  onChange={(e) => setForm((f) => ({ ...f, canCreatePurchases: e.target.checked }))}
                />
              }
              label={t('users.canCreatePurchases')}
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={form.canCreatePayments}
                  onChange={(e) => setForm((f) => ({ ...f, canCreatePayments: e.target.checked }))}
                />
              }
              label={t('users.canRecordPayments')}
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={form.canManageInventory}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, canManageInventory: e.target.checked }))
                  }
                />
              }
              label={t('users.canManageInventory')}
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={form.canImport}
                  onChange={(e) => setForm((f) => ({ ...f, canImport: e.target.checked }))}
                />
              }
              label={t('users.canImport')}
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
              label={t('users.canCancel')}
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
              label={t('users.canViewReports')}
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={form.canExport}
                  onChange={(e) => setForm((f) => ({ ...f, canExport: e.target.checked }))}
                />
              }
              label={t('users.canExport')}
            />
            {!hasAnyWorkCap(form) ? (
              <Alert severity="warning">
                {t('users.noPermissions')}
              </Alert>
            ) : null}
            {createdWithPassword ? (
              <Alert severity="success">
                {t('users.accountCreated')}
              </Alert>
            ) : null}
            {inviteUrl || inviteToken ? (
              <Alert severity="success">
                <Stack spacing={1}>
                  <Typography variant="body2">
                    {inviteUrl ? t('users.inviteLink', { url: inviteUrl }) : t('users.inviteToken', { token: inviteToken ?? '' })}
                  </Typography>
                  <Button
                    size="small"
                    variant="outlined"
                    sx={{ alignSelf: 'flex-start' }}
                    onClick={() => void navigator.clipboard.writeText(inviteUrl ?? inviteToken ?? '')}
                  >
                    {t('users.copyInvite')}
                  </Button>
                </Stack>
              </Alert>
            ) : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => { setOpen(false); setInviteToken(null); setInviteUrl(null); setCreatedWithPassword(false); }}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={!form.email || inviteMutation.isPending}
            onClick={submitInvite}
          >
            {t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>
      <OwnershipTransferDialog member={ownerFor} onClose={() => setOwnerFor(null)} />
    </Stack>
  );
}
