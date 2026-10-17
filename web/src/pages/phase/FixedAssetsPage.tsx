import { useState } from 'react';
import Accordion from '@mui/material/Accordion';
import AccordionDetails from '@mui/material/AccordionDetails';
import AccordionSummary from '@mui/material/AccordionSummary';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Drawer from '@mui/material/Drawer';
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
import axios from 'axios';
import { getErrorMessage } from '@/api/client';
import * as api from '@/api/resources';
import { AccountSelect } from '@/components/accounting/AccountSelect';
import { todayIso } from '@/components/billing';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { PageShell, StatusChip, type Row } from '@/pages/phase/phaseShared';
import { formatMoney, toNumber } from '@/utils/money';
import { t } from '@/i18n';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { useAuth } from '@/auth/AuthContext';
import { canPostJournals } from '@/utils/permissions';

const DEFAULT_USEFUL_LIFE_MONTHS = '36';

type DisposeTarget = { id: number; name: string; cost: number; depreciated: number; acquisitionDate: string };

type AssetForm = {
  id: number | null;
  name: string;
  cost: string;
  acquisitionDate: string;
  usefulLifeMonths: string;
  method: 'SLM' | 'WDV';
  salvage: string;
  wdvRate: string;
  funding: 'ALREADY_BOOKED' | 'CASH' | 'BANK' | 'SUPPLIER';
  bank: string;
  supplier: string;
  category: string;
  assetAccount: string;
  accumulatedAccount: string;
  expenseAccount: string;
  depreciated: number;
};

const blankForm = (): AssetForm => ({
  id: null, name: '', cost: '', acquisitionDate: todayIso(), usefulLifeMonths: DEFAULT_USEFUL_LIFE_MONTHS, method: 'SLM',
  salvage: '', wdvRate: '', funding: 'ALREADY_BOOKED', bank: '', supplier: '', category: '', assetAccount: '',
  accumulatedAccount: '', expenseAccount: '', depreciated: 0,
});

const num = (value: unknown) => toNumber(value as string | number | null | undefined);

export function FixedAssetsPage() {
  const { writesBlocked: subscriptionBlocked } = useSubscriptionGate();
  const { user } = useAuth();
  const writesBlocked = subscriptionBlocked || !canPostJournals(user);
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ['fixed-assets'], queryFn: () => api.listFixedAssets(), retry: false });
  const summary = useQuery({ queryKey: ['fixed-assets-summary'], queryFn: api.getFixedAssetSummary, retry: false, enabled: query.isSuccess });
  const [form, setForm] = useState<AssetForm | null>(null);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  // ACS-12: disposal needs a date, the money received and where it went -- not a bare confirm.
  const [disposeTarget, setDisposeTarget] = useState<DisposeTarget | null>(null);
  const [disposalDate, setDisposalDate] = useState(todayIso());
  const [disposalProceeds, setDisposalProceeds] = useState('');
  const [receivedIn, setReceivedIn] = useState('CASH');
  const [typedName, setTypedName] = useState('');
  const [chargePartMonth, setChargePartMonth] = useState(true);
  const [detail, setDetail] = useState<Row | null>(null);
  const [runOpen, setRunOpen] = useState(false);
  const banks = useQuery({
    queryKey: ['bank-accounts'], queryFn: api.listBankAccounts, enabled: disposeTarget !== null || form !== null,
  });
  const suppliers = useQuery({ queryKey: ['suppliers-all'], queryFn: () => api.listSuppliers(), enabled: form?.funding === 'SUPPLIER' });
  const accounts = useQuery({ queryKey: ['accounts'], queryFn: api.listAccounts, enabled: form !== null });
  const presets = useQuery({ queryKey: ['asset-presets'], queryFn: api.listFixedAssetPresets, enabled: form !== null && form.id === null });

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['fixed-assets'] });
    void qc.invalidateQueries({ queryKey: ['fixed-assets-summary'] });
    void qc.invalidateQueries({ queryKey: ['asset-schedule'] });
  };

  const save = useMutation({
    mutationFn: (f: AssetForm) => {
      const schedule = {
        name: f.name,
        acquisitionDate: f.acquisitionDate,
        usefulLifeMonths: Number(f.usefulLifeMonths),
        method: f.method,
        salvageValue: Number(f.salvage) || 0,
        wdvAnnualRate: f.method === 'WDV' ? Number(f.wdvRate) || 0 : 0,
      };
      if (f.id !== null) {
        // Depreciation already posted against the old schedule: the schedule inputs are history, only the name moves.
        return f.depreciated > 0 ? api.updateFixedAsset(f.id, { name: f.name }) : api.updateFixedAsset(f.id, schedule);
      }
      return api.createFixedAsset({
        ...schedule,
        acquisitionCost: Number(f.cost),
        funding: f.funding,
        fundingBankAccount: f.funding === 'BANK' ? Number(f.bank) : null,
        fundingSupplier: f.funding === 'SUPPLIER' ? Number(f.supplier) : null,
        category: f.category,
        ...(f.assetAccount ? { assetAccount: Number(f.assetAccount) } : {}),
        ...(f.accumulatedAccount ? { accumulatedDepreciationAccount: Number(f.accumulatedAccount) } : {}),
        ...(f.expenseAccount ? { depreciationExpenseAccount: Number(f.expenseAccount) } : {}),
      });
    },
    onSuccess: () => { setForm(null); setError(''); refresh(); },
    onError: (e) => setError(getErrorMessage(e)),
  });
  const dispose = useMutation({
    mutationFn: (target: DisposeTarget) => {
      const proceeds = Number(disposalProceeds) || 0;
      const payload: Record<string, unknown> = { confirm: true, proceeds, disposalDate };
      if (chargePartMonth) payload.chargePartMonth = true;
      if (proceeds > 0) {
        if (receivedIn === 'BANK_AGGREGATE') payload.cashAccountCode = '1500';
        else if (receivedIn !== 'CASH') payload.bankAccount = Number(receivedIn);
      }
      return api.disposeFixedAsset(target.id, payload);
    },
    onSuccess: () => { setError(''); setDisposeTarget(null); refresh(); },
    onError: (e) => setError(getErrorMessage(e)),
  });
  const draftFix = useMutation({
    mutationFn: api.draftAssetRegisterFix,
    onSuccess: (data) => { setError(''); setInfo(t('assets.fixDrafted', { number: data.number })); },
    onError: (e) => setError(getErrorMessage(e)),
  });

  const openCreate = () => { setError(''); setForm(blankForm()); };
  const openEdit = (row: Row) => {
    setError('');
    setForm({
      ...blankForm(),
      id: Number(row.id),
      name: String(row.name ?? ''),
      cost: String(row.acquisitionCost ?? ''),
      acquisitionDate: String(row.acquisitionDate ?? todayIso()).slice(0, 10),
      usefulLifeMonths: String(row.usefulLifeMonths ?? DEFAULT_USEFUL_LIFE_MONTHS),
      method: row.method === 'WDV' ? 'WDV' : 'SLM',
      salvage: String(row.salvageValue ?? ''),
      wdvRate: String(row.wdvAnnualRate ?? ''),
      depreciated: num(row.depreciatedAmount),
    });
  };
  const openDispose = (row: Row) => {
    setDisposeTarget({
      id: Number(row.id), name: String(row.name ?? ''), cost: num(row.acquisitionCost),
      depreciated: num(row.depreciatedAmount), acquisitionDate: String(row.acquisitionDate ?? '').slice(0, 10),
    });
    setDisposalDate(todayIso());
    setDisposalProceeds('');
    setReceivedIn('CASH');
    setTypedName('');
    setChargePartMonth(true);
    setError('');
  };

  const nbv = disposeTarget ? Math.max(0, disposeTarget.cost - disposeTarget.depreciated) : 0;
  const proceedsNumber = Number(disposalProceeds) || 0;
  const gainOrLoss = proceedsNumber - nbv;
  const disposalDateError = !disposeTarget
    ? ''
    : disposalDate > todayIso()
      ? t('phase.disposalDateFuture')
      : disposeTarget.acquisitionDate && disposalDate < disposeTarget.acquisitionDate
        ? t('phase.disposalDateBeforePurchase')
        : '';

  if (query.isLoading) return <LoadingState />;
  if (query.isError) {
    // The module is a pilot limitation and is switched off per deployment: say so instead of showing a raw error.
    if (axios.isAxiosError(query.error) && query.error.response?.status === 404) {
      return (
        <PageShell title={t('phase.fixedAssets')} subtitle={t('phase.fixedAssetsSubtitle')}>
          <EmptyState description={t('assets.switchedOff')} />
        </PageShell>
      );
    }
    return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  }
  const rows = (query.data ?? []) as Row[];
  const s = summary.data;
  const gl = s?.registerVsGl;
  const mismatch = gl ? num(gl.costDifference) !== 0 || num(gl.accumulatedDifference) !== 0 : false;
  const failing = rows.filter((r) => Array.isArray(r.depreciationErrors) && (r.depreciationErrors as unknown[]).length > 0);

  const schemaErrors = form
    ? {
        cost: form.id === null && !(Number(form.cost) > 0) ? t('assets.errCost') : '',
        life: !(Number(form.usefulLifeMonths) >= 1) ? t('assets.errLife') : '',
        salvage: Number(form.salvage) < 0 || (Number(form.cost) > 0 && Number(form.salvage) >= Number(form.cost)) ? t('assets.errSalvage') : '',
        rate: form.method === 'WDV' && (Number(form.wdvRate) <= 0 || Number(form.wdvRate) > 100) ? t('assets.errRate') : '',
        bank: form.id === null && form.funding === 'BANK' && !form.bank ? t('assets.errBank') : '',
        supplier: form.id === null && form.funding === 'SUPPLIER' && !form.supplier ? t('assets.errSupplier') : '',
      }
    : null;
  const formInvalid = !form || !form.name.trim() || Object.values(schemaErrors ?? {}).some(Boolean);
  const frozen = Boolean(form && form.id !== null && form.depreciated > 0);

  return (
    <PageShell
      title={t('phase.fixedAssets')}
      subtitle={t('phase.fixedAssetsSubtitle')}
      actions={
        <Stack direction="row" spacing={1}>
          <Button disabled={writesBlocked} onClick={() => setRunOpen(true)}>{t('assets.runDepreciation')}</Button>
          <Button variant="contained" onClick={openCreate} disabled={writesBlocked}>{t('phase.addAsset')}</Button>
        </Stack>
      }
    >
      {error && !form && !disposeTarget ? <HelpErrorAlert message={error} /> : null}
      {info ? <Alert severity="success" onClose={() => setInfo('')}>{info}</Alert> : null}
      {s ? (
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr 1fr', md: 'repeat(4, 1fr)' }, gap: 1 }} data-testid="asset-summary">
          <Card label={t('assets.totalCost')} value={formatMoney(num(s.totalCost))} />
          <Card label={t('assets.accumulated')} value={formatMoney(num(s.accumulated))} />
          <Card label={t('assets.nbv')} value={formatMoney(num(s.netBookValue))} />
          <Card label={t('assets.thisMonth')} value={formatMoney(num(s.thisMonthCharge))} />
        </Box>
      ) : null}
      {mismatch && gl ? (
        <Alert
          severity="warning"
          action={!writesBlocked ? (
            <Button color="inherit" size="small" disabled={draftFix.isPending} onClick={() => draftFix.mutate()}>{t('assets.draftFix')}</Button>
          ) : undefined}
        >
          {t('assets.registerMismatch', {
            cost: formatMoney(num(gl.costDifference)),
            accumulated: formatMoney(num(gl.accumulatedDifference)),
          })}
        </Alert>
      ) : null}
      {failing.length > 0 ? (
        <Alert severity="error">
          <Typography variant="body2" sx={{ fontWeight: 600 }}>{t('assets.depreciationFailed')}</Typography>
          {failing.map((r) => (
            <Typography key={String(r.id)} variant="body2">
              {String(r.name)}: {(r.depreciationErrors as Array<{ month: string; reason: string }>).map((e) => `${e.month} ${e.reason}`.trim()).join('; ')}
            </Typography>
          ))}
        </Alert>
      ) : null}
      <Paper variant="outlined" sx={{ overflowX: 'auto' }}>
        <Table size="small" aria-label={t('phase.fixedAssets')}>
          <TableHead>
            <TableRow>
              <TableCell>{t('common.name')}</TableCell>
              <TableCell align="right">{t('phase.assetCost')}</TableCell>
              <TableCell align="right">{t('assets.accumulated')}</TableCell>
              <TableCell align="right">{t('assets.nbv')}</TableCell>
              <TableCell>{t('assets.method')}</TableCell>
              <TableCell>{t('assets.lastCharge')}</TableCell>
              <TableCell>{t('common.status')}</TableCell>
              <TableCell align="right" />
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.length === 0 ? <TableRow><TableCell colSpan={8}>{t('phase.noFixedAssets')}</TableCell></TableRow> : null}
            {rows.map((row) => {
              const errs = (row.depreciationErrors as unknown[] | undefined) ?? [];
              const catchup = (row.catchupMonths as unknown[] | undefined) ?? [];
              return (
                <TableRow key={String(row.id)} hover>
                  <TableCell>{String(row.name)}</TableCell>
                  <TableCell align="right">{formatMoney(num(row.acquisitionCost))}</TableCell>
                  <TableCell align="right">{formatMoney(num(row.depreciatedAmount))}</TableCell>
                  <TableCell align="right">{formatMoney(num(row.netBookValue))}</TableCell>
                  <TableCell>{row.method === 'WDV' ? t('assets.methodWdv') : t('assets.methodSlm')}</TableCell>
                  <TableCell>{String(row.lastDepreciationMonth || '—')}</TableCell>
                  <TableCell>
                    <Stack direction="row" spacing={0.5} alignItems="center">
                      <StatusChip value={row.status} />
                      {errs.length ? <Chip size="small" color="error" label={t('assets.chipError')} /> : null}
                      {catchup.length ? <Chip size="small" color="warning" label={t('assets.chipCatchup', { count: String(catchup.length) })} /> : null}
                    </Stack>
                  </TableCell>
                  <TableCell align="right">
                    <Stack direction="row" spacing={1} justifyContent="flex-end">
                      <Button size="small" onClick={() => setDetail(row)} aria-label={`${t('assets.details')} ${String(row.name)}`}>{t('assets.details')}</Button>
                      {row.status === 'ACTIVE' ? <Button size="small" disabled={writesBlocked} onClick={() => openEdit(row)}>{t('common.edit')}</Button> : null}
                      {row.status === 'ACTIVE' ? (
                        <Button size="small" color="error" disabled={writesBlocked} onClick={() => openDispose(row)}>{t('phase.assetDispose')}</Button>
                      ) : null}
                    </Stack>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </Paper>

      <Dialog open={form !== null} onClose={() => setForm(null)} fullWidth maxWidth="sm">
        <DialogTitle>{form?.id != null ? t('phase.editFixedAsset') : t('phase.fixedAsset')}</DialogTitle>
        <DialogContent>
          {form && schemaErrors ? (
            <Stack spacing={2} sx={{ mt: 1 }}>
              {error ? <HelpErrorAlert message={error} /> : null}
              {frozen ? <Alert severity="info">{t('phase.assetScheduleFrozen')}</Alert> : null}
              {form.id === null && presets.data ? (
                <TextField
                  select size="small" label={t('assets.preset')} value={form.category}
                  helperText={presets.data.note}
                  onChange={(e) => {
                    const p = presets.data!.results.find((x) => x.key === e.target.value);
                    setForm(p
                      ? { ...form, category: p.key, usefulLifeMonths: String(p.usefulLifeMonths), method: p.method === 'WDV' ? 'WDV' : 'SLM', wdvRate: p.wdvAnnualRate }
                      : { ...form, category: '' });
                  }}
                >
                  <MenuItem value="">{t('assets.noPreset')}</MenuItem>
                  {presets.data.results.map((p) => <MenuItem key={p.key} value={p.key}>{p.name}</MenuItem>)}
                </TextField>
              ) : null}
              <TextField label={t('common.name')} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
                <TextField
                  label={t('phase.acquisitionCost')} type="number" value={form.cost} onChange={(e) => setForm({ ...form, cost: e.target.value })}
                  disabled={form.id !== null} error={Boolean(form.cost) && Boolean(schemaErrors.cost)}
                  helperText={form.id !== null ? t('phase.assetCostFixed') : schemaErrors.cost && form.cost ? schemaErrors.cost : undefined} sx={{ flex: 1 }}
                />
                <TextField
                  label={t('phase.acquisitionDate')} type="date" value={form.acquisitionDate} onChange={(e) => setForm({ ...form, acquisitionDate: e.target.value })}
                  InputLabelProps={{ shrink: true }} disabled={frozen} sx={{ flex: 1 }}
                />
              </Stack>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
                <TextField
                  label={t('phase.usefulLifeMonths')} type="number" value={form.usefulLifeMonths} disabled={frozen}
                  onChange={(e) => setForm({ ...form, usefulLifeMonths: e.target.value })}
                  error={Boolean(schemaErrors.life)} helperText={schemaErrors.life || undefined} sx={{ flex: 1 }}
                />
                <TextField select label={t('assets.method')} value={form.method} disabled={frozen} onChange={(e) => setForm({ ...form, method: e.target.value as 'SLM' | 'WDV' })} sx={{ flex: 1 }}>
                  <MenuItem value="SLM">{t('assets.methodSlm')}</MenuItem>
                  <MenuItem value="WDV">{t('assets.methodWdv')}</MenuItem>
                </TextField>
              </Stack>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
                <TextField
                  label={t('assets.salvage')} type="number" value={form.salvage} disabled={frozen} onChange={(e) => setForm({ ...form, salvage: e.target.value })}
                  error={Boolean(schemaErrors.salvage)} helperText={schemaErrors.salvage || undefined} sx={{ flex: 1 }}
                />
                {form.method === 'WDV' ? (
                  <TextField
                    label={t('assets.wdvRate')} type="number" value={form.wdvRate} disabled={frozen} onChange={(e) => setForm({ ...form, wdvRate: e.target.value })}
                    error={Boolean(schemaErrors.rate)} helperText={schemaErrors.rate || undefined} sx={{ flex: 1 }}
                  />
                ) : null}
              </Stack>
              {form.id === null ? (
                <>
                  <TextField select label={t('assets.funding')} value={form.funding} onChange={(e) => setForm({ ...form, funding: e.target.value as AssetForm['funding'] })} helperText={t(`assets.fundingHelp_${form.funding}`)}>
                    <MenuItem value="ALREADY_BOOKED">{t('assets.funding_ALREADY_BOOKED')}</MenuItem>
                    <MenuItem value="CASH">{t('assets.funding_CASH')}</MenuItem>
                    <MenuItem value="BANK">{t('assets.funding_BANK')}</MenuItem>
                    <MenuItem value="SUPPLIER">{t('assets.funding_SUPPLIER')}</MenuItem>
                  </TextField>
                  {form.funding === 'BANK' ? (
                    <TextField select required label={t('expenses.bankAccount')} value={form.bank} onChange={(e) => setForm({ ...form, bank: e.target.value })} error={Boolean(schemaErrors.bank)}>
                      {(banks.data ?? []).map((b) => <MenuItem key={String(b.id)} value={String(b.id)}>{String(b.name)}</MenuItem>)}
                    </TextField>
                  ) : null}
                  {form.funding === 'SUPPLIER' ? (
                    <TextField select required label={t('phase.journalSupplier')} value={form.supplier} onChange={(e) => setForm({ ...form, supplier: e.target.value })} error={Boolean(schemaErrors.supplier)}>
                      {(suppliers.data ?? []).map((sp) => <MenuItem key={String(sp.id)} value={String(sp.id)}>{String(sp.name)}</MenuItem>)}
                    </TextField>
                  ) : null}
                  <Accordion disableGutters variant="outlined">
                    <AccordionSummary><Typography variant="body2">{t('assets.advancedAccounts')}</Typography></AccordionSummary>
                    <AccordionDetails>
                      <Stack spacing={1.5}>
                        <AccountSelect size="small" accounts={accounts.data} label={t('assets.assetAccount')} value={form.assetAccount} onChange={(id) => setForm({ ...form, assetAccount: id })} helperText={t('assets.accountDefault')} />
                        <AccountSelect size="small" accounts={accounts.data} label={t('assets.accumulatedAccount')} value={form.accumulatedAccount} onChange={(id) => setForm({ ...form, accumulatedAccount: id })} />
                        <AccountSelect size="small" accounts={accounts.data} label={t('assets.expenseAccount')} value={form.expenseAccount} onChange={(id) => setForm({ ...form, expenseAccount: id })} />
                      </Stack>
                    </AccordionDetails>
                  </Accordion>
                </>
              ) : null}
            </Stack>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setForm(null)}>{t('common.cancel')}</Button>
          <Button variant="contained" disabled={writesBlocked || formInvalid || save.isPending} onClick={() => form && save.mutate(form)}>
            {t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={disposeTarget !== null} onClose={() => setDisposeTarget(null)} fullWidth maxWidth="xs">
        <DialogTitle>{t('phase.disposeAssetTitle')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {disposeTarget ? <Alert severity="info">{t('phase.disposeAssetBody', { name: disposeTarget.name })}</Alert> : null}
            {error ? <HelpErrorAlert message={error} /> : null}
            <TextField
              type="date" label={t('phase.disposalDate')} value={disposalDate} onChange={(e) => setDisposalDate(e.target.value)}
              InputLabelProps={{ shrink: true }} error={Boolean(disposalDateError)} helperText={disposalDateError || undefined}
            />
            <TextField type="number" label={t('phase.disposalProceeds')} value={disposalProceeds} onChange={(e) => setDisposalProceeds(e.target.value)} inputProps={{ min: 0, step: 0.01 }} />
            {proceedsNumber > 0 ? (
              <TextField select label={t('phase.disposalReceivedIn')} value={receivedIn} onChange={(e) => setReceivedIn(e.target.value)}>
                <MenuItem value="CASH">{t('phase.disposalCashInHand')}</MenuItem>
                <MenuItem value="BANK_AGGREGATE">{t('phase.disposalBankAggregate')}</MenuItem>
                {(banks.data ?? []).map((b) => <MenuItem key={String(b.id)} value={String(b.id)}>{String(b.name)}</MenuItem>)}
              </TextField>
            ) : null}
            <FormControlLabel
              control={<Checkbox checked={chargePartMonth} onChange={(e) => setChargePartMonth(e.target.checked)} />}
              label={t('assets.chargePartMonth')}
            />
            <Alert severity={gainOrLoss < 0 ? 'warning' : 'success'}>
              {t('phase.disposalNbv', { amount: formatMoney(nbv) })} ·{' '}
              {gainOrLoss > 0.004
                ? t('phase.disposalGain', { amount: formatMoney(gainOrLoss) })
                : gainOrLoss < -0.004
                  ? t('phase.disposalLoss', { amount: formatMoney(-gainOrLoss) })
                  : t('phase.disposalBreakEven')}
            </Alert>
            <TextField label={t('phase.disposalTypeName')} value={typedName} onChange={(e) => setTypedName(e.target.value)} helperText={disposeTarget?.name} />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDisposeTarget(null)} disabled={dispose.isPending}>{t('common.cancel')}</Button>
          <Button
            color="error" variant="contained"
            disabled={writesBlocked || dispose.isPending || !disposeTarget || Boolean(disposalDateError) || proceedsNumber < 0 || typedName.trim() !== disposeTarget.name}
            onClick={() => disposeTarget && dispose.mutate(disposeTarget)}
          >
            {t('phase.disposeAssetConfirm')}
          </Button>
        </DialogActions>
      </Dialog>

      <DepreciationDialog
        open={runOpen}
        onClose={() => setRunOpen(false)}
        lastMonth={s?.lastCompletedMonth ?? ''}
        onDone={() => { refresh(); }}
      />

      <Drawer anchor="right" open={detail !== null} onClose={() => setDetail(null)} PaperProps={{ sx: { width: { xs: '100%', sm: 520 }, p: 2 } }}>
        {detail ? <AssetDetail asset={detail} onClose={() => setDetail(null)} /> : null}
      </Drawer>
    </PageShell>
  );
}

function Card({ label, value }: { label: string; value: string }) {
  return (
    <Paper variant="outlined" sx={{ p: 1.5 }}>
      <Typography variant="caption" color="text.secondary">{label}</Typography>
      <Typography variant="h6">{value}</Typography>
    </Paper>
  );
}

function AssetDetail({ asset, onClose }: { asset: Row; onClose: () => void }) {
  const schedule = useQuery({
    queryKey: ['asset-schedule', asset.id],
    queryFn: () => api.getFixedAssetSchedule(Number(asset.id)),
  });
  return (
    <Stack spacing={1.5} role="region" aria-label={t('assets.details')}>
      <Typography variant="h6">{String(asset.name)}</Typography>
      <Typography variant="body2" color="text.secondary">
        {t('assets.detailLine', { cost: formatMoney(num(asset.acquisitionCost)), life: String(asset.usefulLifeMonths), method: asset.method === 'WDV' ? t('assets.methodWdv') : t('assets.methodSlm') })}
      </Typography>
      {asset.acquisitionJournalNumber ? <Typography variant="body2">{t('assets.bookedBy', { number: String(asset.acquisitionJournalNumber) })}</Typography> : null}
      {schedule.isLoading ? <LoadingState /> : null}
      {schedule.isError ? <HelpErrorAlert message={getErrorMessage(schedule.error)} /> : null}
      {schedule.data?.disposal ? (
        <Alert severity="info">{t('assets.disposedBy', { number: schedule.data.disposal.number, date: schedule.data.disposal.date })}</Alert>
      ) : null}
      {schedule.data ? (
        <Box sx={{ overflowX: 'auto' }}>
          <Table size="small" aria-label={t('assets.schedule')}>
            <TableHead>
              <TableRow>
                <TableCell>{t('assets.month')}</TableCell>
                <TableCell align="right">{t('phase.reconAmount')}</TableCell>
                <TableCell>{t('common.status')}</TableCell>
                <TableCell>{t('assets.voucher')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {schedule.data.rows.map((r) => (
                <TableRow key={r.month}>
                  <TableCell>{r.month}</TableCell>
                  <TableCell align="right">{formatMoney(num(r.amount))}</TableCell>
                  <TableCell>
                    <Chip size="small" variant="outlined" color={r.status === 'posted' ? 'success' : r.status === 'missing' ? 'error' : 'default'} label={t(`assets.rowStatus_${r.status}`)} />
                  </TableCell>
                  <TableCell>{r.number}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Box>
      ) : null}
      <Button onClick={onClose}>{t('common.close')}</Button>
    </Stack>
  );
}

function DepreciationDialog({ open, onClose, lastMonth, onDone }: { open: boolean; onClose: () => void; lastMonth: string; onDone: () => void }) {
  const [month, setMonth] = useState('');
  const [result, setResult] = useState<api.DepreciationRun | null>(null);
  const [error, setError] = useState('');
  const effective = month || lastMonth;
  const run = useMutation({
    mutationFn: (dryRun: boolean) => api.runFixedAssetDepreciation({ month: effective, dryRun }),
    onSuccess: (data) => { setResult(data); setError(''); if (!data.dryRun) onDone(); },
    onError: (e) => setError(getErrorMessage(e)),
  });
  const close = () => { setResult(null); setError(''); setMonth(''); onClose(); };
  return (
    <Dialog open={open} onClose={close} fullWidth maxWidth="md">
      <DialogTitle>{t('assets.runDepreciation')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography variant="body2">{t('assets.runBody')}</Typography>
          <TextField
            type="month" size="small" label={t('assets.throughMonth')} value={effective}
            onChange={(e) => { setMonth(e.target.value); setResult(null); }}
            InputLabelProps={{ shrink: true }} inputProps={{ max: lastMonth || undefined }} sx={{ maxWidth: 220 }}
          />
          {error ? <HelpErrorAlert message={error} /> : null}
          {result ? (
            <Stack spacing={1}>
              <Alert severity={result.dryRun ? 'info' : result.assets.some((a) => a.errors.length) ? 'warning' : 'success'}>
                {result.dryRun
                  ? t('assets.previewSummary', { count: String(result.assets.reduce((n, a) => n + a.months.length, 0)) })
                  : t('assets.runSummary', { posted: String(result.posted), total: formatMoney(num(result.total)) })}
              </Alert>
              {result.assets.map((a) => (
                <Box key={a.asset}>
                  <Typography variant="subtitle2">{a.name}</Typography>
                  {a.months.map((m) => (
                    <Typography key={m.month} variant="body2" color={m.status === 'blocked' ? 'error' : undefined}>
                      {m.month}: {formatMoney(num(m.amount))} · {t(`assets.runStatus_${m.status}`)}
                    </Typography>
                  ))}
                  {a.errors.map((e) => <Typography key={e} variant="caption" color="error" display="block">{e}</Typography>)}
                </Box>
              ))}
            </Stack>
          ) : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={close}>{t('common.close')}</Button>
        <Button disabled={run.isPending || !effective} onClick={() => run.mutate(true)}>{t('assets.preview')}</Button>
        <Button variant="contained" disabled={run.isPending || !effective || !result || !result.dryRun || result.assets.length === 0} onClick={() => run.mutate(false)}>
          {t('assets.postNow')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
