import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import * as api from '@/api/resources';
import { ErrorState, LoadingState } from '@/components/PageState';
import {
  asRows,
  DataTable,
  PageShell,
  type Row,
} from '@/pages/phase/phaseShared';


export function AccountingSettingsPage() {
  const qc = useQueryClient();
  const [msg, setMsg] = useState('');
  const [fyEnd, setFyEnd] = useState('2026-03-31');
  const [confirmOpen, setConfirmOpen] = useState(false);
  const m = useMutation({
    mutationFn: (enabled: boolean) => api.updateAccountingSettings({ accounting_enabled: enabled }),
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
    <PageShell title="Accounting" subtitle="Opt-in light books. Documents remain the source of truth.">
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
            <Button variant="contained" disabled={m.isPending} onClick={() => m.mutate(true)}>
              Enable accounting
            </Button>
            <Button variant="outlined" disabled={m.isPending} onClick={() => m.mutate(false)}>
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
          <Button color="error" variant="contained" disabled={!fyEnd || fyClose.isPending} onClick={() => setConfirmOpen(true)}>
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
          <Button color="error" variant="contained" disabled={fyClose.isPending} onClick={() => fyClose.mutate()}>
            Confirm close
          </Button>
        </DialogActions>
      </Dialog>
    </PageShell>
  );
}

export function AccountingBankReconPage() {
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ['accounting-bank-recon'], queryFn: api.listAccountingBankReconSessions });
  const [account, setAccount] = useState('');
  const [statement, setStatement] = useState('');
  const [session, setSession] = useState('');
  const [journalLine, setJournalLine] = useState('');
  const [bankLine, setBankLine] = useState('');
  const create = useMutation({
    mutationFn: () => api.createAccountingBankReconSession({ account: Number(account), statement: Number(statement) }),
    onSuccess: () => { setAccount(''); setStatement(''); void qc.invalidateQueries({ queryKey: ['accounting-bank-recon'] }); },
  });
  const match = useMutation({
    mutationFn: () => api.matchAccountingBankRecon(Number(session), { journalLine: Number(journalLine), bankStatementLine: Number(bankLine) }),
    onSuccess: () => { setJournalLine(''); setBankLine(''); void qc.invalidateQueries({ queryKey: ['accounting-bank-recon'] }); },
  });
  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState message={getErrorMessage(query.error)} onRetry={() => void query.refetch()} />;
  return (
    <PageShell title="GL bank reconciliation" subtitle="Clears GL bank lines against Phase 3 statement lines.">
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={1}>
          <TextField label="GL account ID" size="small" value={account} onChange={(e) => setAccount(e.target.value)} />
          <TextField label="Statement ID" size="small" value={statement} onChange={(e) => setStatement(e.target.value)} />
          <Button variant="contained" disabled={!account || !statement || create.isPending} onClick={() => create.mutate()}>Create session</Button>
        </Stack>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} sx={{ mt: 2 }}>
          <TextField label="Session ID" size="small" value={session} onChange={(e) => setSession(e.target.value)} />
          <TextField label="Journal line ID" size="small" value={journalLine} onChange={(e) => setJournalLine(e.target.value)} />
          <TextField label="Bank statement line ID" size="small" value={bankLine} onChange={(e) => setBankLine(e.target.value)} />
          <Button variant="outlined" disabled={!session || !journalLine || !bankLine || match.isPending} onClick={() => match.mutate()}>Match lines</Button>
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
  if (query.isError) return <ErrorState message={getErrorMessage(query.error)} onRetry={() => void query.refetch()} />;
  return (
    <PageShell
      title="Cost centers"
      subtitle="Optional dimension for P&L slicing."
      actions={
        <Button variant="contained" onClick={() => setOpen(true)}>
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
          <Button variant="contained" disabled={!name || create.isPending} onClick={() => create.mutate()}>
            Save
          </Button>
        </DialogActions>
      </Dialog>
    </PageShell>
  );
}
