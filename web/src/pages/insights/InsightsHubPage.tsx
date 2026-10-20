import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardActionArea from '@mui/material/CardActionArea';
import CardContent from '@mui/material/CardContent';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { generateDailySummary, getDailySummary, listBusinessAlerts, listGrowthHints } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { HonestyBanner } from '@/components/HonestyBanner';
import { AiConsentOffScreen, useAiConsentOn } from '@/components/insights/AiConsentGate';
import {
  DisclaimerBanner,
  KpiStat,
  PageHeader,
  SeverityChip,
  useMaskedText,
} from '@/components/insights';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { t, useLocale } from '@/i18n';
import { formatDateTime } from '@/utils/dateTime';
import { canUseAiAssistant, canViewFinancialReports } from '@/utils/permissions';

export function InsightsHubPage() {
  useLocale();
  const { user } = useAuth();
  const mask = useMaskedText();
  const consentOn = useAiConsentOn();
  const qc = useQueryClient();
  const [notice, setNotice] = useState<string | null>(null);
  const summary = useQuery({ queryKey: ['insights-summary'], queryFn: () => getDailySummary(), enabled: consentOn });
  const alerts = useQuery({ queryKey: ['insights-alerts'], queryFn: () => listBusinessAlerts(), enabled: consentOn });
  const hints = useQuery({ queryKey: ['insights-hints'], queryFn: () => listGrowthHints(), enabled: consentOn });
  const afterBuild = () => {
    void qc.invalidateQueries({ queryKey: ['insights-summary'] });
    void qc.invalidateQueries({ queryKey: ['insights-alerts'] });
  };
  // Rebuilding the summary never sends anything; the digest is a separate, explicit action.
  const refresh = useMutation({
    mutationFn: () => generateDailySummary(),
    onMutate: () => setNotice(null),
    onSuccess: afterBuild,
  });
  const digest = useMutation({
    mutationFn: () => generateDailySummary({ send: true }),
    onMutate: () => setNotice(null),
    onSuccess: () => {
      setNotice(t('insights.digestSent'));
      afterBuild();
    },
  });

  if (!consentOn) return <AiConsentOffScreen title={t('nav.insights')} />;
  if (summary.isLoading) return <LoadingState />;
  if (summary.isError) {
    return <ErrorState message={getErrorMessage(summary.error)} error={summary.error} onRetry={() => void summary.refetch()} />;
  }

  const data = summary.data!;
  const canGenerate = data.canGenerate === true;
  const hasSummary = data.id != null;
  const kpis = data.kpis ?? {};
  const topAlerts = (alerts.data ?? []).slice(0, 5);
  // The count beside the list comes from the same live list, not the frozen summary figure.
  const openAlertCount = alerts.data ? alerts.data.length : (kpis.openAlerts ?? kpis.open_alerts ?? 0);
  const busy = refresh.isPending || digest.isPending;

  return (
    <Stack spacing={2}>
      <PageHeader
        title={t('nav.insights')}
        subtitle={t('insights.todaySummary')}
        actions={
          canGenerate && hasSummary ? (
            <>
              <Button variant="outlined" onClick={() => refresh.mutate()} disabled={busy}>
                {t('insights.generate')}
              </Button>
              <Button variant="text" onClick={() => digest.mutate()} disabled={busy}>
                {t('insights.sendDigest')}
              </Button>
            </>
          ) : null
        }
      />
      <HonestyBanner messageKey="honesty.insightsNotBooks" />
      <DisclaimerBanner>{t('insights.disclaimer')}</DisclaimerBanner>
      {refresh.isError ? <Alert severity="error">{`${t('insights.refreshFailed')} ${getErrorMessage(refresh.error)}`}</Alert> : null}
      {digest.isError ? <Alert severity="error">{getErrorMessage(digest.error)}</Alert> : null}
      {notice ? <Alert severity="success">{notice}</Alert> : null}

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} useFlexGap flexWrap="wrap">
        {canViewFinancialReports(user) ? (
          <Button component={RouterLink} to="/insights/health" size="small">
            {t('nav.insightsHealth')}
          </Button>
        ) : null}
        <Button component={RouterLink} to="/insights/cashflow" size="small">
          {t('nav.insightsCashflow')}
        </Button>
        <Button component={RouterLink} to="/insights/alerts" size="small">
          {t('nav.insightsAlerts')}
        </Button>
        {canUseAiAssistant(user) ? (
          <Button component={RouterLink} to="/insights/assistant" size="small">
            {t('nav.insightsAssistant')}
          </Button>
        ) : null}
        {canViewFinancialReports(user) ? (
          <Button component={RouterLink} to="/attention" size="small">
            {t('nav.attention')}
          </Button>
        ) : null}
      </Stack>

      {hasSummary ? (
        <>
          {data.stale ? (
            <Alert severity="warning">{t('insights.summaryStale', { date: data.summaryDate })}</Alert>
          ) : data.generatedAt ? (
            <Typography variant="caption" color="text.secondary">
              {t('insights.summaryAsOf', { time: formatDateTime(data.generatedAt) })}
            </Typography>
          ) : null}
          <Stack
            direction="row"
            spacing={2}
            useFlexGap
            flexWrap="wrap"
            sx={{ '& > *': { flex: '1 1 160px', minWidth: 160, maxWidth: 280 } }}
          >
            <KpiStat label={t('insights.salesToday')} value={kpis.salesTodayTotal ?? kpis.sales_today_total} money dense />
            <KpiStat label={t('insights.salesMtd')} value={kpis.salesMtdTotal ?? kpis.sales_mtd_total} money dense />
            <KpiStat label={t('insights.receivables')} value={kpis.receivables} money dense />
            <KpiStat label={t('insights.payables')} value={kpis.payables} money dense />
            <KpiStat label={t('insights.openAlerts')} value={openAlertCount} dense />
          </Stack>

          <Paper variant="outlined" sx={{ p: 2 }}>
            <Typography variant="body1">{mask(data.narrative)}</Typography>
          </Paper>
        </>
      ) : (
        <EmptyState
          title={t('insights.summaryNone')}
          description={canGenerate ? undefined : t('insights.summaryNoneAsk')}
          action={
            canGenerate ? (
              <Button variant="contained" onClick={() => refresh.mutate()} disabled={busy}>
                {t('insights.generateFirst')}
              </Button>
            ) : undefined
          }
        />
      )}

      <Typography variant="h6">{t('insights.topAlerts')}</Typography>
      {alerts.isLoading ? (
        <LoadingState />
      ) : alerts.isError ? (
        <ErrorState
          message={`${t('insights.alertsLoadFailed')} ${getErrorMessage(alerts.error)}`}
          error={alerts.error}
          onRetry={() => void alerts.refetch()}
        />
      ) : topAlerts.length === 0 ? (
        <EmptyState description={t('insights.noAlerts')} />
      ) : (
        <Stack spacing={1}>
          {topAlerts.map((a) => (
            <Paper key={a.id} variant="outlined" sx={{ p: 1.5 }}>
              <Stack direction="row" spacing={1} alignItems="center">
                <SeverityChip severity={a.severity} />
                <Typography variant="body2" sx={{ flex: 1 }}>
                  {mask(a.message)}
                </Typography>
                {a.ctaPath ? (
                  <Button component={RouterLink} to={a.ctaPath} size="small">
                    {t('sweep2.open')}
                  </Button>
                ) : null}
              </Stack>
            </Paper>
          ))}
          {(alerts.data?.length ?? 0) > topAlerts.length ? (
            <Button component={RouterLink} to="/insights/alerts" size="small" sx={{ alignSelf: 'flex-start' }}>
              {t('insights.openAlerts')}: {alerts.data!.length}
            </Button>
          ) : null}
        </Stack>
      )}

      <Typography variant="h6">{t('insights.growthHints')}</Typography>
      {hints.isError ? (
        <ErrorState
          message={`${t('insights.hintsLoadFailed')} ${getErrorMessage(hints.error)}`}
          error={hints.error}
          onRetry={() => void hints.refetch()}
        />
      ) : hints.isLoading ? (
        <LoadingState />
      ) : (hints.data ?? []).length === 0 ? (
        <EmptyState description={t('insights.hintsEmpty')} />
      ) : (
        <Stack direction="row" spacing={2} useFlexGap flexWrap="wrap">
          {(hints.data ?? []).slice(0, 4).map((h) => (
            <Card key={h.code} variant="outlined" sx={{ width: { xs: '100%', sm: 280 } }}>
              <CardActionArea component={RouterLink} to={h.ctaPath}>
                <CardContent>
                  <Typography variant="subtitle1" fontWeight={600}>
                    {h.title}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {h.message}
                  </Typography>
                </CardContent>
              </CardActionArea>
            </Card>
          ))}
        </Stack>
      )}
    </Stack>
  );
}
