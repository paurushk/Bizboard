import { useMemo, useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
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
import type { ReconSession } from '@/api/resources';
import { AccountSelect } from '@/components/accounting/AccountSelect';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { ErrorState, LoadingState } from '@/components/PageState';
import { useAuth } from '@/auth/AuthContext';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { PageShell, StatusChip, stackedTableSx } from '@/pages/phase/phaseShared';
import { t } from '@/i18n';
import { canPostJournals, isOwner } from '@/utils/permissions';
import { formatMoney, toNumber } from '@/utils/money';

function saveBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

const money = (v: string | null | undefined) => (v === null || v === undefined ? '—' : formatMoney(toNumber(v)));

export function AccountingBankReconPage() {
  const { user } = useAuth();
  const { writesBlocked: subscriptionBlocked } = useSubscriptionGate();
  const writesBlocked = subscriptionBlocked || !canPostJournals(user);
  const owner = !!user && isOwner(user.role);
  const qc = useQueryClient();
  const [openId, setOpenId] = useState<number | null>(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [error, setError] = useState('');

  const sessions = useQuery({
    queryKey: ['recon-sessions', statusFilter],
    queryFn: () => api.listBankReconSessions(statusFilter ? { status: statusFilter } : undefined),
  });
  const accounts = useQuery({ queryKey: ['accounts'], queryFn: api.listAccounts });
  const statements = useQuery({
    queryKey: ['bank-statements'],
    queryFn: async () => (await api.listBankStatementsPage()).results,
  });
  const [account, setAccount] = useState('');
  const [statement, setStatement] = useState('');
  const [closing, setClosing] = useState('');
  const bankLedgers = useMemo(() => {
    const all = accounts.data ?? [];
    const banks = all.filter((a) => Boolean(a.bankAccount) || /^(11|15)/.test(a.code));
    return banks.length ? banks : all.filter((a) => a.type === 'ASSET');
  }, [accounts.data]);
  const create = useMutation({
    mutationFn: () =>
      api.createAccountingBankReconSession({
        account: Number(account),
        statement: Number(statement),
        ...(closing !== '' ? { statementClosingBalance: closing } : {}),
      }),
    onSuccess: (data) => {
      setError('');
      setClosing('');
      void qc.invalidateQueries({ queryKey: ['recon-sessions'] });
      const id = Number((data as { id?: number })?.id);
      if (id) setOpenId(id);
    },
    onError: (e) => setError(getErrorMessage(e)),
  });

  if (openId !== null) {
    return <ReconWorkspace id={openId} onBack={() => { setOpenId(null); void qc.invalidateQueries({ queryKey: ['recon-sessions'] }); }} writesBlocked={writesBlocked} owner={owner} />;
  }
  if (sessions.isLoading) return <LoadingState />;
  if (sessions.isError) return <ErrorState message={getErrorMessage(sessions.error)} error={sessions.error} onRetry={() => void sessions.refetch()} />;
  const rows = sessions.data?.results ?? [];
  const statementRows = statements.data ?? [];

  return (
    <PageShell title={t('phase.glRecon')} subtitle={t('phase.glReconSubtitle')}>
      <Alert
        severity="info"
        action={
          <Button color="inherit" size="small" component={RouterLink} to="/payments/reconciliation">
            {t('phase.openPaymentsRecon')}
          </Button>
        }
      >
        {t('phase.glReconDistinct')}
      </Alert>
      {error ? <HelpErrorAlert message={error} /> : null}
      {!statementRows.length ? (
        <Alert
          severity="info"
          action={
            <Button color="inherit" size="small" component={RouterLink} to="/payments/statements">
              {t('sweep2.openBankStatements')}
            </Button>
          }
        >
          {t('phase.reconNoStatements')}
        </Alert>
      ) : (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>{t('phase.reconNew')}</Typography>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={1}>
            <AccountSelect
              accounts={bankLedgers}
              label={t('sweep.glAccount')}
              value={account}
              onChange={setAccount}
              size="small"
              sx={{ minWidth: 240, flex: 1 }}
            />
            <TextField select size="small" label={t('sweep.bankStatement')} value={statement} onChange={(e) => setStatement(e.target.value)} sx={{ minWidth: 240, flex: 1 }}>
              {statementRows.map((row) => (
                <MenuItem key={String(row.id)} value={String(row.id)}>
                  {String(row.sourceFilename || `#${row.id}`)}
                  {row.periodStart ? ` · ${String(row.periodStart)}` : ''}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              size="small"
              type="number"
              label={t('phase.reconClosingBalance')}
              helperText={t('phase.reconClosingHint')}
              value={closing}
              onChange={(e) => setClosing(e.target.value)}
              inputProps={{ step: 0.01 }}
            />
            <Button variant="contained" disabled={writesBlocked || !account || !statement || create.isPending} onClick={() => create.mutate()}>
              {t('sweep2.createSession')}
            </Button>
          </Stack>
        </Paper>
      )}
      <Stack direction="row" spacing={1} alignItems="center">
        <Typography variant="subtitle2" sx={{ flex: 1 }}>{t('phase.reconSessions')}</Typography>
        <TextField select size="small" label={t('common.status')} value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} sx={{ minWidth: 170 }}>
          <MenuItem value="">{t('phase.journalAllStatuses')}</MenuItem>
          {['OPEN', 'IN_PROGRESS', 'RECONCILED', 'FINALISED'].map((s) => (
            <MenuItem key={s} value={s}>{t(`status.${s}`)}</MenuItem>
          ))}
        </TextField>
      </Stack>
      <Paper variant="outlined" sx={{ overflowX: 'auto' }}>
        <Table size="small" aria-label={t('phase.reconSessions')} sx={stackedTableSx}>
          <TableHead>
            <TableRow>
              <TableCell>{t('phase.reconBank')}</TableCell>
              <TableCell>{t('sweep.bankStatement')}</TableCell>
              <TableCell>{t('common.status')}</TableCell>
              <TableCell align="right">{t('phase.reconDifference')}</TableCell>
              <TableCell>{t('common.date')}</TableCell>
              <TableCell align="right" />
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.length === 0 ? (
              <TableRow><TableCell colSpan={6}>{t('phase.reconNoSessions')}</TableCell></TableRow>
            ) : null}
            {rows.map((r: ReconSession) => (
              <TableRow key={r.id} hover>
                <TableCell data-label={t('phase.reconBank')}>{r.accountName}</TableCell>
                <TableCell data-label={t('sweep.bankStatement')}>{r.statementName}</TableCell>
                <TableCell data-label={t('common.status')}><StatusChip value={r.status} /></TableCell>
                <TableCell align="right" data-label={t('phase.reconDifference')}>{money(r.difference)}</TableCell>
                <TableCell data-label={t('common.date')}>{r.statementDate ?? ''}</TableCell>
                <TableCell align="right" data-label="">
                  <Button size="small" onClick={() => setOpenId(r.id)}>{t('phase.reconOpen')}</Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Paper>
    </PageShell>
  );
}

function ReconWorkspace({ id, onBack, writesBlocked, owner }: { id: number; onBack: () => void; writesBlocked: boolean; owner: boolean }) {
  const qc = useQueryClient();
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const detail = useQuery({ queryKey: ['recon-session', id], queryFn: () => api.getBankReconSession(id) });
  const accounts = useQuery({ queryKey: ['accounts'], queryFn: api.listAccounts });

  const [showMatched, setShowMatched] = useState(false);
  const [bankQ, setBankQ] = useState('');
  const [glQ, setGlQ] = useState('');
  const [amountQ, setAmountQ] = useState('');
  const bankSearch = useDebouncedValue(bankQ.trim(), 300);
  const glSearch = useDebouncedValue(glQ.trim(), 300);
  const amountSearch = useDebouncedValue(amountQ.trim(), 300);
  const [bankPage, setBankPage] = useState(0);
  const [glPage, setGlPage] = useState(0);
  const bankLines = useQuery({
    queryKey: ['recon-bank-lines', id, showMatched, bankSearch, amountSearch, bankPage],
    queryFn: () =>
      api.listReconStatementLines(id, { status: showMatched ? 'matched' : 'open', q: bankSearch, amount: amountSearch, page: bankPage + 1, pageSize: 25 }),
  });
  const glLines = useQuery({
    queryKey: ['recon-gl-lines', id, glSearch, amountSearch, glPage],
    queryFn: () => api.listReconLedgerLines(id, { q: glSearch, amount: amountSearch, page: glPage + 1, pageSize: 25 }),
  });
  const [pickedBank, setPickedBank] = useState<number[]>([]);
  const [pickedGl, setPickedGl] = useState<number[]>([]);
  const toggle = (list: number[], set: (v: number[]) => void, v: number) =>
    set(list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['recon-session', id] });
    void qc.invalidateQueries({ queryKey: ['recon-bank-lines', id] });
    void qc.invalidateQueries({ queryKey: ['recon-gl-lines', id] });
    void qc.invalidateQueries({ queryKey: ['recon-suggestions', id] });
  };
  const onError = (e: unknown) => setError(getErrorMessage(e));

  const bankSelected = (bankLines.data?.results ?? []).filter((l) => pickedBank.includes(l.id));
  const glSelected = (glLines.data?.results ?? []).filter((l) => pickedGl.includes(l.id));
  const bankTotal = bankSelected.reduce((s, l) => s + toNumber(l.amount), 0);
  const glTotal = glSelected.reduce((s, l) => s + toNumber(l.signedAmount), 0);
  const selectionDiff = Math.round((glTotal - bankTotal) * 100) / 100;
  const shapeOk = (pickedBank.length >= 1 && pickedGl.length >= 1) && !(pickedBank.length > 1 && pickedGl.length > 1);
  const canMatch = shapeOk && selectionDiff === 0;

  const match = useMutation({
    mutationFn: () => api.matchManyRecon(id, { journalLines: pickedGl, bankLines: pickedBank }),
    onSuccess: () => {
      setPickedBank([]);
      setPickedGl([]);
      setError('');
      refresh();
    },
    onError,
  });
  const unmatch = useMutation({
    mutationFn: (bankLine: number) => api.unmatchGlRecon(id, bankLine),
    onSuccess: () => { setError(''); refresh(); },
    onError,
  });

  const [suggestOpen, setSuggestOpen] = useState(false);
  const suggestions = useQuery({
    queryKey: ['recon-suggestions', id],
    queryFn: () => api.getReconSuggestions(id),
    enabled: suggestOpen,
  });
  const accept = useMutation({
    mutationFn: (pairs: Array<{ bankLine: number; journalLine: number }>) => api.acceptReconSuggestions(id, { pairs }),
    onSuccess: (data) => {
      setError('');
      setInfo(t('phase.reconAccepted', { count: String(data.matched ?? 0) }));
      refresh();
    },
    onError,
  });

  const [entryFor, setEntryFor] = useState<number | null>(null);
  const [entryAccount, setEntryAccount] = useState('');
  const [entryNote, setEntryNote] = useState('');
  const createEntry = useMutation({
    mutationFn: () => api.createReconEntry(id, { bankLine: entryFor as number, account: Number(entryAccount), narration: entryNote }),
    onSuccess: () => {
      setEntryFor(null);
      setEntryAccount('');
      setEntryNote('');
      setError('');
      refresh();
    },
    onError,
  });

  const [closingEdit, setClosingEdit] = useState('');
  const saveClosing = useMutation({
    mutationFn: () => api.patchBankReconSession(id, { statementClosingBalance: closingEdit }),
    onSuccess: () => { setClosingEdit(''); setError(''); refresh(); },
    onError,
  });
  const [finaliseOpen, setFinaliseOpen] = useState(false);
  const [reopenOpen, setReopenOpen] = useState(false);
  const finalise = useMutation({
    mutationFn: (writeOff: boolean) => api.finaliseRecon(id, writeOff),
    onSuccess: () => { setFinaliseOpen(false); setError(''); setInfo(t('phase.reconFinalised')); refresh(); },
    onError: (e) => { setFinaliseOpen(false); onError(e); },
  });
  const reopen = useMutation({
    mutationFn: (reason: string) => api.reopenRecon(id, reason),
    onSuccess: () => { setReopenOpen(false); setError(''); setInfo(t('phase.reconReopened')); refresh(); },
    onError,
  });
  const download = async (file: 'xlsx' | 'pdf') => {
    try {
      saveBlob(await api.reconReportFile(id, file), `bank-reconciliation-${id}.${file}`);
    } catch (e) {
      onError(e);
    }
  };

  if (detail.isLoading) return <LoadingState />;
  if (detail.isError) return <ErrorState message={getErrorMessage(detail.error)} error={detail.error} onRetry={() => void detail.refetch()} />;
  const session = detail.data as ReconSession;
  const s = session.summary;
  const finalised = session.status === 'FINALISED';
  const locked = writesBlocked || finalised;
  const diff = s?.difference === null || s?.difference === undefined ? null : toNumber(s.difference);
  const smallDiff = diff !== null && diff !== 0 && Math.abs(diff) <= 10;

  return (
    <PageShell
      title={`${session.accountName} · ${session.statementName}`}
      subtitle={t('phase.reconWorkspaceSubtitle')}
      actions={
        <Stack direction="row" spacing={1}>
          <Button onClick={onBack}>{t('phase.reconBackToList')}</Button>
          <Button onClick={() => void download('xlsx')}>{t('phase.journalExportXlsx')}</Button>
          <Button onClick={() => void download('pdf')}>{t('phase.reconPdf')}</Button>
        </Stack>
      }
    >
      {error ? <HelpErrorAlert message={error} /> : null}
      {info ? <Alert severity="success" onClose={() => setInfo('')}>{info}</Alert> : null}
      <Paper variant="outlined" sx={{ p: 2 }} data-testid="recon-summary">
        <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
          <StatusChip value={session.status} />
          {finalised ? (
            <Typography variant="caption">{t('phase.reconFinalisedBy', { name: session.finalisedByName || '—' })}</Typography>
          ) : null}
        </Stack>
        {s && s.statementClosingBalance === null && !finalised ? (
          <Alert severity="warning" sx={{ mb: 1 }}>
            <Stack direction="row" spacing={1} alignItems="center">
              <span>{t('phase.reconNeedClosing')}</span>
              <TextField size="small" type="number" value={closingEdit} onChange={(e) => setClosingEdit(e.target.value)} label={t('phase.reconClosingBalance')} />
              <Button size="small" variant="contained" disabled={!closingEdit || saveClosing.isPending} onClick={() => saveClosing.mutate()}>{t('common.save')}</Button>
            </Stack>
          </Alert>
        ) : null}
        {s ? (
          <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr 1fr', md: 'repeat(4, 1fr)' }, gap: 1 }}>
            <Figure label={t('phase.reconBankBalance')} value={money(s.statementClosingBalance)} />
            <Figure label={t('phase.reconDepositsInTransit')} value={money(s.outstandingDeposits)} />
            <Figure label={t('phase.reconPaymentsInTransit')} value={money(s.outstandingPayments)} />
            <Figure label={t('phase.reconAdjustedBank')} value={money(s.adjustedBankBalance)} strong />
            <Figure label={t('phase.reconBookBalance')} value={money(s.glBalanceAsAt)} />
            <Figure label={t('phase.reconNotInBooks')} value={money(s.unrecordedBankItems)} />
            <Figure label={t('phase.reconAdjustedBook')} value={money(s.adjustedBookBalance)} strong />
            <Figure label={t('phase.reconDifference')} value={money(s.difference)} strong color={diff === 0 ? 'success.main' : 'error.main'} />
          </Box>
        ) : null}
        <Stack direction="row" spacing={1} sx={{ mt: 2 }}>
          <Button variant="outlined" onClick={() => setSuggestOpen(true)} disabled={locked}>{t('phase.reconSuggestions')}</Button>
          {!finalised ? (
            <Button variant="contained" disabled={locked || diff === null} onClick={() => setFinaliseOpen(true)}>{t('phase.reconFinalise')}</Button>
          ) : owner ? (
            <Button color="warning" variant="outlined" onClick={() => setReopenOpen(true)}>{t('phase.reconReopen')}</Button>
          ) : null}
        </Stack>
      </Paper>

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} alignItems={{ md: 'center' }}>
          <TextField size="small" label={t('phase.reconSearchBank')} value={bankQ} onChange={(e) => { setBankQ(e.target.value); setBankPage(0); }} />
          <TextField size="small" label={t('phase.reconSearchLedger')} value={glQ} onChange={(e) => { setGlQ(e.target.value); setGlPage(0); }} />
          <TextField size="small" label={t('phase.reconAmount')} value={amountQ} onChange={(e) => { setAmountQ(e.target.value); setBankPage(0); setGlPage(0); }} />
          <Box sx={{ flex: 1 }} />
          <Chip
            variant={showMatched ? 'filled' : 'outlined'}
            label={showMatched ? t('phase.reconShowingMatched') : t('phase.reconShowingOpen')}
            onClick={() => { setShowMatched(!showMatched); setBankPage(0); setPickedBank([]); }}
          />
        </Stack>
        <Stack direction="row" spacing={2} alignItems="center" sx={{ mt: 1 }} data-testid="recon-selection">
          <Typography variant="body2">{t('phase.reconSelectedBank')}: {formatMoney(bankTotal)}</Typography>
          <Typography variant="body2">{t('phase.reconSelectedLedger')}: {formatMoney(glTotal)}</Typography>
          <Typography variant="body2" color={selectionDiff === 0 ? 'success.main' : 'warning.main'}>
            {t('phase.reconDifference')}: {formatMoney(selectionDiff)}
          </Typography>
          <Button variant="contained" size="small" disabled={locked || !canMatch || match.isPending} onClick={() => match.mutate()}>
            {t('sweep2.matchLines')}
          </Button>
        </Stack>
      </Paper>

      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: '1fr 1fr' }, gap: 2 }}>
        <Paper variant="outlined" sx={{ overflowX: 'auto' }}>
          <Typography variant="subtitle2" sx={{ p: 1 }}>{t('phase.reconStatementSide')}</Typography>
          <Table size="small" aria-label={t('phase.reconStatementSide')}>
            <TableHead>
              <TableRow>
                <TableCell padding="checkbox" />
                <TableCell>{t('common.date')}</TableCell>
                <TableCell>{t('phase.journalNarration')}</TableCell>
                <TableCell align="right">{t('phase.reconAmount')}</TableCell>
                <TableCell />
              </TableRow>
            </TableHead>
            <TableBody>
              {(bankLines.data?.results ?? []).map((l) => (
                <TableRow key={l.id} hover selected={pickedBank.includes(l.id)}>
                  <TableCell padding="checkbox">
                    {!showMatched ? (
                      <Checkbox size="small" disabled={locked} checked={pickedBank.includes(l.id)} onChange={() => toggle(pickedBank, setPickedBank, l.id)} inputProps={{ 'aria-label': `${t('phase.reconPick')} ${l.narration || l.id}` }} />
                    ) : null}
                  </TableCell>
                  <TableCell>{l.txnDate}</TableCell>
                  <TableCell>{l.narration}</TableCell>
                  <TableCell align="right">{formatMoney(toNumber(l.amount))}</TableCell>
                  <TableCell align="right">
                    {showMatched ? (
                      <Button size="small" color="warning" disabled={locked || unmatch.isPending} onClick={() => unmatch.mutate(l.id)}>{t('phase.reconUnmatch')}</Button>
                    ) : (
                      <Button size="small" disabled={locked} onClick={() => setEntryFor(l.id)}>{t('phase.reconCreateEntry')}</Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
              {(bankLines.data?.results ?? []).length === 0 ? (
                <TableRow><TableCell colSpan={5}>{t('phase.reconNothingHere')}</TableCell></TableRow>
              ) : null}
            </TableBody>
          </Table>
          <TablePagination component="div" count={bankLines.data?.count ?? 0} page={bankPage} rowsPerPage={25} rowsPerPageOptions={[25]} onPageChange={(_e, p) => setBankPage(p)} />
        </Paper>
        <Paper variant="outlined" sx={{ overflowX: 'auto' }}>
          <Typography variant="subtitle2" sx={{ p: 1 }}>{t('phase.reconLedgerSide')}</Typography>
          <Table size="small" aria-label={t('phase.reconLedgerSide')}>
            <TableHead>
              <TableRow>
                <TableCell padding="checkbox" />
                <TableCell>{t('common.date')}</TableCell>
                <TableCell>{t('phase.journalNarration')}</TableCell>
                <TableCell align="right">{t('phase.reconAmount')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(glLines.data?.results ?? []).map((l) => (
                <TableRow key={l.id} hover selected={pickedGl.includes(l.id)}>
                  <TableCell padding="checkbox">
                    <Checkbox size="small" disabled={locked} checked={pickedGl.includes(l.id)} onChange={() => toggle(pickedGl, setPickedGl, l.id)} inputProps={{ 'aria-label': `${t('phase.reconPick')} ${l.entryNumber}` }} />
                  </TableCell>
                  <TableCell>{l.entryDate}</TableCell>
                  <TableCell>{l.entryNumber} {l.narration}</TableCell>
                  <TableCell align="right">{formatMoney(toNumber(l.signedAmount))}</TableCell>
                </TableRow>
              ))}
              {(glLines.data?.results ?? []).length === 0 ? (
                <TableRow><TableCell colSpan={4}>{t('phase.reconNothingHere')}</TableCell></TableRow>
              ) : null}
            </TableBody>
          </Table>
          <TablePagination component="div" count={glLines.data?.count ?? 0} page={glPage} rowsPerPage={25} rowsPerPageOptions={[25]} onPageChange={(_e, p) => setGlPage(p)} />
        </Paper>
      </Box>

      <Dialog open={suggestOpen} onClose={() => setSuggestOpen(false)} fullWidth maxWidth="md">
        <DialogTitle>{t('phase.reconSuggestions')}</DialogTitle>
        <DialogContent>
          {suggestions.isLoading ? <LoadingState /> : null}
          {suggestions.data ? (
            suggestions.data.length === 0 ? (
              <Typography variant="body2">{t('phase.reconNoSuggestions')}</Typography>
            ) : (
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>{t('phase.reconAmount')}</TableCell>
                    <TableCell>{t('phase.reconConfidence')}</TableCell>
                    <TableCell>{t('phase.reconWhy')}</TableCell>
                    <TableCell />
                  </TableRow>
                </TableHead>
                <TableBody>
                  {suggestions.data.map((r) => (
                    <TableRow key={`${r.bankLine}-${r.journalLine}`}>
                      <TableCell>{formatMoney(toNumber(r.amount))}</TableCell>
                      <TableCell><Chip size="small" color={r.confidence === 'high' ? 'success' : 'default'} label={t(`phase.reconConf_${r.confidence}`)} /></TableCell>
                      <TableCell>{t('phase.reconWhyText', { gap: String(r.dateGap), words: r.sharedWords.join(', ') || '—' })}</TableCell>
                      <TableCell align="right">
                        <Button size="small" disabled={accept.isPending} onClick={() => accept.mutate([{ bankLine: r.bankLine, journalLine: r.journalLine }])}>{t('phase.reconAccept')}</Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSuggestOpen(false)}>{t('common.close')}</Button>
          <Button
            variant="contained"
            disabled={accept.isPending || !(suggestions.data ?? []).some((r) => r.confidence === 'high')}
            onClick={() =>
              accept.mutate((suggestions.data ?? []).filter((r) => r.confidence === 'high').map((r) => ({ bankLine: r.bankLine, journalLine: r.journalLine })))
            }
          >
            {t('phase.reconAcceptHigh', { count: String((suggestions.data ?? []).filter((r) => r.confidence === 'high').length) })}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={entryFor !== null} onClose={() => setEntryFor(null)} fullWidth maxWidth="sm">
        <DialogTitle>{t('phase.reconCreateEntry')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Typography variant="body2">{t('phase.reconCreateEntryBody')}</Typography>
            <AccountSelect accounts={accounts.data} label={t('phase.journalAccount')} value={entryAccount} onChange={setEntryAccount} />
            <TextField size="small" label={t('phase.journalNarration')} value={entryNote} onChange={(e) => setEntryNote(e.target.value)} />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEntryFor(null)}>{t('common.cancel')}</Button>
          <Button variant="contained" disabled={!entryAccount || createEntry.isPending} onClick={() => createEntry.mutate()}>{t('phase.reconPostAndMatch')}</Button>
        </DialogActions>
      </Dialog>

      <Dialog open={finaliseOpen} onClose={() => setFinaliseOpen(false)}>
        <DialogTitle>{t('phase.reconFinalise')}</DialogTitle>
        <DialogContent>
          <Typography variant="body2">{t('phase.reconFinaliseBody')}</Typography>
          {diff !== null && diff !== 0 ? (
            <Alert severity="warning" sx={{ mt: 1 }}>
              {smallDiff && owner ? t('phase.reconWriteOffOffer', { amount: formatMoney(diff) }) : t('phase.reconDifferenceBlocks', { amount: formatMoney(diff) })}
            </Alert>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setFinaliseOpen(false)}>{t('common.cancel')}</Button>
          {diff !== null && diff !== 0 && smallDiff && owner ? (
            <Button color="warning" variant="contained" disabled={finalise.isPending} onClick={() => finalise.mutate(true)}>{t('phase.reconWriteOffFinalise')}</Button>
          ) : (
            <Button variant="contained" disabled={finalise.isPending || (diff !== null && diff !== 0)} onClick={() => finalise.mutate(false)}>{t('phase.reconFinalise')}</Button>
          )}
        </DialogActions>
      </Dialog>

      <ConfirmDialog
        open={reopenOpen}
        title={t('phase.reconReopen')}
        body={t('phase.reconReopenBody')}
        confirmLabel={t('phase.reconReopen')}
        confirmColor="warning"
        requireReason={{ label: t('phase.reasonLabel'), maxLength: 200 }}
        onClose={() => setReopenOpen(false)}
        onConfirm={(reason) => reopen.mutate(reason)}
      />
    </PageShell>
  );
}

function Figure({ label, value, strong, color }: { label: string; value: string; strong?: boolean; color?: string }) {
  return (
    <Box>
      <Typography variant="caption" color="text.secondary">{label}</Typography>
      <Typography variant="body1" sx={{ fontWeight: strong ? 700 : 400, color }}>{value}</Typography>
    </Box>
  );
}
