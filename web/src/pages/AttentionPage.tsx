import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
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
import { listAttentionRows, snoozeAttentionRow } from '@/api/resources';
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
  const query = useQuery({ queryKey: ['attention-rows'], queryFn: listAttentionRows });
  const [pending, setPending] = useState<AttentionRow | null>(null);
  const [reason, setReason] = useState('');
  const snooze = useMutation({
    mutationFn: ({ key, reason }: { key: string; reason: string }) => snoozeAttentionRow(key, reason, 7),
    onSuccess: () => {
      setPending(null);
      setReason('');
      void qc.invalidateQueries({ queryKey: ['attention-rows'] });
    },
  });

  return (
    <Stack spacing={2}>
      <PageHeader title={t('nav.attention')} />
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
                    <Typography variant="body2">{row.title}</Typography>
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
      {snooze.isError ? <ErrorState message={getErrorMessage(snooze.error)} error={snooze.error} /> : null}
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
        <Stack key={row.dedupeKey} direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
          <SeverityChip severity={row.severity} />
          <Typography variant="body2" sx={{ flex: 1, minWidth: 160 }}>
            {row.title}
          </Typography>
          {row.moneyImpactPaise ? (
            <Typography variant="caption">{formatMoney(rupeesFromPaise(row.moneyImpactPaise))}</Typography>
          ) : null}
          <Button component={RouterLink} to={safeAppPath(row.actionHref, "/attention")} size="small">
            {row.actionLabel || t('attention.fix')}
          </Button>
        </Stack>
      ))}
      <Button component={RouterLink} to="/attention" size="small">
        {t('attention.seeAll')}
      </Button>
    </Stack>
  );
}
