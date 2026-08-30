import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardActionArea from '@mui/material/CardActionArea';
import CardContent from '@mui/material/CardContent';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { generateDailySummary, getDailySummary, listBusinessAlerts, listGrowthHints } from '@/api/resources';
import {
  DisclaimerBanner,
  KpiStat,
  PageHeader,
  SeverityChip,
} from '@/components/insights';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';

export function InsightsHubPage() {
  const qc = useQueryClient();
  const summary = useQuery({ queryKey: ['insights-summary'], queryFn: () => getDailySummary() });
  const alerts = useQuery({ queryKey: ['insights-alerts'], queryFn: () => listBusinessAlerts() });
  const hints = useQuery({ queryKey: ['insights-hints'], queryFn: () => listGrowthHints() });
  const refresh = useMutation({
    mutationFn: () => generateDailySummary(),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['insights-summary'] });
      void qc.invalidateQueries({ queryKey: ['insights-alerts'] });
    },
  });

  if (summary.isLoading) return <LoadingState />;
  if (summary.isError) {
    return <ErrorState message={getErrorMessage(summary.error)} error={summary.error} onRetry={() => void summary.refetch()} />;
  }

  const kpis = summary.data!.kpis ?? {};
  const topAlerts = (alerts.data ?? []).slice(0, 5);

  return (
    <Stack spacing={2}>
      <PageHeader
        title={t('nav.insights')}
        subtitle={t('insights.todaySummary')}
        actions={
          <Button variant="outlined" onClick={() => refresh.mutate()} disabled={refresh.isPending}>
            {t('insights.generate')}
          </Button>
        }
      />
      <DisclaimerBanner>{t('insights.disclaimer')}</DisclaimerBanner>

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} useFlexGap flexWrap="wrap">
        <Button component={RouterLink} to="/insights/health" size="small">
          {t('nav.insightsHealth')}
        </Button>
        <Button component={RouterLink} to="/insights/cashflow" size="small">
          {t('nav.insightsCashflow')}
        </Button>
        <Button component={RouterLink} to="/insights/alerts" size="small">
          {t('nav.insightsAlerts')}
        </Button>
        <Button component={RouterLink} to="/insights/assistant" size="small">
          {t('nav.insightsAssistant')}
        </Button>
      </Stack>

      <Stack
        direction="row"
        spacing={2}
        useFlexGap
        flexWrap="wrap"
        sx={{ '& > *': { flex: '1 1 160px', minWidth: 160, maxWidth: 280 } }}
      >
        <KpiStat label="Sales today" value={kpis.salesTodayTotal ?? kpis.sales_today_total} money dense />
        <KpiStat label="Sales MTD" value={kpis.salesMtdTotal ?? kpis.sales_mtd_total} money dense />
        <KpiStat label="Receivables" value={kpis.receivables} money dense />
        <KpiStat label="Payables" value={kpis.payables} money dense />
        <KpiStat label={t('insights.openAlerts')} value={kpis.openAlerts ?? kpis.open_alerts ?? 0} dense />
      </Stack>

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography variant="body1">{summary.data!.narrative}</Typography>
      </Paper>

      <Typography variant="h6">{t('insights.topAlerts')}</Typography>
      {alerts.isLoading ? (
        <LoadingState />
      ) : topAlerts.length === 0 ? (
        <EmptyState description={t('insights.noAlerts')} />
      ) : (
        <Stack spacing={1}>
          {topAlerts.map((a) => (
            <Paper key={a.id} variant="outlined" sx={{ p: 1.5 }}>
              <Stack direction="row" spacing={1} alignItems="center">
                <SeverityChip severity={a.severity} />
                <Typography variant="body2" sx={{ flex: 1 }}>
                  {a.message}
                </Typography>
                {a.ctaPath ? (
                  <Button component={RouterLink} to={a.ctaPath} size="small">
                    Open
                  </Button>
                ) : null}
              </Stack>
            </Paper>
          ))}
        </Stack>
      )}

      <Typography variant="h6">{t('insights.growthHints')}</Typography>
      <Stack direction="row" spacing={2} useFlexGap flexWrap="wrap">
        {(hints.data ?? []).slice(0, 4).map((h) => (
          <Card key={h.code} variant="outlined" sx={{ width: 280 }}>
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
    </Stack>
  );
}
