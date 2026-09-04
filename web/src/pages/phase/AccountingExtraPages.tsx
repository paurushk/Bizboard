import { useMemo, useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import * as api from '@/api/resources';
import { ErrorState, LoadingState } from '@/components/PageState';
import { formatMoney, toNumber } from '@/utils/money';
import { t } from '@/i18n';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import {
  asRows,
  DataTable,
  PageShell,
  type Row,
} from '@/pages/phase/phaseShared';


export function AccountingSettingsPage() {
  const { writesBlocked } = useSubscriptionGate();
  const qc = useQueryClient();
  const [msg, setMsg] = useState('');
  const [fyEnd, setFyEnd] = useState('2026-03-31');
  const [confirmOpen, setConfirmOpen] = useState(false);
  const m = useMutation({
    mutationFn: (enabled: boolean) => api.updateAccountingSettings({ accountingEnabled: enabled }),
    onSuccess: (data) => {
      const enabled = Boolean((data as Row)?.accountingEnabled ?? (data as Row)?.accounting_enabled);
      setMsg(enabled ? 'Accounting enabled — CoA seeded.' : 'Accounting disabled.');
      void qc.invalidateQueries();
    },
    onError: (e) => setMsg(getErrorMessage(e)),
  });
  const fyClose = useMutation({
    mutationFn: () => api.closeFinancialYear({ fyEnd, confirm: true }),
    onSuccess: () => {
      setMsg(`Financial year closed through ${fyEnd}. Income/expense moved to Retained Earnings; overlapping periods locked.`);
      setConfirmOpen(false);
      void qc.invalidateQueries({ queryKey: ['accounting-periods'] });
    },
    onError: (e) => setMsg(getErrorMessage(e)),
  });
  return (
    <PageShell title={t('phase.accounting')} subtitle={t('phase.accountingSubtitle')}>
      {msg ? <Alert severity="info">{msg}</Alert> : null}
      <Paper variant="outlined" sx={{ p: 3 }}>
        <Stack spacing={2}>
          <Alert severity="info">
            Enable accounting in Settings before using journals, trial balance, or P&amp;L.
          </Alert>
          <Alert severity="warning">
            Enable only when pilots need journals / TB / P&amp;L. GL is a projection of documents — not a second place to edit sales.
          </Alert>
          <Stack direction="row" spacing={1}>
            <Button variant="contained" disabled={writesBlocked || m.isPending} onClick={() => m.mutate(true)}>
              Enable accounting
            </Button>
            <Button variant="outlined" disabled={writesBlocked || m.isPending} onClick={() => m.mutate(false)}>
              Disable
            </Button>
          </Stack>
        </Stack>
      </Paper>
      <Paper variant="outlined" sx={{ p: 3, mt: 2 }}>
        <Stack spacing={2}>
          <Typography variant="h6">Close financial year</Typography>
          <Typography variant="body2" color="text.secondary">
            Zeros income and expense accounts into 3100 Retained Earnings (not 3200 Opening Equity), then locks overlapping periods. Owner only. Refuses unhealthy books or draft invoices in the FY.
          </Typography>
          <TextField
            type="date"
            label="FY end"
            size="small"
            InputLabelProps={{ shrink: true }}
            value={fyEnd}
            onChange={(e) => setFyEnd(e.target.value)}
            sx={{ maxWidth: 220 }}
          />
          <Button color="error" variant="contained" disabled={writesBlocked || !fyEnd || fyClose.isPending} onClick={() => setConfirmOpen(true)}>
            Close financial year…
          </Button>
        </Stack>
      </Paper>
      <Dialog open={confirmOpen} onClose={() => setConfirmOpen(false)}>
        <DialogTitle>Confirm FY close</DialogTitle>
        <DialogContent>
          Close books through {fyEnd}? This posts closing journals and sets overlapping accounting periods to CLOSED. This cannot be undone from the UI.
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmOpen(false)}>Cancel</Button>
          <Button color="error" variant="contained" disabled={writesBlocked || fyClose.isPending} onClick={() => fyClose.mutate()}>
            Confirm close
          </Button>
        </DialogActions>
      </Dialog>
    </PageShell>
  );
}

export function AccountingBankReconPage() {
  const { writesBlocked } = useSubscriptionGate();
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ['accounting-bank-recon'], queryFn: api.listAccountingBankReconSessions });
  const accounts = useQuery({ queryKey: ['accounts'], queryFn: api.listAccounts });
  const statements = useQuery({
    queryKey: ['bank-statements'],
    queryFn: async () => (await api.listBankStatementsPage()).results,
  });
  const journals = useQuery({
    queryKey: ['journals'],
    queryFn: async () => {
      const page = await api.listJournalsPage({ pageSize: 100 });
      // F3-019: keep the total so the picker can say it's capped — a bank line
      // older than the 100 most recent vouchers otherwise silently can't match.
      return { results: page.results, count: page.count ?? page.results.length };
    },
  });
  const [account, setAccount] = useState('');
  const [statement, setStatement] = useState('');
  const [session, setSession] = useState('');
  const [journalLine, setJournalLine] = useState('');
  const [bankLine, setBankLine] = useState('');
  const [error, setError] = useState('');
  const statementDetail = useQuery({
    queryKey: ['bank-statement', statement],
    queryFn: () => api.getBankStatement(Number(statement)),
    enabled: Boolean(statement),
  });
  const cashBankAccounts = useMemo(() => {
    const all = accounts.data ?? [];
    const preferred = all.filter((a) => {
      const hay = `${a.code} ${a.name}`;
      return Boolean(a.bankAccount) || /^(11|12)/.test(a.code) || /cash|bank/i.test(hay);
    });
    return preferred.length ? preferred : all.filter((a) => a.type === 'ASSET');
  }, [accounts.data]);
  const unmatchedGl = useMemo(() => {
    if (!account) return [];
    return (journals.data?.results ?? []).flatMap((entry) => {
      if (entry.status !== 'POSTED') return [];
      return (entry.lines ?? []).filter((line) => {
        const lineAccount = String(line.account);
        return lineAccount === account && !line.bankStatementLine && !line.reconciledAt;
      }).map((line) => ({
        ...line,
        label: `${entry.number || entry.id} · ${entry.entryDate} · Dr ${formatMoney(toNumber(line.debit))} / Cr ${formatMoney(toNumber(line.credit))}`,
      }));
    });
  }, [journals.data, account]);
  const journalsCapped =
    (journals.data?.count ?? 0) > (journals.data?.results?.length ?? 0);
  const unmatchedBank = useMemo(() => {
    const lines = (statementDetail.data?.lines as Row[] | undefined) ?? [];
    return lines.filter((line) => String(line.matchStatus ?? line.match_status ?? 'UNMATCHED') !== 'MATCHED');
  }, [statementDetail.data]);
  const create = useMutation({
    mutationFn: () => api.createAccountingBankReconSession({ account: Number(account), statement: Number(statement) }),
    onSuccess: () => {
      setError('');
      void qc.invalidateQueries({ queryKey: ['accounting-bank-recon'] });
    },
    onError: (e) => setError(getErrorMessage(e)),
  });
  const match = useMutation({
    mutationFn: () => api.matchAccountingBankRecon(Number(session), { journalLine: Number(journalLine), bankStatementLine: Number(bankLine) }),
    onSuccess: () => {
      setJournalLine('');
      setBankLine('');
      setError('');
      void qc.invalidateQueries({ queryKey: ['accounting-bank-recon'] });
      void qc.invalidateQueries({ queryKey: ['journals'] });
      void qc.invalidateQueries({ queryKey: ['bank-statement', statement] });
    },
    onError: (e) => setError(getErrorMessage(e)),
  });
  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  const statementRows = statements.data ?? [];
  return (
    <PageShell title={t('phase.glRecon')} subtitle={t('phase.glReconSubtitle')}>
      {!statementRows.length ? (
        <Alert severity="info" action={
          <Button color="inherit" size="small" component={RouterLink} to="/payments/statements">
            Open bank statements
          </Button>
        }>
          No bank statements yet. Upload and commit a statement first, then pick it here.
        </Alert>
      ) : null}
      {error ? <HelpErrorAlert message={error} /> : null}
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={1}>
          <TextField
            select
            label="GL account"
            size="small"
            value={account}
            onChange={(e) => { setAccount(e.target.value); setJournalLine(''); }}
            sx={{ minWidth: 240, flex: 1 }}
          >
            <MenuItem value="">Select account</MenuItem>
            {cashBankAccounts.map((a) => (
              <MenuItem key={a.id} value={String(a.id)}>
                {a.code} — {a.name}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            select
            label="Bank statement"
            size="small"
            value={statement}
            onChange={(e) => { setStatement(e.target.value); setBankLine(''); }}
            sx={{ minWidth: 240, flex: 1 }}
            disabled={!statementRows.length}
          >
            <MenuItem value="">Select statement</MenuItem>
            {statementRows.map((row) => (
              <MenuItem key={String(row.id)} value={String(row.id)}>
                {String(row.sourceFilename || row.source_filename || `Statement #${row.id}`)}
                {row.periodStart || row.period_start ? ` · ${String(row.periodStart || row.period_start)}` : ''}
              </MenuItem>
            ))}
          </TextField>
          <Button variant="contained" disabled={writesBlocked || !account || !statement || create.isPending} onClick={() => create.mutate()}>
            Create session
          </Button>
        </Stack>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} sx={{ mt: 2 }}>
          <TextField
            select
            label="Session"
            size="small"
            value={session}
            onChange={(e) => setSession(e.target.value)}
            sx={{ minWidth: 160 }}
          >
            <MenuItem value="">Select session</MenuItem>
            {asRows(query.data).map((row) => (
              <MenuItem key={String(row.id)} value={String(row.id)}>
                #{String(row.id)} · {String(row.status || 'OPEN')}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            select
            label="Journal line"
            size="small"
            value={journalLine}
            onChange={(e) => setJournalLine(e.target.value)}
            sx={{ minWidth: 240, flex: 1 }}
            disabled={!account}
            helperText={
              journalsCapped
                ? `only the ${journals.data?.results?.length} most recent vouchers are searchable here`
                : undefined
            }
          >
            <MenuItem value="">{account ? 'Select journal line' : 'Pick a GL account first'}</MenuItem>
            {unmatchedGl.map((line) => (
              <MenuItem key={String(line.id)} value={String(line.id)}>
                {line.label}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            select
            label="Statement line"
            size="small"
            value={bankLine}
            onChange={(e) => setBankLine(e.target.value)}
            sx={{ minWidth: 240, flex: 1 }}
            disabled={!statement}
          >
            <MenuItem value="">{statement ? 'Select statement line' : 'Pick a statement first'}</MenuItem>
            {unmatchedBank.map((line) => (
              <MenuItem key={String(line.id)} value={String(line.id)}>
                {String(line.txnDate || line.txn_date || '')} · {formatMoney(toNumber((line.amount as string | number) ?? 0))}
                {line.narration ? ` · ${String(line.narration).slice(0, 40)}` : ''}
              </MenuItem>
            ))}
          </TextField>
          <Button
            variant="outlined"
            disabled={writesBlocked || !session || !journalLine || !bankLine || match.isPending}
            onClick={() => {
              // F2-014: block a mismatched GL↔bank match unless explicitly ack'd.
              const gl = unmatchedGl.find((l) => String(l.id) === journalLine);
              const bank = unmatchedBank.find((l) => String(l.id) === bankLine);
              const glAmt = gl ? Math.abs(toNumber(gl.debit) - toNumber(gl.credit)) : 0;
              const bankAmt = bank ? Math.abs(toNumber((bank.amount as string | number) ?? 0)) : 0;
              if (
                gl && bank && Math.abs(glAmt - bankAmt) > 0.01 &&
                !window.confirm(
                  `GL line is ${formatMoney(glAmt)} but the bank line is ${formatMoney(bankAmt)}. Match them anyway?`,
                )
              ) {
                return;
              }
              match.mutate();
            }}
          >
            Match lines
          </Button>
        </Stack>
      </Paper>
      <DataTable
        rows={asRows(query.data)}
        empty="No recon sessions yet."
        columns={[
          { key: 'account', label: 'GL account' },
          { key: 'statement', label: 'Statement' },
          { key: 'status', label: 'Status', status: true },
          { key: 'glBalance', label: 'GL balance', money: true },
          { key: 'statementBalance', label: 'Statement', money: true },
        ]}
      />
    </PageShell>
  );
}

export function CostCentersPage() {
  const { writesBlocked } = useSubscriptionGate();
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ['cost-centers'], queryFn: api.listCostCenters });
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [code, setCode] = useState('');
  const create = useMutation({
    mutationFn: () => api.createCostCenter({ name, code: code || name.slice(0, 8).toUpperCase() }),
    onSuccess: () => {
      setOpen(false);
      void qc.invalidateQueries({ queryKey: ['cost-centers'] });
    },
  });
  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  return (
    <PageShell
      title={t('phase.costCenters')}
      subtitle={t('phase.costCentersSubtitle')}
      actions={
        <Button variant="contained" onClick={() => setOpen(true)} disabled={writesBlocked}>
          Add
        </Button>
      }
    >
      <DataTable
        rows={asRows(query.data)}
        empty="No cost centers."
        columns={[
          { key: 'code', label: 'Code' },
          { key: 'name', label: 'Name' },
          { key: 'isActive', label: 'Active', bool: true },
        ]}
      />
      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>Cost center</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} />
            <TextField label="Code" value={code} onChange={(e) => setCode(e.target.value)} />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button variant="contained" disabled={writesBlocked || !name || create.isPending} onClick={() => create.mutate()}>
            Save
          </Button>
        </DialogActions>
      </Dialog>
    </PageShell>
  );
}
