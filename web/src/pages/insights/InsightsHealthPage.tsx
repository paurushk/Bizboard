import Box from '@mui/material/Box';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import Card from '@mui/material/Card';
import CardActionArea from '@mui/material/CardActionArea';
import CardContent from '@mui/material/CardContent';
import { getErrorMessage } from '@/api/client';
import { getBusinessHealth, getBusinessHealthHistory, listGrowthHints } from '@/api/resources';
import {
  DisclaimerBanner,
  FactorBreakdown,
  KpiStat,
  PageHeader,
} from '@/components/insights';
import { ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';

export function InsightsHealthPage() {
  const health = useQuery({ queryKey: ['insights-health'], queryFn: getBusinessHealth });
  const history = useQuery({ queryKey: ['insights-health-history'], queryFn: getBusinessHealthHistory });
  const hints = useQuery({ queryKey: ['insights-hints'], queryFn: listGrowthHints });

  if (health.isLoading) return <LoadingState />;
  if (health.isError) {
    return <ErrorState message={getErrorMessage(health.error)} error={health.error} onRetry={() => void health.refetch()} />;
  }

  const data = health.data!;
  const hist = (history.data ?? []).slice().reverse();

  return (
    <Stack spacing={2}>
      <PageHeader title={t('nav.insightsHealth')} subtitle={t('insights.score')} />
      <DisclaimerBanner>{t('insights.disclaimer')}</DisclaimerBanner>
      {data.limitedData ? (
        <DisclaimerBanner severity="warning">{t('insights.limitedData')}</DisclaimerBanner>
      ) : null}

      <Stack direction="row" spacing={2} useFlexGap flexWrap="wrap">
        <Box sx={{ minWidth: 160 }}>
          <KpiStat label={t('insights.score')} value={data.score} limitedData={data.limitedData} />
        </Box>
        <Box sx={{ minWidth: 120 }}>
          <KpiStat label={t('insights.grade')} value={data.grade} />
        </Box>
        <Box sx={{ minWidth: 160 }}>
          <KpiStat
            label={t('insights.mtdVsPrior')}
            value={(data as { mtdSales?: string }).mtdSales}
            money
            deltaLabel={`Prior month: ${
              (data as { priorMonthSales?: string }).priorMonthSales ?? '—'
            }`}
          />
        </Box>
      </Stack>

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography variant="h6" sx={{ mb: 2 }}>
          Factor breakdown
        </Typography>
        <FactorBreakdown factors={data.factors ?? []} />
      </Paper>

      {hist.length > 1 ? (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Typography variant="h6" sx={{ mb: 1 }}>
            Score history
          </Typography>
          <Stack direction="row" spacing={0.5} alignItems="flex-end" sx={{ height: 80 }}>
            {hist.map((h) => {
              const score = Number(h.score);
              return (
                <Box
                  key={h.id}
                  title={`${h.asOf}: ${h.score}`}
                  sx={{
                    flex: 1,
                    bgcolor: 'primary.main',
                    opacity: 0.75,
                    height: `${Math.max(8, score)}%`,
                    borderRadius: 0.5,
                    minWidth: 4,
                  }}
                />
              );
            })}
          </Stack>
        </Paper>
      ) : null}

      <Typography variant="h6">{t('insights.growthHints')}</Typography>
      <Stack direction="row" spacing={2} useFlexGap flexWrap="wrap">
        {(hints.data ?? []).map((h) => (
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
