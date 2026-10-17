import { useMemo, useRef, useState } from 'react';
import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Divider from '@mui/material/Divider';
import Drawer from '@mui/material/Drawer';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TablePagination from '@mui/material/TablePagination';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import * as api from '@/api/resources';
import { todayIso } from '@/components/billing';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { ErrorState, LoadingState } from '@/components/PageState';
import { formatMoney } from '@/utils/money';
import { t } from '@/i18n';
import { asRows, DataTable, PageShell } from '@/pages/phase/phaseShared';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { useAuth } from '@/auth/AuthContext';
import { AccountSelect } from '@/components/accounting/AccountSelect';
import { canPostJournals } from '@/utils/permissions';
import type { JournalEntry } from '@/types/domain';

type FormLine = {
  account: string;
  debit: string;
  credit: string;
  costCenter: string;
  customer: string;
  supplier: string;
  narration: string;
};
type PartyOption = { id: number; name: string };

// Accounts that must carry a customer or supplier tag (mirrors the server rule).
const CUSTOMER_CONTROL = new Set(['1200', '2300']);
const SUPPLIER_CONTROL = new Set(['2100', '1250']);

const blankLine = (): FormLine => ({ account: '', debit: '', credit: '', costCenter: '', customer: '', supplier: '', narration: '' });
const blankLines = () => [blankLine(), blankLine()];

function newToken(): string {
  try {
    return globalThis.crypto.randomUUID();
  } catch {
    return `jv-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  }
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function JournalsPage() {
  const { writesBlocked: subscriptionBlocked } = useSubscriptionGate();
  const { user } = useAuth();
  // ACS-00: one gate for every write button -- subscription lapse or no journal-posting right.
  const writesBlocked = subscriptionBlocked || !canPostJournals(user);
  const qc = useQueryClient();

  // ACS-23: server-side filters and paging.
  const [status, setStatus] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(25);
  const q = useDebouncedValue(search.trim(), 300);
  const filterParams = useMemo(() => {
    const p: Record<string, string> = {};
    if (status) p.status = status;
    if (dateFrom) p.date_from = dateFrom;
    if (dateTo) p.date_to = dateTo;
    if (q) p.q = q;
    return p;
  }, [status, dateFrom, dateTo, q]);
  const query = useQuery({
    queryKey: ['journals', filterParams, page, pageSize],
    queryFn: () => api.listJournalsPage({ ...filterParams, page: page + 1, pageSize }),
  });
  const accounts = useQuery({ queryKey: ['accounts'], queryFn: api.listAccounts });
  const costCenters = useQuery({ queryKey: ['cost-centers'], queryFn: api.listCostCenters });

  // Form (create or edit a draft).
  const [open, setOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [narration, setNarration] = useState('');
  const [reference, setReference] = useState('');
  const [entryDate, setEntryDate] = useState(todayIso());
  const [lines, setLines] = useState<FormLine[]>(blankLines());
  const [error, setError] = useState('');
  const token = useRef(newToken());
  const [initialSnap, setInitialSnap] = useState('');
  const snapshot = () => JSON.stringify({ narration, reference, entryDate, lines });
  const dirty = open && snapshot() !== initialSnap;
  const [confirmClose, setConfirmClose] = useState(false);

  const needsCustomer = lines.some((l) => CUSTOMER_CONTROL.has(codeOf(l.account)));
  const needsSupplier = lines.some((l) => SUPPLIER_CONTROL.has(codeOf(l.account)));
  function codeOf(id: string): string {
    return (accounts.data ?? []).find((a) => String(a.id) === id)?.code ?? '';
  }
  const customers = useQuery({
    queryKey: ['journal-customers'],
    queryFn: () => api.listCustomers(),
    enabled: open && needsCustomer,
  });
  const suppliers = useQuery({
    queryKey: ['journal-suppliers'],
    queryFn: () => api.listSuppliers(),
    enabled: open && needsSupplier,
  });
  const customerOptions: PartyOption[] = (customers.data ?? []).map((c) => ({ id: Number(c.id), name: String(c.name) }));
  const supplierOptions: PartyOption[] = (suppliers.data ?? []).map((c) => ({ id: Number(c.id), name: String(c.name) }));

  const begin = (next: { id: number | null; narration: string; reference: string; entryDate: string; lines: FormLine[] }) => {
    setEditingId(next.id);
    setNarration(next.narration);
    setReference(next.reference);
    setEntryDate(next.entryDate);
    setLines(next.lines);
    setError('');
    token.current = newToken();
    setInitialSnap(JSON.stringify({
      narration: next.narration,
      reference: next.reference,
      entryDate: next.entryDate,
      lines: next.lines,
    }));
    setOpen(true);
  };
  const openNew = () => begin({ id: null, narration: '', reference: '', entryDate: todayIso(), lines: blankLines() });
  const openEdit = (r: JournalEntry) =>
    begin({
      id: r.id,
      narration: r.narration ?? '',
      reference: r.reference ?? '',
      entryDate: r.entryDate,
      lines: (r.lines ?? []).map((l) => ({
        account: String(l.account),
        debit: Number(l.debit) > 0 ? String(l.debit) : '',
        credit: Number(l.credit) > 0 ? String(l.credit) : '',
        costCenter: l.costCenter ? String(l.costCenter) : '',
        customer: l.customer ? String(l.customer) : '',
        supplier: l.supplier ? String(l.supplier) : '',
        narration: l.narration ?? '',
      })),
    });
  const requestClose = () => (dirty ? setConfirmClose(true) : setOpen(false));

  const totals = useMemo(() => {
    const debit = lines.reduce((s, l) => s + (Number(l.debit) || 0), 0);
    const credit = lines.reduce((s, l) => s + (Number(l.credit) || 0), 0);
    return { debit, credit, balanced: Math.abs(debit - credit) < 0.005 && debit > 0 };
  }, [lines]);

  // Client rules that mirror the server: a half-filled line is flagged, not dropped silently.
  const lineIssues = lines.map((l) => {
    const has = l.account || l.debit || l.credit || l.customer || l.supplier || l.costCenter;
    if (!has) return '';
    if (!l.account) return t('phase.journalLineNoAccount');
    if (!(Number(l.debit) > 0) && !(Number(l.credit) > 0)) return t('phase.journalLineNoAmount');
    const code = codeOf(l.account);
    if (CUSTOMER_CONTROL.has(code) && !l.customer) return t('phase.journalNeedsCustomer');
    if (SUPPLIER_CONTROL.has(code) && !l.supplier) return t('phase.journalNeedsSupplier');
    return '';
  });
  const hasIssues = lineIssues.some(Boolean);

  const save = useMutation({
    mutationFn: () => {
      const payload = {
        narration,
        reference,
        entryDate,
        ...(editingId === null ? { clientToken: token.current } : {}),
        lines: lines
          .filter((l) => l.account)
          .map((l) => ({
            account: Number(l.account),
            debit: Number(l.debit) || 0,
            credit: Number(l.credit) || 0,
            costCenter: l.costCenter ? Number(l.costCenter) : null,
            customer: l.customer ? Number(l.customer) : null,
            supplier: l.supplier ? Number(l.supplier) : null,
            narration: l.narration,
          })),
      };
      return editingId === null ? api.createJournal(payload) : api.updateJournal(editingId, payload);
    },
    onSuccess: () => {
      setOpen(false);
      setEditingId(null);
      void qc.invalidateQueries({ queryKey: ['journals'] });
    },
    onError: (e) => setError(getErrorMessage(e)),
  });

  // ACS-24: "already posted/changed" means the screen is stale; refresh instead of showing a dead end.
  const staleOrError = (e: unknown) => {
    const code = (e as { response?: { data?: { error?: { code?: string }; code?: string } } })?.response?.data;
    if (code?.error?.code === 'journal_not_draft' || code?.code === 'journal_not_draft') {
      setError(t('phase.journalAlreadyChanged'));
      void qc.invalidateQueries({ queryKey: ['journals'] });
      return;
    }
    setError(getErrorMessage(e));
  };
  const post = useMutation({
    mutationFn: (id: number) => api.postJournal(id),
    onSuccess: () => {
      setError('');
      void qc.invalidateQueries({ queryKey: ['journals'] });
    },
    onError: staleOrError,
  });
  const reverse = useMutation({
    mutationFn: (id: number) => api.reverseJournal(id),
    onSuccess: () => {
      setError('');
      void qc.invalidateQueries({ queryKey: ['journals'] });
    },
    onError: staleOrError,
  });
  const discard = useMutation({
    mutationFn: (id: number) => api.discardJournal(id),
    onSuccess: () => {
      setError('');
      setDetail(null);
      void qc.invalidateQueries({ queryKey: ['journals'] });
    },
    onError: staleOrError,
  });
  const [exporting, setExporting] = useState(false);
  const runExport = async (file: 'csv' | 'xlsx') => {
    setExporting(true);
    try {
      downloadBlob(await api.exportJournals(filterParams, file), `journals.${file}`);
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setExporting(false);
    }
  };

  const [confirm, setConfirm] = useState<{ mode: 'post' | 'reverse' | 'discard'; id: number } | null>(null);
  const [detail, setDetail] = useState<JournalEntry | null>(null);

  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  const journalRows = asRows(query.data?.results);
  const total = query.data?.count ?? journalRows.length;
  const confirmTarget = confirm ? (journalRows.find((r) => Number(r.id) === confirm.id) as unknown as JournalEntry | undefined) : undefined;
  const filtered = Boolean(status || dateFrom || dateTo || q);

  const setLine = (idx: number, patch: Partial<FormLine>) => {
    const next = [...lines];
    next[idx] = { ...next[idx], ...patch };
    setLines(next);
  };

  return (
    <PageShell
      title={t('phase.journals')}
      subtitle={t('phase.journalsSubtitle')}
      actions={
        <Stack direction="row" spacing={1}>
          <Button disabled={exporting} onClick={() => void runExport('csv')}>
            {t('phase.journalExportCsv')}
          </Button>
          <Button disabled={exporting} onClick={() => void runExport('xlsx')}>
            {t('phase.journalExportXlsx')}
          </Button>
          <Button variant="contained" onClick={openNew} disabled={writesBlocked}>
            {t('phase.newVoucher')}
          </Button>
        </Stack>
      }
    >
      {error && !open ? <HelpErrorAlert message={error} /> : null}
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} sx={{ mb: 2 }}>
        <TextField select size="small" label={t('common.status')} value={status} onChange={(e) => { setStatus(e.target.value); setPage(0); }} sx={{ minWidth: 150 }}>
          <MenuItem value="">{t('phase.journalAllStatuses')}</MenuItem>
          <MenuItem value="DRAFT">{t('status.DRAFT')}</MenuItem>
          <MenuItem value="POSTED">{t('status.POSTED')}</MenuItem>
          <MenuItem value="REVERSED">{t('status.REVERSED')}</MenuItem>
          <MenuItem value="DISCARDED">{t('phase.journalDiscarded')}</MenuItem>
        </TextField>
        <TextField size="small" type="date" label={t('phase.journalFrom')} value={dateFrom} onChange={(e) => { setDateFrom(e.target.value); setPage(0); }} InputLabelProps={{ shrink: true }} />
        <TextField size="small" type="date" label={t('phase.journalTo')} value={dateTo} onChange={(e) => { setDateTo(e.target.value); setPage(0); }} InputLabelProps={{ shrink: true }} />
        <TextField size="small" label={t('phase.journalSearch')} value={search} onChange={(e) => { setSearch(e.target.value); setPage(0); }} sx={{ flex: 1 }} />
      </Stack>
      <DataTable
        rows={journalRows}
        empty={filtered ? t('phase.journalNoMatch') : t('phase.noJournals')}
        columns={[
          { key: 'number', label: t('common.number') },
          { key: 'entryDate', label: t('common.date') },
          { key: 'status', label: t('common.status'), status: true },
          { key: 'totalDebit', label: t('phase.journalAmount'), money: true },
          {
            key: 'sourceLabel',
            label: t('phase.journalSource'),
            render: (r) => {
              const path = typeof r.sourcePath === 'string' ? r.sourcePath : '';
              const label = r.sourceType === 'MANUAL_JOURNAL' || !r.sourceType
                ? t('phase.journalManualEntry')
                : String(r.sourceLabel ?? '');
              return path ? (
                <Typography component={RouterLink} to={path} variant="body2" sx={{ color: 'primary.main' }}>
                  {label}
                </Typography>
              ) : (
                label
              );
            },
          },
          { key: 'narration', label: t('phase.journalNarration') },
        ]}
        rowLabel={(r) => String(r.number ?? '')}
        stackOnMobile
        actions={(r) => (
          <Stack direction="row" spacing={0.5} justifyContent="flex-end">
            <Button size="small" onClick={() => setDetail(r as unknown as JournalEntry)} aria-label={`${t('phase.journalView')} ${String(r.number ?? '')}`}>
              {t('phase.journalView')}
            </Button>
            {r.status === 'DRAFT' ? (
              <>
                <Button size="small" disabled={writesBlocked} onClick={() => openEdit(r as unknown as JournalEntry)}>
                  {t('common.edit')}
                </Button>
                <Button size="small" color="warning" disabled={writesBlocked} onClick={() => setConfirm({ mode: 'discard', id: Number(r.id) })}>
                  {t('phase.journalDiscard')}
                </Button>
                <Button size="small" variant="contained" disabled={writesBlocked} onClick={() => setConfirm({ mode: 'post', id: Number(r.id) })}>
                  {t('phase.journalPost')}
                </Button>
              </>
            ) : r.status === 'POSTED' && r.canReverse === true ? (
              <Button size="small" color="warning" disabled={writesBlocked} onClick={() => setConfirm({ mode: 'reverse', id: Number(r.id) })}>
                {t('phase.journalReverse')}
              </Button>
            ) : null}
          </Stack>
        )}
      />
      <TablePagination
        component="div"
        count={total}
        page={page}
        rowsPerPage={pageSize}
        rowsPerPageOptions={[25, 50, 100]}
        onPageChange={(_e, p) => setPage(p)}
        onRowsPerPageChange={(e) => { setPageSize(Number(e.target.value)); setPage(0); }}
      />

      <Dialog open={open} onClose={requestClose} fullWidth maxWidth="lg">
        <DialogTitle>{editingId === null ? t('phase.journalVoucher') : t('phase.journalEditVoucher')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
              <TextField
                type="date"
                label={t('phase.journalEntryDate')}
                value={entryDate}
                onChange={(e) => setEntryDate(e.target.value)}
                InputLabelProps={{ shrink: true }}
                sx={{ maxWidth: 220 }}
              />
              <TextField label={t('phase.journalReference')} value={reference} onChange={(e) => setReference(e.target.value)} inputProps={{ maxLength: 120 }} sx={{ maxWidth: 260 }} />
              <TextField label={t('phase.journalNarration')} value={narration} onChange={(e) => setNarration(e.target.value)} fullWidth />
            </Stack>
            {lines.map((line, idx) => {
              const code = codeOf(line.account);
              const wantsCustomer = CUSTOMER_CONTROL.has(code);
              const wantsSupplier = SUPPLIER_CONTROL.has(code);
              return (
                <Stack key={idx} spacing={0.5}>
                  <Stack direction={{ xs: 'column', md: 'row' }} spacing={1}>
                    <AccountSelect
                      accounts={accounts.data}
                      label={t('phase.journalAccount')}
                      value={line.account}
                      onChange={(id) => setLine(idx, { account: id, customer: '', supplier: '' })}
                      error={Boolean(lineIssues[idx]) && !line.account}
                      sx={{ flex: 2, minWidth: 200 }}
                    />
                    <TextField
                      label={t('phase.journalDebit')}
                      type="number"
                      inputProps={{ min: 0, step: 0.01 }}
                      value={line.debit}
                      onChange={(e) => {
                        const raw = e.target.value;
                        setLine(idx, { debit: raw === '' || Number(raw) >= 0 ? raw : '0', credit: '' });
                      }}
                    />
                    <TextField
                      label={t('phase.journalCredit')}
                      type="number"
                      inputProps={{ min: 0, step: 0.01 }}
                      value={line.credit}
                      onChange={(e) => {
                        const raw = e.target.value;
                        setLine(idx, { credit: raw === '' || Number(raw) >= 0 ? raw : '0', debit: '' });
                      }}
                    />
                    <TextField
                      select
                      label={t('phase.journalCostCenter')}
                      value={line.costCenter}
                      onChange={(e) => setLine(idx, { costCenter: e.target.value })}
                      sx={{ minWidth: 150 }}
                    >
                      <MenuItem value="">{t('phase.journalNoCostCenter')}</MenuItem>
                      {(costCenters.data ?? [])
                        .filter((c) => c.isActive !== false)
                        .map((c) => (
                          <MenuItem key={String(c.id)} value={String(c.id)}>
                            {String(c.code)} · {String(c.name)}
                          </MenuItem>
                        ))}
                    </TextField>
                    {lines.length > 2 ? (
                      <Button size="small" onClick={() => setLines(lines.filter((_, i) => i !== idx))} aria-label={t('phase.journalRemoveLine')}>
                        {t('phase.journalRemoveLine')}
                      </Button>
                    ) : null}
                  </Stack>
                  <Stack direction={{ xs: 'column', md: 'row' }} spacing={1}>
                    {wantsCustomer || wantsSupplier ? (
                      <Autocomplete
                        size="small"
                        sx={{ flex: 1, minWidth: 220 }}
                        options={wantsCustomer ? customerOptions : supplierOptions}
                        getOptionLabel={(o) => o.name}
                        isOptionEqualToValue={(o, v) => o.id === v.id}
                        value={
                          (wantsCustomer ? customerOptions : supplierOptions).find(
                            (o) => String(o.id) === (wantsCustomer ? line.customer : line.supplier),
                          ) ?? null
                        }
                        onChange={(_e, next) =>
                          setLine(idx, wantsCustomer ? { customer: next ? String(next.id) : '' } : { supplier: next ? String(next.id) : '' })
                        }
                        renderInput={(params) => (
                          <TextField
                            {...params}
                            required
                            label={wantsCustomer ? t('phase.journalCustomer') : t('phase.journalSupplier')}
                          />
                        )}
                      />
                    ) : null}
                    <TextField
                      size="small"
                      label={t('phase.journalLineNarration')}
                      value={line.narration}
                      onChange={(e) => setLine(idx, { narration: e.target.value })}
                      inputProps={{ maxLength: 255 }}
                      sx={{ flex: 2 }}
                    />
                  </Stack>
                  {lineIssues[idx] ? <Typography variant="caption" color="error">{lineIssues[idx]}</Typography> : null}
                </Stack>
              );
            })}
            <Button size="small" onClick={() => setLines([...lines, blankLine()])} disabled={writesBlocked}>
              {t('phase.journalAddLine')}
            </Button>
            <Alert severity={totals.balanced ? 'success' : 'warning'}>
              {t('phase.journalDebit')} {formatMoney(totals.debit)} · {t('phase.journalCredit')} {formatMoney(totals.credit)}
              {totals.balanced ? ` · ${t('phase.journalBalanced')}` : ` · ${t('phase.journalNotBalanced')}`}
            </Alert>
            {error ? <HelpErrorAlert message={error} /> : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={requestClose}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={writesBlocked || !totals.balanced || hasIssues || save.isPending}
            onClick={() => save.mutate()}
          >
            {t('phase.journalSaveDraft')}
          </Button>
        </DialogActions>
      </Dialog>

      <ConfirmDialog
        open={confirmClose}
        title={t('phase.journalDiscardChangesTitle')}
        body={t('phase.journalDiscardChangesBody')}
        confirmLabel={t('phase.journalDiscardChanges')}
        confirmColor="error"
        onClose={() => setConfirmClose(false)}
        onConfirm={() => {
          setConfirmClose(false);
          setOpen(false);
        }}
      />

      <ConfirmDialog
        open={confirm !== null}
        title={
          confirm?.mode === 'reverse'
            ? t('phase.journalReverseConfirm')
            : confirm?.mode === 'discard'
              ? t('phase.journalDiscardConfirm')
              : t('phase.journalPostConfirm')
        }
        body={[
          confirm?.mode === 'reverse'
            ? t('phase.journalReverseBody')
            : confirm?.mode === 'discard'
              ? t('phase.journalDiscardBody')
              : t('phase.journalPostBody'),
          confirmTarget
            ? `${confirmTarget.number} · ${confirmTarget.entryDate} · ${formatMoney(Number(confirmTarget.totalDebit ?? 0))} · ${confirmTarget.lines?.length ?? 0} ${t('phase.journalLines')}`
            : '',
        ]
          .filter(Boolean)
          .join('\n')}
        confirmLabel={
          confirm?.mode === 'reverse' ? t('phase.journalReverse') : confirm?.mode === 'discard' ? t('phase.journalDiscard') : t('phase.journalPost')
        }
        confirmColor={confirm?.mode === 'post' ? 'primary' : 'error'}
        confirming={
          confirm?.mode === 'reverse' ? reverse.isPending : confirm?.mode === 'discard' ? discard.isPending : post.isPending
        }
        onClose={() => setConfirm(null)}
        onConfirm={() => {
          if (!confirm) return;
          if (confirm.mode === 'reverse') reverse.mutate(confirm.id);
          else if (confirm.mode === 'discard') discard.mutate(confirm.id);
          else post.mutate(confirm.id);
          setConfirm(null);
        }}
      />

      <Drawer anchor="right" open={detail !== null} onClose={() => setDetail(null)} PaperProps={{ sx: { width: { xs: '100%', sm: 560 }, p: 2 } }}>
        {detail ? (
          <Stack spacing={1.5} role="region" aria-label={t('phase.journalDetail')}>
            <Typography variant="h6">{detail.number}</Typography>
            <Typography variant="body2" color="text.secondary">
              {detail.entryDate} · {t(`status.${detail.status}`)}
            </Typography>
            {detail.narration ? <Typography variant="body2">{detail.narration}</Typography> : null}
            {detail.reference ? (
              <Typography variant="body2">{t('phase.journalReference')}: {detail.reference}</Typography>
            ) : null}
            <Typography variant="body2">
              {t('phase.journalSource')}:{' '}
              {detail.sourcePath ? (
                <RouterLink to={detail.sourcePath}>{detail.sourceLabel}</RouterLink>
              ) : detail.sourceType && detail.sourceType !== 'MANUAL_JOURNAL' ? (
                detail.sourceLabel
              ) : (
                t('phase.journalManualEntry')
              )}
            </Typography>
            {detail.postedAt ? (
              <Typography variant="body2">
                {t('phase.journalPostedBy', { name: detail.postedByName || '—', at: detail.postedAt.slice(0, 16).replace('T', ' ') })}
              </Typography>
            ) : null}
            {detail.reversedEntry ? <Typography variant="body2">{t('phase.journalReversedBy', { id: String(detail.reversedEntry) })}</Typography> : null}
            {detail.reversalOf ? <Typography variant="body2">{t('phase.journalReversalOf', { id: String(detail.reversalOf) })}</Typography> : null}
            <Divider />
            <Box sx={{ overflowX: 'auto' }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>{t('phase.journalAccount')}</TableCell>
                    <TableCell align="right">{t('phase.journalDebit')}</TableCell>
                    <TableCell align="right">{t('phase.journalCredit')}</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(detail.lines ?? []).map((l, i) => (
                    <TableRow key={l.id ?? i}>
                      <TableCell>
                        {l.accountCode} {l.accountName}
                        {l.customerName || l.supplierName ? (
                          <Typography variant="caption" display="block">{l.customerName || l.supplierName}</Typography>
                        ) : null}
                        {l.costCenterName ? <Typography variant="caption" display="block">{l.costCenterName}</Typography> : null}
                        {l.narration ? <Typography variant="caption" display="block">{l.narration}</Typography> : null}
                      </TableCell>
                      <TableCell align="right">{Number(l.debit) > 0 ? formatMoney(Number(l.debit)) : ''}</TableCell>
                      <TableCell align="right">{Number(l.credit) > 0 ? formatMoney(Number(l.credit)) : ''}</TableCell>
                    </TableRow>
                  ))}
                  <TableRow>
                    <TableCell><strong>{t('phase.journalTotal')}</strong></TableCell>
                    <TableCell align="right"><strong>{formatMoney((detail.lines ?? []).reduce((s, l) => s + Number(l.debit || 0), 0))}</strong></TableCell>
                    <TableCell align="right"><strong>{formatMoney((detail.lines ?? []).reduce((s, l) => s + Number(l.credit || 0), 0))}</strong></TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </Box>
            <Button onClick={() => setDetail(null)}>{t('common.close')}</Button>
          </Stack>
        ) : null}
      </Drawer>
    </PageShell>
  );
}
