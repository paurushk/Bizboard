import { useState } from 'react';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import FormControlLabel from '@mui/material/FormControlLabel';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as api from '@/api/resources';
import { AsyncSection } from '@/components/settings/AsyncSection';
import { SettingsPage } from '@/components/settings/SettingsPage';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { asRows, DataTable, type Row } from '@/pages/phase/phaseShared';
import { t } from '@/i18n';
import type { BankAccount } from '@/types/domain';
import { isValidIfsc, isValidUpiVpa } from '@/utils/gst';
import { formatMoney, toNumber } from '@/utils/money';
import { useIdempotentSave } from '@/hooks/useIdempotentSave';
import { settingsErrorText } from '@/utils/settingsErrors';

type Form = {
  name: string;
  accountType: string;
  accountNumber: string;
  ifsc: string;
  upiId: string;
  openingBalance: string;
  openingAsOf: string;
  isDefault: boolean;
  printOnInvoices: boolean;
};

const EMPTY: Form = {
  name: '',
  accountType: 'CURRENT',
  accountNumber: '',
  ifsc: '',
  upiId: '',
  openingBalance: '',
  openingAsOf: '',
  isDefault: false,
  printOnInvoices: false,
};

const KEYS = ['bank-accounts'];

export function BankAccountsPage() {
  const { writesBlocked } = useSubscriptionGate();
  const qc = useQueryClient();
  const query = useQuery({ queryKey: [...KEYS, 'all'], queryFn: api.listAllBankAccounts });
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<BankAccount | null>(null);
  const [form, setForm] = useState<Form>(EMPTY);
  const [shownNumber, setShownNumber] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [switchOff, setSwitchOff] = useState<BankAccount | null>(null);

  const refresh = () => void qc.invalidateQueries({ queryKey: KEYS });
  const idem = useIdempotentSave();

  const openNew = () => {
    idem.renew();
    setEditing(null);
    setForm(EMPTY);
    setShownNumber(null);
    setError('');
    setOpen(true);
  };
  const openEdit = (row: BankAccount) => {
    setEditing(row);
    setForm({
      name: row.name,
      accountType: row.accountType ?? 'CURRENT',
      accountNumber: '',
      ifsc: row.ifsc ?? '',
      upiId: row.upiId ?? '',
      openingBalance: row.openingBalance == null ? '' : String(row.openingBalance),
      openingAsOf: row.openingAsOf ?? '',
      isDefault: Boolean(row.isDefault),
      printOnInvoices: Boolean(row.printOnInvoices),
    });
    setShownNumber(null);
    setError('');
    setOpen(true);
  };

  const save = useMutation({
    mutationFn: () => {
      const ifsc = form.ifsc.trim().toUpperCase();
      if (ifsc && !isValidIfsc(ifsc)) throw new Error(t('banks.ifscInvalid'));
      if (form.upiId.trim() && !isValidUpiVpa(form.upiId.trim())) throw new Error(t('banks.upiInvalid'));
      const payload: Record<string, unknown> = {
        name: form.name.trim(),
        account_type: form.accountType,
        ifsc,
        upi_id: form.upiId.trim(),
        is_default: form.isDefault,
        print_on_invoices: form.accountType === 'CASH_BOX' ? false : form.printOnInvoices,
      };
      // Only send a number the owner actually typed; blank keeps the saved one.
      if (form.accountNumber.trim()) payload.account_number = form.accountNumber;
      if (!editing?.openingLocked) {
        payload.opening_balance = form.openingBalance.trim() === '' ? '0' : form.openingBalance;
        payload.opening_as_of = form.openingAsOf || null;
      }
      if (editing?.updatedAt) payload.expected_updated_at = editing.updatedAt;
      return editing ? api.updateBankAccount(editing.id, payload) : api.createBankAccount(payload, idem.headers());
    },
    onSuccess: () => {
      idem.renew();
      setOpen(false);
      setError('');
      refresh();
    },
    onError: (e) => setError(settingsErrorText(e)),
  });

  const patch = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Record<string, unknown> }) => api.updateBankAccount(id, body),
    onSuccess: refresh,
    onError: (e) => setError(settingsErrorText(e)),
  });

  const deactivate = useMutation({
    mutationFn: (id: number) => api.deactivateBankAccount(id),
    onSuccess: () => {
      setSwitchOff(null);
      refresh();
    },
    onError: (e) => {
      setSwitchOff(null);
      setError(settingsErrorText(e));
    },
  });

  const reveal = useMutation({
    mutationFn: (id: number) => api.revealBankAccountNumber(id),
    onSuccess: (data) => setShownNumber(data.accountNumber),
    onError: (e) => setError(settingsErrorText(e)),
  });

  const byId = (row: Row) => (query.data ?? []).find((a) => a.id === Number(row.id)) as BankAccount;

  return (
    <SettingsPage
      title={t('banks.title')}
      purpose={t('banks.purpose')}
      actions={
        <Button variant="contained" onClick={openNew} disabled={writesBlocked}>
          {t('banks.add')}
        </Button>
      }
    >
      {error && !open ? <HelpErrorAlert message={error} /> : null}
      <AsyncSection
        query={query}
        isEmpty={(rows) => rows.length === 0}
        empty={{ description: t('banks.empty') }}
      >
        {(rows) => (
          <>
            <DataTable
              rows={asRows(rows)}
              empty={t('banks.empty')}
              columns={[
                { key: 'name', label: t('banks.name') },
                {
                  key: 'accountType',
                  label: t('banks.type'),
                  render: (row) =>
                    row.accountType === 'CASH_BOX'
                      ? t('banks.typeCashBox')
                      : row.accountType === 'SAVINGS'
                        ? t('banks.typeSavings')
                        : t('banks.typeCurrent'),
                },
                {
                  key: 'accountNumberMasked',
                  label: t('banks.colAccount'),
                  render: (row) =>
                    row.accountType === 'CASH_BOX' ? (
                      '—'
                    ) : (
                      <Stack>
                        <span>{String(row.accountNumberMasked || '—')}</span>
                        <Typography variant="caption" color="text.secondary">
                          {row.hasFullNumber ? t('banks.fullNumberSaved') : t('banks.noFullNumber')}
                        </Typography>
                      </Stack>
                    ),
                },
                { key: 'ifsc', label: t('banks.ifsc') },
                { key: 'upiId', label: t('banks.colUpi') },
                {
                  key: 'openingBalance',
                  label: t('banks.colOpening'),
                  render: (row) => formatMoney(toNumber(row.openingBalance as string | number | undefined)),
                },
                {
                  key: 'isDefault',
                  label: '',
                  render: (row) => (
                    <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                      {row.isDefault ? <Chip size="small" color="primary" label={t('banks.chipDefault')} /> : null}
                      {row.printOnInvoices ? (
                        <Chip size="small" color="success" variant="outlined" label={t('banks.chipInvoices')} />
                      ) : null}
                      {row.isActive === false ? <Chip size="small" label={t('banks.chipOff')} /> : null}
                    </Stack>
                  ),
                },
              ]}
              actions={(row) => {
                const account = byId(row);
                const active = account.isActive !== false;
                return (
                  <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                    <Button size="small" disabled={writesBlocked} onClick={() => openEdit(account)}>
                      {t('banks.edit')}
                    </Button>
                    {active && !account.isDefault ? (
                      <Button
                        size="small"
                        disabled={writesBlocked}
                        onClick={() => patch.mutate({ id: account.id, body: { is_default: true } })}
                      >
                        {t('banks.makeDefault')}
                      </Button>
                    ) : null}
                    {active && !account.printOnInvoices && account.hasFullNumber && account.accountType !== 'CASH_BOX' ? (
                      <Button
                        size="small"
                        disabled={writesBlocked}
                        onClick={() => patch.mutate({ id: account.id, body: { print_on_invoices: true } })}
                      >
                        {t('banks.useOnInvoices')}
                      </Button>
                    ) : null}
                    {active ? (
                      <Button size="small" color="error" disabled={writesBlocked} onClick={() => setSwitchOff(account)}>
                        {t('banks.switchOff')}
                      </Button>
                    ) : (
                      <Button
                        size="small"
                        disabled={writesBlocked}
                        onClick={() => patch.mutate({ id: account.id, body: { is_active: true } })}
                      >
                        {t('banks.switchOn')}
                      </Button>
                    )}
                  </Stack>
                );
              }}
            />
            <Typography variant="caption" color="text.secondary">
              {t('banks.invoiceChangeNote')}
            </Typography>
          </>
        )}
      </AsyncSection>

      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editing ? t('banks.editTitle') : t('banks.newTitle')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label={t('banks.name')}
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              required
            />
            <TextField
              select
              label={t('banks.type')}
              value={form.accountType}
              onChange={(e) => setForm({ ...form, accountType: e.target.value })}
            >
              <MenuItem value="CURRENT">{t('banks.typeCurrent')}</MenuItem>
              <MenuItem value="SAVINGS">{t('banks.typeSavings')}</MenuItem>
              <MenuItem value="CASH_BOX">{t('banks.typeCashBox')}</MenuItem>
            </TextField>
            {form.accountType !== 'CASH_BOX' ? (
              <>
                <TextField
                  label={t('banks.accountNumber')}
                  value={form.accountNumber}
                  onChange={(e) => setForm({ ...form, accountNumber: e.target.value })}
                  helperText={
                    editing?.hasFullNumber
                      ? `${editing.accountNumberMasked ?? ''} · ${t('banks.accountNumberKeep')}`
                      : t('banks.accountNumberHelp')
                  }
                  slotProps={{ htmlInput: { inputMode: 'numeric', autoComplete: 'off' } }}
                />
                {editing?.hasFullNumber ? (
                  <Stack direction="row" spacing={1} alignItems="center">
                    <Button
                      size="small"
                      onClick={() => (shownNumber === null ? reveal.mutate(editing.id) : setShownNumber(null))}
                      disabled={reveal.isPending}
                    >
                      {shownNumber === null ? t('banks.showNumber') : t('banks.hideNumber')}
                    </Button>
                    {shownNumber !== null ? (
                      <Typography sx={{ fontFamily: 'monospace' }}>{shownNumber}</Typography>
                    ) : null}
                  </Stack>
                ) : null}
                <TextField
                  label={t('banks.ifsc')}
                  value={form.ifsc}
                  onChange={(e) => setForm({ ...form, ifsc: e.target.value })}
                />
                <TextField
                  label={t('banks.upi')}
                  value={form.upiId}
                  onChange={(e) => setForm({ ...form, upiId: e.target.value })}
                />
              </>
            ) : null}
            <TextField
              label={t('banks.opening')}
              type="number"
              value={form.openingBalance}
              disabled={Boolean(editing?.openingLocked)}
              onChange={(e) => setForm({ ...form, openingBalance: e.target.value })}
              helperText={editing?.openingLocked ? t('banks.openingLocked') : undefined}
            />
            <TextField
              label={t('banks.openingAsOf')}
              type="date"
              value={form.openingAsOf}
              disabled={Boolean(editing?.openingLocked)}
              onChange={(e) => setForm({ ...form, openingAsOf: e.target.value })}
              InputLabelProps={{ shrink: true }}
            />
            <FormControlLabel
              control={
                <Switch checked={form.isDefault} onChange={(e) => setForm({ ...form, isDefault: e.target.checked })} />
              }
              label={t('banks.chipDefault')}
            />
            {form.accountType !== 'CASH_BOX' ? (
              <FormControlLabel
                control={
                  <Switch
                    checked={form.printOnInvoices}
                    onChange={(e) => setForm({ ...form, printOnInvoices: e.target.checked })}
                  />
                }
                label={
                  <Stack>
                    <span>{t('banks.useOnInvoices')}</span>
                    <Typography variant="caption" color="text.secondary">
                      {t('banks.useOnInvoicesHelp')}
                    </Typography>
                  </Stack>
                }
              />
            ) : null}
            {error ? <HelpErrorAlert message={error} /> : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={writesBlocked || !form.name.trim() || save.isPending}
            onClick={() => idem.once(save.mutate)}
          >
            {t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>

      <ConfirmDialog
        open={switchOff !== null}
        title={t('banks.switchOffTitle')}
        body={t('banks.switchOffBody')}
        confirmLabel={t('banks.switchOff')}
        confirmColor="error"
        confirming={deactivate.isPending}
        onClose={() => setSwitchOff(null)}
        onConfirm={() => switchOff && deactivate.mutate(switchOff.id)}
      />
    </SettingsPage>
  );
}
