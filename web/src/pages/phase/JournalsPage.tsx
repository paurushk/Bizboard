import { useMemo, useState } from 'react';
import Alert from '@mui/material/Alert';
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
import { todayIso } from '@/components/billing';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { ErrorState, LoadingState } from '@/components/PageState';
import { formatMoney } from '@/utils/money';
import { t } from '@/i18n';
import { asRows, DataTable, PageShell } from '@/pages/phase/phaseShared';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';

export function JournalsPage() {
  const { writesBlocked } = useSubscriptionGate();
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: ['journals'],
    queryFn: () => api.listJournals(),
  });
  const accounts = useQuery({ queryKey: ['accounts'], queryFn: api.listAccounts });
  const [open, setOpen] = useState(false);
  const [narration, setNarration] = useState('');
  const [lines, setLines] = useState([
    { account: '', debit: '', credit: '' },
    { account: '', debit: '', credit: '' },
  ]);
  const [error, setError] = useState('');
  const [confirm, setConfirm] = useState<{ mode: 'post' | 'reverse'; id: number } | null>(null);
  const totals = useMemo(() => {
    const debit = lines.reduce((s, l) => s + (Number(l.debit) || 0), 0);
    const credit = lines.reduce((s, l) => s + (Number(l.credit) || 0), 0);
    return { debit, credit, balanced: Math.abs(debit - credit) < 0.005 && debit > 0 };
  }, [lines]);
  const create = useMutation({
    mutationFn: () =>
      api.createJournal({
        narration,
        entryDate: todayIso(),
        lines: lines
          .filter((l) => l.account)
          .map((l) => ({
            account: Number(l.account),
            debit: Number(l.debit) || 0,
            credit: Number(l.credit) || 0,
          })),
      }),
    onSuccess: () => {
      setOpen(false);
      void qc.invalidateQueries({ queryKey: ['journals'] });
    },
    onError: (e) => setError(getErrorMessage(e)),
  });
  const post = useMutation({
    mutationFn: (id: number) => api.postJournal(id),
    onSuccess: () => {
      setError('');
      void qc.invalidateQueries({ queryKey: ['journals'] });
    },
    onError: (e) => setError(getErrorMessage(e)),
  });
  const reverse = useMutation({
    mutationFn: (id: number) => api.reverseJournal(id),
    onSuccess: () => {
      setError('');
      void qc.invalidateQueries({ queryKey: ['journals'] });
    },
    onError: (e) => setError(getErrorMessage(e)),
  });
  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  return (
    <PageShell
      title={t('phase.journals')}
      subtitle={t('phase.journalsSubtitle')}
      actions={
        <Button variant="contained" onClick={() => setOpen(true)} disabled={writesBlocked}>
          New voucher
        </Button>
      }
    >
      {error && !open ? <HelpErrorAlert message={error} /> : null}
      <DataTable
        rows={asRows(query.data)}
        empty="No journals yet."
        columns={[
          { key: 'number', label: 'Number' },
          { key: 'entryDate', label: 'Date' },
          { key: 'status', label: 'Status', status: true },
          { key: 'narration', label: 'Narration' },
        ]}
        actions={(r) =>
          r.status === 'DRAFT' ? (
            <Button size="small" variant="contained" disabled={writesBlocked} onClick={() => setConfirm({ mode: 'post', id: Number(r.id) })}>
              Post
            </Button>
          ) : r.status === 'POSTED' ? (
            <Button size="small" color="warning" disabled={writesBlocked} onClick={() => setConfirm({ mode: 'reverse', id: Number(r.id) })}>
              Reverse
            </Button>
          ) : null
        }
      />
      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="md">
        <DialogTitle>Journal voucher</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField label="Narration" value={narration} onChange={(e) => setNarration(e.target.value)} fullWidth />
            {lines.map((line, idx) => (
              <Stack key={idx} direction={{ xs: 'column', sm: 'row' }} spacing={1}>
                <TextField
                  select
                  label="Account"
                  value={line.account}
                  onChange={(e) => {
                    const next = [...lines];
                    next[idx] = { ...next[idx], account: e.target.value };
                    setLines(next);
                  }}
                  sx={{ flex: 2 }}
                >
                  {(accounts.data ?? []).map((a) => (
                    <MenuItem key={a.id} value={String(a.id)}>
                      {a.code} — {a.name}
                    </MenuItem>
                  ))}
                </TextField>
                <TextField
                  label="Debit"
                  type="number"
                  inputProps={{ min: 0, step: 0.01 }}
                  value={line.debit}
                  onChange={(e) => {
                    const raw = e.target.value;
                    const v = raw === '' || Number(raw) >= 0 ? raw : '0';
                    const next = [...lines];
                    next[idx] = { ...next[idx], debit: v, credit: '' };
                    setLines(next);
                  }}
                />
                <TextField
                  label="Credit"
                  type="number"
                  inputProps={{ min: 0, step: 0.01 }}
                  value={line.credit}
                  onChange={(e) => {
                    const raw = e.target.value;
                    const v = raw === '' || Number(raw) >= 0 ? raw : '0';
                    const next = [...lines];
                    next[idx] = { ...next[idx], credit: v, debit: '' };
                    setLines(next);
                  }}
                />
              </Stack>
            ))}
            <Button size="small" onClick={() => setLines([...lines, { account: '', debit: '', credit: '' }])} disabled={writesBlocked}>
              Add line
            </Button>
            <Alert severity={totals.balanced ? 'success' : 'warning'}>
              Debit {formatMoney(totals.debit)} · Credit {formatMoney(totals.credit)}
              {totals.balanced ? ' · Balanced' : ' · Not balanced'}
            </Alert>
            {error ? <HelpErrorAlert message={error} /> : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button variant="contained" disabled={writesBlocked || !totals.balanced || create.isPending} onClick={() => create.mutate()}>
            Save draft
          </Button>
        </DialogActions>
      </Dialog>
      <ConfirmDialog
        open={confirm !== null}
        title={confirm?.mode === 'reverse' ? 'Reverse this posted journal?' : 'Post this journal?'}
        body={
          confirm?.mode === 'reverse'
            ? 'This writes a counter-entry to the general ledger. It cannot be undone.'
            : 'This posts the voucher to the general ledger.'
        }
        confirmLabel={confirm?.mode === 'reverse' ? 'Reverse' : 'Post'}
        confirmColor={confirm?.mode === 'reverse' ? 'error' : 'primary'}
        confirming={confirm?.mode === 'reverse' ? reverse.isPending : post.isPending}
        onClose={() => setConfirm(null)}
        onConfirm={() => {
          if (!confirm) return;
          if (confirm.mode === 'reverse') reverse.mutate(confirm.id);
          else post.mutate(confirm.id);
          setConfirm(null);
        }}
      />
    </PageShell>
  );
}
