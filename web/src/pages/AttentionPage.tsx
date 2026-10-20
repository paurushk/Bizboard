import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Snackbar from '@mui/material/Snackbar';
import Stack from '@mui/material/Stack';
import Tab from '@mui/material/Tab';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Tabs from '@mui/material/Tabs';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import useMediaQuery from '@mui/material/useMediaQuery';
import { useTheme } from '@mui/material/styles';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import {
  assignAttentionRow,
  dismissAttentionRow,
  getAttentionFeed,
  listCompanyUsers,
  markAttentionSeen,
  reopenAttentionRow,
  snoozeAttentionRow,
} from '@/api/resources';
import { isRuntimeFlagEnabled, useFeatureFlagEpoch } from '@/config/featureFlags';
import { AttentionRowActions } from '@/components/attention/AttentionRowActions';
import { attentionActionLabel, attentionReason, attentionTitle } from '@/components/attention/rowText';
import { DisclaimerBanner, MoneyText, PageHeader, SeverityChip } from '@/components/insights';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { t, useLocale } from '@/i18n';
import type { AttentionRow } from '@/types/domain';
import { formatMoney } from '@/utils/money';
import { safeAppPath } from '@/utils/safeUrl';

const PAGE_SIZE = 25;
const LEFT_KEY = 'bb_attention_left';

type AttentionTab = 'open' | 'snoozed' | 'dismissed';

function rupeesFromPaise(paise: number): number {
  return (Number(paise) || 0) / 100;
}

const BASIS_KEYS: Record<string, string> = {
  overdue: 'attention.basisOverdue',
  invoice_total: 'attention.basisInvoiceTotal',
  tax_delta: 'attention.basisTaxDelta',
  credit_at_risk: 'attention.basisCreditAtRisk',
  received_not_posted: 'attention.basisReceivedNotPosted',
  promised: 'attention.basisPromised',
  payable_due: 'attention.basisPayableDue',
  amount: 'attention.basisAmount',
};

function basisLabel(basis?: string): string {
  const key = basis ? BASIS_KEYS[basis] : undefined;
  return key ? t(key) : '';
}

function ageLabel(days?: number): string {
  if (!days) return t('attention.ageToday');
  if (days === 1) return t('attention.ageOne');
  return t('attention.ageDays', { n: days });
}

function shortDate(value?: string | null): string {
  if (!value) return '';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString();
}

export function AttentionPage() {
  useLocale();
  const qc = useQueryClient();
  const theme = useTheme();
  const compact = useMediaQuery(theme.breakpoints.down('sm'));
  useFeatureFlagEpoch();
  const assignmentOn = isRuntimeFlagEnabled('ENABLE_ACTION_ASSIGNMENT');
  const [tab, setTab] = useState<AttentionTab>('open');
  const [severity, setSeverity] = useState('');
  const [category, setCategory] = useState('');
  const [assigned, setAssigned] = useState<'' | 'mine' | 'unassigned'>('');
  const [limit, setLimit] = useState(PAGE_SIZE);
  const assignedFilter = assignmentOn ? assigned : '';
  const query = useQuery({
    queryKey: ['attention-rows', tab, severity, category, assignedFilter, limit],
    queryFn: () =>
      getAttentionFeed({
        status: tab,
        severity: tab === 'open' ? severity : undefined,
        category: tab === 'open' ? category : undefined,
        assigned: tab === 'open' && assignedFilter ? assignedFilter : undefined,
        limit: tab === 'open' ? limit : undefined,
      }),
    placeholderData: keepPreviousData,
  });
  const members = useQuery({
    queryKey: ['company-users'],
    queryFn: listCompanyUsers,
    enabled: assignmentOn,
  });
  const [pending, setPending] = useState<AttentionRow | null>(null);
  const [reason, setReason] = useState('');
  const [snoozeDays, setSnoozeDays] = useState('7');
  const [customDays, setCustomDays] = useState('14');
  // Setting aside a row that needs a reason (a possible duplicate payment, any critical row) keeps it.
  const [dismissing, setDismissing] = useState<AttentionRow | null>(null);
  const [dismissReason, setDismissReason] = useState('');
  const [assigning, setAssigning] = useState<AttentionRow | null>(null);
  const [assignee, setAssignee] = useState('');
  const [dueDate, setDueDate] = useState('');
  const [notice, setNotice] = useState<{ text: string; undoKey?: string } | null>(null);

  // A person who follows Fix and comes back should be told if that row is now gone. Read once on arrival.
  const [left] = useState<{ key: string; title: string } | null>(() => {
    try {
      const raw = sessionStorage.getItem(LEFT_KEY);
      sessionStorage.removeItem(LEFT_KEY);
      return raw ? (JSON.parse(raw) as { key: string; title: string }) : null;
    } catch {
      return null;
    }
  });
  const [resolvedClosed, setResolvedClosed] = useState(false);
  const rememberFix = (row: AttentionRow) => {
    try {
      sessionStorage.setItem(LEFT_KEY, JSON.stringify({ key: row.dedupeKey, title: attentionTitle(row) }));
    } catch {
      /* storage blocked: no return message */
    }
  };
  // Rows first seen after this visit show as "new" next time.
  useEffect(() => {
    return () => {
      void Promise.resolve(markAttentionSeen()).catch(() => undefined);
    };
  }, []);

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['attention-rows'] });
    void qc.invalidateQueries({ queryKey: ['learning-report'] });
  };
  const dismiss = useMutation({
    mutationFn: ({ key, reason }: { key: string; reason?: string }) => (reason ? dismissAttentionRow(key, reason) : dismissAttentionRow(key)),
    onSuccess: (_data, vars) => {
      setDismissing(null);
      setNotice({ text: t('attention.dismissedToast'), undoKey: vars.key });
      refresh();
    },
  });
  const snooze = useMutation({
    mutationFn: ({ key, reason, days }: { key: string; reason: string; days: number }) =>
      snoozeAttentionRow(key, reason, days),
    onSuccess: (_data, vars) => {
      setPending(null);
      setReason('');
      setNotice({ text: t('attention.snoozedToast'), undoKey: vars.key });
      refresh();
    },
  });
  const assign = useMutation({
    mutationFn: () => assignAttentionRow(
      assigning!.dedupeKey,
      assignee ? Number(assignee) : null,
      dueDate || null,
    ),
    onSuccess: () => {
      setAssigning(null);
      setNotice({ text: t('attention.assignedToast') });
      refresh();
    },
  });
  const reopen = useMutation({
    mutationFn: (key: string) => reopenAttentionRow(key),
    onSuccess: () => {
      setNotice(null);
      refresh();
    },
  });

  const feed = query.data;
  const customDaysValid = Number.isInteger(Number(customDays)) && Number(customDays) >= 1 && Number(customDays) <= 90;
  const rows = feed?.rows ?? [];
  const filtersActive = Boolean(severity || category || assignedFilter);
  const setAside = tab !== 'open';
  // "Resolved" only when we can see the whole list: no filters, nothing cut off, every check ran.
  const resolvedTitle =
    left && !resolvedClosed && tab === 'open' && query.isSuccess && !query.isFetching && !feed?.degraded
    && !filtersActive && feed?.nextOffset == null && !rows.some((row) => row.dedupeKey === left.key)
      ? left.title
      : '';

  // The same row is drawn as a table row on a wide screen and as a card on a phone.
  const titleId = (row: AttentionRow) => `attention-title-${row.dedupeKey.replace(/[^A-Za-z0-9_-]/g, '_')}`;

  const renderTitle = (row: AttentionRow) => (
    <>
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
        <Typography variant="body2" id={titleId(row)}>{attentionTitle(row)}</Typography>
        {row.isNew ? <Chip size="small" color="info" label={t('attention.newBadge')} /> : null}
        {row.overdue ? <Chip size="small" color="warning" label={t('osPlan.overdue')} /> : null}
      </Stack>
      <Typography variant="caption" color="text.secondary" component="div">
        {setAside
          ? [
              row.stateBy?.name
                ? t('attention.setBy', { who: row.stateBy.name, when: shortDate(row.stateAt) })
                : shortDate(row.stateAt),
              tab === 'snoozed' && row.snoozeUntil ? t('attention.snoozeUntil', { date: shortDate(row.snoozeUntil) }) : '',
              row.conditionCleared === true ? t('attention.resolvedSince') : row.conditionCleared === false ? t('attention.stillOpen') : '',
            ].filter(Boolean).join(' · ')
          : ageLabel(row.ageDays)}
      </Typography>
      {assignmentOn && !setAside ? (
        <Typography variant="caption" color="text.secondary" component="div">
          {row.assignedTo
            ? (members.data ?? []).find((member) => member.id === row.assignedTo)?.fullName || row.assignedTo
            : t('osPlan.unassigned')}
          {row.dueDate ? ` · ${row.dueDate}` : ''}
        </Typography>
      ) : null}
    </>
  );

  const renderAmount = (row: AttentionRow) =>
    row.moneyImpactPaise ? (
      <>
        <MoneyText value={rupeesFromPaise(row.moneyImpactPaise)} />
        {basisLabel(row.amountBasis) ? (
          <Typography variant="caption" color="text.secondary" component="div">
            {basisLabel(row.amountBasis)}
          </Typography>
        ) : null}
      </>
    ) : (
      '—'
    );

  const renderReason = (row: AttentionRow) => (
    <>
      <Typography variant="body2" sx={{ whiteSpace: 'normal' }}>
        {attentionReason(row)}
      </Typography>
      {setAside && row.stateReason ? (
        <Typography variant="caption" color="text.secondary" component="div">
          {t('attention.reason')}: {row.stateReason}
        </Typography>
      ) : null}
    </>
  );

  const renderActions = (row: AttentionRow) => (
    <AttentionRowActions
      row={row}
      setAside={setAside}
      assignmentOn={assignmentOn}
      describedBy={titleId(row)}
      reopenBusy={reopen.isPending && reopen.variables === row.dedupeKey}
      dismissBusy={dismiss.isPending && dismiss.variables?.key === row.dedupeKey}
      onFix={() => rememberFix(row)}
      onReopen={() => reopen.mutate(row.dedupeKey)}
      onAssign={() => {
        assign.reset();
        setAssigning(row);
        setAssignee(row.assignedTo ? String(row.assignedTo) : '');
        setDueDate(row.dueDate ?? '');
      }}
      onSnooze={() => {
        snooze.reset();
        setPending(row);
        setReason('');
        setSnoozeDays('7');
        setCustomDays('14');
      }}
      onDismiss={() => {
        dismiss.reset();
        if (row.code === 'DUPLICATE_PAYMENT' || row.requiresReason) {
          setDismissing(row);
          setDismissReason('');
        } else {
          dismiss.mutate({ key: row.dedupeKey });
        }
      }}
    />
  );

  function changeFilter(apply: () => void) {
    apply();
    setLimit(PAGE_SIZE);
  }

  return (
    <Stack spacing={2}>
      <PageHeader title={t('nav.attention')} />
      <DisclaimerBanner>{t('attention.disclaimer')}</DisclaimerBanner>
      <Tabs
        value={tab}
        onChange={(_e, value: AttentionTab) => { setTab(value); setLimit(PAGE_SIZE); }}
        aria-label={t('nav.attention')}
      >
        <Tab value="open" label={tab === 'open' && feed?.totalCount != null ? `${t('attention.tabOpen')} (${feed.totalCount})` : t('attention.tabOpen')} />
        <Tab value="snoozed" label={t('attention.tabSnoozed')} />
        <Tab value="dismissed" label={t('attention.tabDismissed')} />
      </Tabs>

      {tab === 'open' ? (
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} alignItems={{ sm: 'center' }}>
          <TextField
            select
            size="small"
            label={t('attention.filterSeverity')}
            value={severity}
            onChange={(e) => changeFilter(() => setSeverity(e.target.value))}
            sx={{ minWidth: 150 }}
          >
            <MenuItem value="">{t('attention.filterAll')}</MenuItem>
            {(['critical', 'warning', 'info'] as const).map((value) => (
              <MenuItem key={value} value={value}>
                {t(`attention.sev${value[0].toUpperCase()}${value.slice(1)}`)}
                {feed?.countsBySeverity?.[value] != null ? ` (${feed.countsBySeverity[value]})` : ''}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            select
            size="small"
            label={t('attention.filterCategory')}
            value={category}
            onChange={(e) => changeFilter(() => setCategory(e.target.value))}
            sx={{ minWidth: 150 }}
          >
            <MenuItem value="">{t('attention.filterAll')}</MenuItem>
            {(['money', 'gst', 'stock', 'other'] as const).map((value) => (
              <MenuItem key={value} value={value}>
                {t(`attention.cat${value[0].toUpperCase()}${value.slice(1)}`)}
                {feed?.countsByCategory?.[value] != null ? ` (${feed.countsByCategory[value]})` : ''}
              </MenuItem>
            ))}
          </TextField>
          {assignmentOn ? (
            <TextField
              select
              size="small"
              label={t('attention.filterAssigned')}
              value={assigned}
              onChange={(e) => changeFilter(() => setAssigned(e.target.value as '' | 'mine' | 'unassigned'))}
              sx={{ minWidth: 150 }}
            >
              <MenuItem value="">{t('attention.filterAll')}</MenuItem>
              <MenuItem value="mine">{t('attention.assignedMine')}</MenuItem>
              <MenuItem value="unassigned">{t('attention.assignedUnassigned')}</MenuItem>
            </TextField>
          ) : null}
          {filtersActive ? (
            <Button size="small" onClick={() => { setSeverity(''); setCategory(''); setAssigned(''); setLimit(PAGE_SIZE); }}>
              {t('common.clear')}
            </Button>
          ) : null}
        </Stack>
      ) : null}

      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {query.isError && query.data ? <Alert severity="warning">{t('attention.staleData')}</Alert> : null}
      {query.fetchStatus === 'paused' ? <Alert severity="warning">{t('attention.offlineNotice')}</Alert> : null}
      {tab === 'open' && (feed?.truncatedCodes ?? []).length > 0 ? (
        <Alert severity="info">{t('attention.truncated', { n: feed!.truncatedCodes!.length })}</Alert>
      ) : null}
      {dismiss.isError && !dismissing ? (
        <Alert severity="error" onClose={() => dismiss.reset()}>{getErrorMessage(dismiss.error)}</Alert>
      ) : null}
      {reopen.isError ? (
        <Alert severity="error" onClose={() => reopen.reset()}>{getErrorMessage(reopen.error)}</Alert>
      ) : null}
      {query.isSuccess && rows.length === 0 ? (
        <EmptyState
          description={
            tab === 'snoozed'
              ? t('attention.emptySnoozed')
              : tab === 'dismissed'
                ? t('attention.emptyDismissed')
                : filtersActive
                  ? t('attention.emptyFiltered')
                  : t('attention.empty')
          }
        />
      ) : null}
      {rows.length > 0 && compact ? (
        <Stack spacing={1.5} component="ul" sx={{ listStyle: 'none', p: 0, m: 0 }} aria-label={t('nav.attention')}>
          {rows.map((row) => (
            <Paper key={row.dedupeKey} component="li" variant="outlined" sx={{ p: 2 }}>
              <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={1}>
                <SeverityChip severity={row.severity} />
                <div>{renderAmount(row)}</div>
              </Stack>
              <div style={{ marginTop: 8 }}>{renderTitle(row)}</div>
              <div style={{ marginTop: 8 }}>{renderReason(row)}</div>
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mt: 1.5 }}>
                {renderActions(row)}
              </Stack>
            </Paper>
          ))}
        </Stack>
      ) : null}
      {rows.length > 0 && !compact ? (
        <Paper variant="outlined" tabIndex={0} role="region" aria-label={t('common.scrollableTable')} sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('reports.severity')}</TableCell>
                <TableCell>{t('attention.problem')}</TableCell>
                <TableCell align="right">{t('attention.amountInvolved')}</TableCell>
                <TableCell>{t('attention.why')}</TableCell>
                <TableCell align="right">{t('common.actions')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.dedupeKey} hover>
                  <TableCell>
                    <SeverityChip severity={row.severity} />
                  </TableCell>
                  <TableCell>{renderTitle(row)}</TableCell>
                  <TableCell align="right">{renderAmount(row)}</TableCell>
                  <TableCell sx={{ whiteSpace: 'normal', maxWidth: 360 }}>{renderReason(row)}</TableCell>
                  <TableCell align="right">
                    <Stack direction="row" spacing={1} justifyContent="flex-end">
                      {renderActions(row)}
                    </Stack>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}
      {tab === 'open' && feed?.nextOffset != null ? (
        <Button onClick={() => setLimit((value) => value + PAGE_SIZE)} disabled={query.isFetching}>
          {t('attention.loadMore')}
        </Button>
      ) : null}

      <Dialog open={Boolean(pending)} onClose={() => setPending(null)} fullWidth maxWidth="sm">
        <DialogTitle>{t('attention.snoozeTitle')}</DialogTitle>
        <DialogContent>
          <TextField
            select
            fullWidth
            margin="dense"
            label={t('attention.snoozeFor')}
            value={snoozeDays}
            onChange={(e) => setSnoozeDays(e.target.value)}
          >
            {[1, 7, 30].map((days) => (
              <MenuItem key={days} value={String(days)}>{t('attention.snoozeDays', { n: days })}</MenuItem>
            ))}
            <MenuItem value="custom">{t('attention.snoozeCustom')}</MenuItem>
          </TextField>
          {snoozeDays === 'custom' ? (
            <TextField
              fullWidth
              margin="dense"
              type="number"
              label={t('attention.snoozeCustomDays')}
              value={customDays}
              onChange={(e) => setCustomDays(e.target.value)}
              inputProps={{ min: 1, max: 90 }}
              helperText={t('attention.snoozeCustomHelp')}
              error={!customDaysValid}
            />
          ) : null}
          <TextField
            autoFocus
            fullWidth
            required
            margin="dense"
            label={t('attention.snoozeReason')}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
          {snooze.isError ? <Alert severity="error" sx={{ mt: 1 }}>{getErrorMessage(snooze.error)}</Alert> : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPending(null)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={!reason.trim() || snooze.isPending || (snoozeDays === 'custom' && !customDaysValid)}
            onClick={() => pending && snooze.mutate({ key: pending.dedupeKey, reason: reason.trim(), days: snoozeDays === 'custom' ? Number(customDays) : Number(snoozeDays) })}
          >
            {t('attention.snoozeButton')}
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog open={Boolean(dismissing)} onClose={() => setDismissing(null)} fullWidth maxWidth="sm">
        <DialogTitle>{t('attention.dismiss')}</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            fullWidth
            required
            margin="dense"
            label={dismissing?.code === 'DUPLICATE_PAYMENT' ? t('receipts.dismissReasonPrompt') : t('attention.dismissReasonPrompt')}
            value={dismissReason}
            onChange={(e) => setDismissReason(e.target.value)}
          />
          {dismiss.isError ? <Alert severity="error" sx={{ mt: 1 }}>{getErrorMessage(dismiss.error)}</Alert> : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDismissing(null)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={dismissReason.trim().length < 3 || dismiss.isPending}
            onClick={() => {
              if (!dismissing) return;
              dismiss.mutate({ key: dismissing.dedupeKey, reason: dismissReason.trim() });
            }}
          >
            {t('attention.dismiss')}
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog open={Boolean(assigning)} onClose={() => setAssigning(null)} fullWidth maxWidth="sm">
        <DialogTitle>{t('osPlan.assign')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              select
              label={t('osPlan.assignee')}
              value={assignee}
              onChange={(e) => setAssignee(e.target.value)}
            >
              <MenuItem value="">{t('osPlan.unassigned')}</MenuItem>
              {(members.data ?? []).filter((member) => member.user).map((member) => (
                <MenuItem key={member.id} value={String(member.id)}>{member.fullName || member.email}</MenuItem>
              ))}
            </TextField>
            <TextField
              type="date"
              label={t('osPlan.dueDate')}
              value={dueDate}
              onChange={(e) => setDueDate(e.target.value)}
              InputLabelProps={{ shrink: true }}
            />
            {assign.isError ? <Alert severity="error">{getErrorMessage(assign.error)}</Alert> : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAssigning(null)}>{t('common.cancel')}</Button>
          <Button variant="contained" disabled={!assigning || assign.isPending} onClick={() => assign.mutate()}>
            {t('osPlan.saveAssignment')}
          </Button>
        </DialogActions>
      </Dialog>
      <Snackbar
        open={Boolean(resolvedTitle)}
        autoHideDuration={6000}
        onClose={() => setResolvedClosed(true)}
        message={t('attention.resolvedToast', { title: resolvedTitle })}
      />
      <Snackbar
        open={Boolean(notice)}
        autoHideDuration={6000}
        onClose={() => setNotice(null)}
        message={notice?.text}
        action={
          notice?.undoKey ? (
            <Button color="inherit" size="small" onClick={() => notice.undoKey && reopen.mutate(notice.undoKey)}>
              {t('attention.undo')}
            </Button>
          ) : undefined
        }
      />
    </Stack>
  );
}

export function AttentionQueuePreview({ limit = 5 }: { limit?: number }) {
  const query = useQuery({
    queryKey: ['attention-rows', 'preview', limit],
    queryFn: () => getAttentionFeed({ status: 'open', limit }),
  });
  if (query.isLoading) return <LoadingState />;
  if (query.isError) {
    return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  }
  const rows = query.data?.rows ?? [];
  if (rows.length === 0) return <EmptyState description={t('attention.empty')} />;
  const hidden = Math.max(0, (query.data?.count ?? rows.length) - rows.length);
  return (
    <Stack spacing={1}>
      <Typography variant="caption" color="text.secondary">
        {(query.data?.count ?? rows.length) === 1
          ? t('attention.totalItemsOne')
          : t('attention.totalItems', { n: query.data?.count ?? rows.length })}
        {query.data?.criticalCount ? ` · ${t('attention.countCritical', { n: query.data.criticalCount })}` : ''}
      </Typography>
      {rows.map((row) => (
        <Stack
          key={row.dedupeKey}
          direction={{ xs: 'column', sm: 'row' }}
          spacing={1}
          alignItems={{ xs: 'flex-start', sm: 'center' }}
          justifyContent="space-between"
          sx={{ py: 0.5, borderBottom: '1px solid', borderColor: 'divider' }}
        >
          <Stack direction="row" spacing={1} alignItems="center" sx={{ flex: 1, minWidth: 0 }}>
            <SeverityChip severity={row.severity} />
            <Typography variant="body2">
              {attentionTitle(row)}
            </Typography>
            {row.isNew ? <Chip size="small" color="info" label={t('attention.newBadge')} /> : null}
          </Stack>
          <Stack direction="row" spacing={1} alignItems="center" alignSelf={{ xs: 'flex-end', sm: 'auto' }}>
            {row.moneyImpactPaise ? (
              <Typography variant="caption" color="text.secondary">
                {formatMoney(rupeesFromPaise(row.moneyImpactPaise))}
                {basisLabel(row.amountBasis) ? ` · ${basisLabel(row.amountBasis)}` : ''}
              </Typography>
            ) : null}
            <Button component={RouterLink} to={safeAppPath(row.actionHref, "/attention")} size="small" sx={{ minHeight: { xs: 44, sm: 30 } }}>
              {attentionActionLabel(row)}
            </Button>
          </Stack>
        </Stack>
      ))}
      <Button component={RouterLink} to="/attention" size="small">
        {hidden > 0 ? `${t('attention.seeAll')} (${t('attention.moreRows', { n: hidden })})` : t('attention.seeAll')}
      </Button>
    </Stack>
  );
}
