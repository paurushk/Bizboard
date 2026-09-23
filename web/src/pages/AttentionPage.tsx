import Button from '@mui/material/Button';
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
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { assignAttentionRow, listAttentionRows, listCompanyUsers, snoozeAttentionRow } from '@/api/resources';
import { isRuntimeFlagEnabled, useFeatureFlagEpoch } from '@/config/featureFlags';
import { DisclaimerBanner, MoneyText, PageHeader, SeverityChip } from '@/components/insights';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';
import type { AttentionRow } from '@/types/domain';
import { formatMoney } from '@/utils/money';
import { safeAppPath } from '@/utils/safeUrl';

function rupeesFromPaise(paise: number): number {
  return (Number(paise) || 0) / 100;
}

export function AttentionPage() {
  const qc = useQueryClient();
  useFeatureFlagEpoch();
  const assignmentOn = isRuntimeFlagEnabled('ENABLE_ACTION_ASSIGNMENT');
  const [mine, setMine] = useState(false);
  const query = useQuery({
    queryKey: ['attention-rows', assignmentOn && mine],
    queryFn: () => listAttentionRows({ mine: assignmentOn && mine }),
  });
  const members = useQuery({
    queryKey: ['company-users'],
    queryFn: listCompanyUsers,
    enabled: assignmentOn,
  });
  const [pending, setPending] = useState<AttentionRow | null>(null);
  const [reason, setReason] = useState('');
  const [assigning, setAssigning] = useState<AttentionRow | null>(null);
  const [assignee, setAssignee] = useState('');
  const [dueDate, setDueDate] = useState('');
  const snooze = useMutation({
    mutationFn: ({ key, reason }: { key: string; reason: string }) => snoozeAttentionRow(key, reason, 7),
    onSuccess: () => {
      setPending(null);
      setReason('');
      void qc.invalidateQueries({ queryKey: ['attention-rows'] });
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
      void qc.invalidateQueries({ queryKey: ['attention-rows'] });
    },
  });

  return (
    <Stack spacing={2}>
      <PageHeader title={t('nav.attention')} />
      {assignmentOn ? (
        <Button variant={mine ? 'contained' : 'outlined'} onClick={() => setMine((value) => !value)}>
          {t('osPlan.myActions')}
        </Button>
      ) : null}
      <DisclaimerBanner>{t('attention.disclaimer')}</DisclaimerBanner>
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {!query.isLoading && (query.data?.length ?? 0) === 0 ? (
        <EmptyState description={t('attention.empty')} />
      ) : null}
      {(query.data?.length ?? 0) > 0 ? (
        <Paper variant="outlined" sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('reports.severity')}</TableCell>
                <TableCell>{t('attention.problem')}</TableCell>
                <TableCell align="right">{t('attention.money')}</TableCell>
                <TableCell>{t('attention.why')}</TableCell>
                <TableCell align="right">{t('common.actions')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {query.data!.map((row) => (
                <TableRow key={row.dedupeKey} hover>
                  <TableCell>
                    <SeverityChip severity={row.severity} />
                  </TableCell>
                  <TableCell>
                    <Stack direction="row" spacing={1} alignItems="center">
                      <Typography variant="body2">{row.title}</Typography>
                      {row.overdue ? <Chip size="small" color="warning" label={t('osPlan.overdue')} /> : null}
                    </Stack>
                    {assignmentOn ? (
                      <Typography variant="caption" color="text.secondary">
                        {row.assignedTo
                          ? (members.data ?? []).find((member) => member.id === row.assignedTo)?.fullName || row.assignedTo
                          : t('osPlan.unassigned')}
                        {row.dueDate ? ` · ${row.dueDate}` : ''}
                      </Typography>
                    ) : null}
                  </TableCell>
                  <TableCell align="right">
                    {row.moneyImpactPaise ? (
                      <MoneyText value={rupeesFromPaise(row.moneyImpactPaise)} />
                    ) : (
                      '—'
                    )}
                  </TableCell>
                  <TableCell>
                    <Typography variant="caption" color="text.secondary">
                      {row.reason}
                    </Typography>
                  </TableCell>
                  <TableCell align="right">
                    <Stack direction="row" spacing={1} justifyContent="flex-end">
                      <Button component={RouterLink} to={safeAppPath(row.actionHref, "/attention")} size="small" variant="contained">
                        {row.actionLabel || t('attention.fix')}
                      </Button>
                      {assignmentOn ? (
                        <Button size="small" onClick={() => {
                          setAssigning(row);
                          setAssignee(row.assignedTo ? String(row.assignedTo) : '');
                          setDueDate(row.dueDate ?? '');
                        }}>
                          {t('osPlan.assign')}
                        </Button>
                      ) : null}
                      <Button size="small" onClick={() => { setPending(row); setReason(''); }}>
                        {t('insights.snooze')}
                      </Button>
                    </Stack>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}

      <Dialog open={Boolean(pending)} onClose={() => setPending(null)} fullWidth maxWidth="sm">
        <DialogTitle>{t('attention.snoozeTitle')}</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            fullWidth
            required
            margin="dense"
            label={t('attention.snoozeReason')}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPending(null)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={!reason.trim() || snooze.isPending}
            onClick={() => pending && snooze.mutate({ key: pending.dedupeKey, reason: reason.trim() })}
          >
            {t('insights.snooze')}
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
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAssigning(null)}>{t('common.cancel')}</Button>
          <Button variant="contained" disabled={!assigning || assign.isPending} onClick={() => assign.mutate()}>
            {t('osPlan.saveAssignment')}
          </Button>
        </DialogActions>
      </Dialog>
      {snooze.isError ? <ErrorState message={getErrorMessage(snooze.error)} error={snooze.error} /> : null}
      {assign.isError ? <ErrorState message={getErrorMessage(assign.error)} error={assign.error} /> : null}
    </Stack>
  );
}

export function AttentionQueuePreview({ limit = 5 }: { limit?: number }) {
  const query = useQuery({ queryKey: ['attention-rows'], queryFn: listAttentionRows });
  if (query.isLoading) return <LoadingState />;
  if (query.isError) {
    return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  }
  const rows = (query.data ?? []).slice(0, limit);
  if (rows.length === 0) return <EmptyState description={t('attention.empty')} />;
  return (
    <Stack spacing={1}>
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
              {row.title}
            </Typography>
          </Stack>
          <Stack direction="row" spacing={1} alignItems="center" alignSelf={{ xs: 'flex-end', sm: 'auto' }}>
            {row.moneyImpactPaise ? (
              <Typography variant="caption" color="text.secondary">
                {formatMoney(rupeesFromPaise(row.moneyImpactPaise))}
              </Typography>
            ) : null}
            <Button component={RouterLink} to={safeAppPath(row.actionHref, "/attention")} size="small">
              {row.actionLabel || t('attention.fix')}
            </Button>
          </Stack>
        </Stack>
      ))}
      <Button component={RouterLink} to="/attention" size="small">
        {t('attention.seeAll')}
      </Button>
    </Stack>
  );
}
