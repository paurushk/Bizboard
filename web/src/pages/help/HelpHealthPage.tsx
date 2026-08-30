import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getHelpHealth, listHelpFeedback, resolveHelpFeedback } from '@/api/help';
import { useAuth } from '@/auth/AuthContext';
import { LoadingState, ErrorState } from '@/components/PageState';
import { t } from '@/i18n';
import { getErrorMessage } from '@/api/client';
import { isOwner } from '@/utils/permissions';
import { HELP_INTENTS } from './intents';
import { ForbiddenPage } from '@/pages/ForbiddenPage';
import { isHelpV2Enabled } from '@/config/features';

const SIX_MONTHS_MS = 1000 * 60 * 60 * 24 * 182;

export function HelpHealthPage() {
  const { user } = useAuth();
  const staff = Boolean((user as { isStaff?: boolean } | null)?.isStaff);
  const allowed = isOwner(user?.role ?? 'VIEWER') || staff;
  const qc = useQueryClient();
  const health = useQuery({ queryKey: ['help-health', staff], queryFn: () => getHelpHealth(staff) });
  const feedback = useQuery({ queryKey: ['help-feedback', staff], queryFn: () => listHelpFeedback(staff) });
  const resolveRow = useMutation({
    mutationFn: (id: number) => resolveHelpFeedback(id, staff),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['help-feedback'] });
      void qc.invalidateQueries({ queryKey: ['help-health'] });
    },
  });

  if (!isHelpV2Enabled() || !allowed) return <ForbiddenPage />;
  if (health.isLoading) return <LoadingState />;
  if (health.isError) {
    return <ErrorState message={getErrorMessage(health.error)} error={health.error} onRetry={() => void health.refetch()} />;
  }
  const data = health.data;
  const stale = HELP_INTENTS.filter((i) => {
    const t0 = Date.parse(i.lastReviewed);
    return Number.isFinite(t0) && Date.now() - t0 > SIX_MONTHS_MS;
  });
  const missingHi = HELP_INTENTS.filter((i) => !i.answer.hi);

  return (
    <Stack spacing={2}>
      <Typography variant="h4">{t('help.healthTitle')}</Typography>
      <Typography variant="body2" color="text.secondary">
        {t('help.healthSubtitle')}
      </Typography>
      <Alert severity="info">{t('help.healthScope', { scope: data?.scope ?? 'company' })}</Alert>
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={3}>
          <Stat label={t('help.metricResolution')} value={pct(data?.resolutionRate)} />
          <Stat label={t('help.metricEscalation')} value={pct(data?.escalationRate)} />
          <Stat label={t('help.metricRepeat')} value={pct(data?.repeatQueryRate)} />
          <Stat label={t('help.metricTtr')} value={fmtSeconds(data?.timeToResolutionSeconds)} />
          <Stat label={t('help.metricZero')} value={pct(data?.zeroResultRate)} />
          <Stat label={t('help.metricOpens')} value={String(data?.opens ?? 0)} />
        </Stack>
      </Paper>
      <Section title={t('help.topZero')}>
        <SimpleTable
          rows={(data?.topZeroQueries ?? []).map((r) => [r.query, String(r.n)])}
          headers={[t('help.query'), t('help.count')]}
        />
      </Section>
      <Section title={t('help.worstIntents')}>
        <SimpleTable
          rows={(data?.intents ?? [])
            .slice()
            .sort((a, b) => (a.resolutionRate ?? 1) - (b.resolutionRate ?? 1))
            .slice(0, 10)
            .map((r) => [r.intentId, pct(r.resolutionRate), String(r.opens)])}
          headers={[t('help.intent'), t('help.metricResolution'), t('help.metricOpens')]}
        />
      </Section>
      <Section title={t('help.repeatQueries')}>
        <SimpleTable
          rows={(data?.repeatQueries ?? []).map((r) => [r.query, String(r.n)])}
          headers={[t('help.query'), t('help.count')]}
        />
      </Section>
      <Section title={t('help.staleContent')}>
        {stale.length === 0 ? (
          <Typography variant="body2">{t('help.noStale')}</Typography>
        ) : (
          <SimpleTable
            rows={stale.map((i) => [i.intentId, i.lastReviewed])}
            headers={[t('help.intent'), t('help.lastReviewed')]}
          />
        )}
      </Section>
      <Section title={t('help.translationDebt')}>
        <Typography variant="body2">{missingHi.map((i) => i.intentId).join(', ') || t('help.noDebt')}</Typography>
      </Section>
      <Section title={t('help.feedbackBacklog')}>
        {(feedback.data ?? []).length === 0 ? (
          <Typography variant="body2">{t('common.empty')}</Typography>
        ) : (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('help.intent')}</TableCell>
                <TableCell>{t('help.query')}</TableCell>
                <TableCell>{t('help.feedbackNote')}</TableCell>
                <TableCell>{t('common.actions')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(feedback.data ?? []).map((r) => (
                <TableRow key={r.id}>
                  <TableCell>{r.intentId || '—'}</TableCell>
                  <TableCell>{r.query.slice(0, 80)}</TableCell>
                  <TableCell>{r.note.slice(0, 80)}</TableCell>
                  <TableCell>
                    <Button
                      size="small"
                      aria-label={t('help.markResolvedAria')}
                      disabled={resolveRow.isPending}
                      onClick={() => resolveRow.mutate(r.id)}
                    >
                      {t('help.markResolved')}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Section>
    </Stack>
  );
}

function pct(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return '—';
  return `${Math.round(n * 100)}%`;
}

function fmtSeconds(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return '—';
  if (n < 60) return `${Math.round(n)}s`;
  if (n < 3600) return `${Math.round(n / 60)}m`;
  return `${(n / 3600).toFixed(1)}h`;
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Stack>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="h5">{value}</Typography>
    </Stack>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Typography variant="subtitle1" sx={{ mb: 1 }}>
        {title}
      </Typography>
      {children}
    </Paper>
  );
}

function SimpleTable({ headers, rows }: { headers: string[]; rows: string[][] }) {
  if (!rows.length) {
    return <Typography variant="body2">{t('common.empty')}</Typography>;
  }
  return (
    <Table size="small">
      <TableHead>
        <TableRow>
          {headers.map((h) => (
            <TableCell key={h}>{h}</TableCell>
          ))}
        </TableRow>
      </TableHead>
      <TableBody>
        {rows.map((row, i) => (
          <TableRow key={i}>
            {row.map((c, j) => (
              <TableCell key={j}>{c}</TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
