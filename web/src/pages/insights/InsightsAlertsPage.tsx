import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import FormControlLabel from '@mui/material/FormControlLabel';
import Link from '@mui/material/Link';
import Menu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import Tab from '@mui/material/Tab';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Tabs from '@mui/material/Tabs';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import {
  listBusinessAlerts,
  refreshBusinessAlerts,
  snoozeBusinessAlert,
  unsnoozeBusinessAlert,
} from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { DisclaimerBanner, PageHeader, SeverityChip, resolveAlertHref, useMaskedText } from '@/components/insights';
import { AiConsentOffScreen, useAiConsentOn } from '@/components/insights/AiConsentGate';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';
import type { BusinessAlert } from '@/types/domain';
import { formatDateTime } from '@/utils/dateTime';
import { canViewFinancialReports } from '@/utils/permissions';

type Tab = 'open' | 'snoozed';
const SEVERITIES = ['critical', 'warning', 'info'] as const;

function SnoozeMenu({ disabled, onPick }: { disabled: boolean; onPick: (days: number) => void }) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  return (
    <>
      <Button size="small" disabled={disabled} onClick={(e) => setAnchor(e.currentTarget)}>
        {t('insights.snoozeMenu')}
      </Button>
      <Menu anchorEl={anchor} open={anchor != null} onClose={() => setAnchor(null)}>
        {(
          [
            [1, t('insights.snooze1')],
            [7, t('insights.snooze7')],
            [30, t('insights.snooze30')],
          ] as [number, string][]
        ).map(([days, label]) => (
          <MenuItem
            key={days}
            onClick={() => {
              setAnchor(null);
              onPick(days);
            }}
          >
            {label}
          </MenuItem>
        ))}
      </Menu>
    </>
  );
}

export function InsightsAlertsPage() {
  const consentOn = useAiConsentOn();
  const { user } = useAuth();
  const mask = useMaskedText();
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>('open');
  const [severity, setSeverity] = useState('');
  const [showCodes, setShowCodes] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<number | null>(null);
  const isOwner = user?.role === 'OWNER';

  const query = useQuery({
    queryKey: ['insights-alerts-page', tab, severity],
    queryFn: () =>
      listBusinessAlerts({
        ...(tab === 'snoozed' ? { status: 'SNOOZED' } : {}),
        ...(severity ? { severity } : {}),
      }),
    enabled: consentOn,
  });
  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ['insights-alerts-page'] });
    void qc.invalidateQueries({ queryKey: ['insights-alerts'] });
  };
  const snooze = useMutation({
    mutationFn: ({ id, days }: { id: number; days: number }) => snoozeBusinessAlert(id, days),
    onMutate: ({ id }) => {
      setPendingId(id);
      setNotice(null);
    },
    onSuccess: () => {
      setNotice(t('insights.alertSnoozed'));
      invalidate();
    },
    onSettled: () => setPendingId(null),
  });
  const reopen = useMutation({
    mutationFn: (id: number) => unsnoozeBusinessAlert(id),
    onMutate: (id) => {
      setPendingId(id);
      setNotice(null);
    },
    onSuccess: () => {
      setNotice(t('insights.alertReopened'));
      invalidate();
    },
    onSettled: () => setPendingId(null),
  });
  const refresh = useMutation({
    mutationFn: () => refreshBusinessAlerts(),
    onMutate: () => setNotice(null),
    onSuccess: invalidate,
  });

  if (!consentOn) return <AiConsentOffScreen title={t('nav.insightsAlerts')} />;

  const severityLabels = {
    critical: t('insights.sevCritical'),
    warning: t('insights.sevWarning'),
    info: t('insights.sevInfo'),
  };
  const rows: BusinessAlert[] = query.data ?? [];
  const mutationError = snooze.error ?? reopen.error ?? refresh.error;

  return (
    <Stack spacing={2}>
      <PageHeader
        title={t('nav.insightsAlerts')}
        subtitle={query.dataUpdatedAt ? t('insights.updatedAt', { time: formatDateTime(new Date(query.dataUpdatedAt).toISOString()) }) : undefined}
        actions={
          isOwner ? (
            <Button variant="outlined" onClick={() => refresh.mutate()} disabled={refresh.isPending}>
              {t('insights.refreshAlerts')}
            </Button>
          ) : null
        }
      />
      <DisclaimerBanner>{t('honesty.insightsNotBooks')}</DisclaimerBanner>
      <DisclaimerBanner>{t('insights.disclaimer')}</DisclaimerBanner>
      {canViewFinancialReports(user) ? (
        <Typography variant="body2" color="text.secondary">
          {t('insights.seeAttention')}{' '}
          <Link component={RouterLink} to="/attention">
            {t('nav.attention')}
          </Link>
        </Typography>
      ) : null}

      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems={{ sm: 'center' }} justifyContent="space-between">
        <Tabs value={tab} onChange={(_e, v: Tab) => setTab(v)} aria-label={t('nav.insightsAlerts')}>
          <Tab value="open" label={t('insights.tabOpen')} />
          <Tab value="snoozed" label={t('insights.tabSnoozed')} />
        </Tabs>
        <Stack direction="row" spacing={2} alignItems="center">
          <TextField
            select
            size="small"
            label={t('reports.severity')}
            value={severity}
            onChange={(e) => setSeverity(e.target.value)}
            sx={{ minWidth: 160 }}
          >
            <MenuItem value="">{t('insights.allSeverities')}</MenuItem>
            {SEVERITIES.map((s) => (
              <MenuItem key={s} value={s}>
                {severityLabels[s]}
              </MenuItem>
            ))}
          </TextField>
          <FormControlLabel
            control={<Switch size="small" checked={showCodes} onChange={(e) => setShowCodes(e.target.checked)} />}
            label={t('insights.showCodes')}
          />
        </Stack>
      </Stack>

      {notice ? <Alert severity="success">{notice}</Alert> : null}
      {mutationError ? <Alert severity="error">{getErrorMessage(mutationError)}</Alert> : null}

      {query.isLoading ? (
        <LoadingState />
      ) : query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : rows.length === 0 ? (
        <EmptyState description={tab === 'snoozed' ? t('insights.noSnoozed') : t('insights.noAlerts')} />
      ) : (
        <Paper variant="outlined" tabIndex={0} role="region" aria-label={t('common.scrollableTable')} sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('reports.severity')}</TableCell>
                <TableCell>{t('reports.message')}</TableCell>
                <TableCell>{t('insights.openLink')}</TableCell>
                <TableCell align="right">{t('common.actions')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((alert) => {
                const href = resolveAlertHref({ ...alert, ctaPath: alert.ctaPath });
                const busy = pendingId === alert.id;
                const snoozedNow = alert.status === 'SNOOZED';
                return (
                  <TableRow key={alert.id} hover>
                    <TableCell>
                      <SeverityChip severity={alert.severity} />
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">{mask(alert.message)}</Typography>
                      {showCodes ? (
                        <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'ui-monospace, monospace' }}>
                          {alert.code}
                        </Typography>
                      ) : null}
                      {snoozedNow && alert.snoozedUntil ? (
                        <Typography variant="caption" color="text.secondary" display="block">
                          {alert.snoozedByName
                            ? t('insights.snoozedBy', { name: alert.snoozedByName, date: formatDateTime(alert.snoozedUntil) })
                            : t('insights.snoozedUntil', { date: formatDateTime(alert.snoozedUntil) })}
                        </Typography>
                      ) : null}
                    </TableCell>
                    <TableCell>
                      {href ? (
                        <Link component={RouterLink} to={href}>
                          {t('insights.openLink')}
                        </Link>
                      ) : (
                        '—'
                      )}
                    </TableCell>
                    <TableCell align="right">
                      {snoozedNow ? (
                        <Button size="small" disabled={busy} onClick={() => reopen.mutate(alert.id)}>
                          {t('insights.unsnooze')}
                        </Button>
                      ) : (
                        <SnoozeMenu disabled={busy} onPick={(days) => snooze.mutate({ id: alert.id, days })} />
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </Paper>
      )}
    </Stack>
  );
}
