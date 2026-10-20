import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardActionArea from '@mui/material/CardActionArea';
import CardContent from '@mui/material/CardContent';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { getBusinessHealth, getBusinessHealthHistory, listGrowthHints } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import {
  DisclaimerBanner,
  FactorBreakdown,
  KpiStat,
  PageHeader,
} from '@/components/insights';
import { useAiConsentOn } from '@/components/insights/AiConsentGate';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';
import { formatMoney } from '@/utils/money';
import { canViewAiInsights } from '@/utils/permissions';

export function InsightsHealthPage() {
  const { user } = useAuth();
  const consentOn = useAiConsentOn();
  // The score is deterministic (no AI), so it never waits on AI consent. Hints are an AI-gated
  // surface and are only requested for people who may see them.
  const hintsAllowed = consentOn && canViewAiInsights(user);
  const health = useQuery({ queryKey: ['insights-health'], queryFn: getBusinessHealth });
  const history = useQuery({ queryKey: ['insights-health-history'], queryFn: getBusinessHealthHistory });
  const hints = useQuery({ queryKey: ['insights-hints'], queryFn: listGrowthHints, enabled: hintsAllowed });

  if (health.isLoading) return <LoadingState />;
  if (health.isError) {
    return <ErrorState message={getErrorMessage(health.error)} error={health.error} onRetry={() => void health.refetch()} />;
  }

  const data = health.data!;
  const hist = (history.data ?? []).slice().reverse();
  const withheld = data.gradeWithheld === true;
  const first = hist[0];
  const last = hist[hist.length - 1];
  const pct = data.mtdChangePercent;

  return (
    <Stack spacing={2}>
      <PageHeader title={t('nav.insightsHealth')} subtitle={t('insights.score')} />
      <DisclaimerBanner>{t('honesty.insightsNotBooks')}</DisclaimerBanner>
      <DisclaimerBanner>{t('insights.disclaimer')}</DisclaimerBanner>
      {data.limitedData ? (
        <DisclaimerBanner severity="warning">{t('insights.limitedData')}</DisclaimerBanner>
      ) : null}

      <Stack direction="row" spacing={2} useFlexGap flexWrap="wrap">
        <Box sx={{ minWidth: 160 }}>
          <KpiStat
            label={t('insights.score')}
            value={withheld ? '—' : data.score}
            limitedData={data.limitedData}
            deltaLabel={withheld ? t('insights.gradeWithheld') : null}
          />
        </Box>
        <Box sx={{ minWidth: 120 }}>
          <KpiStat label={t('insights.grade')} value={withheld ? '—' : data.grade} />
        </Box>
        <Box sx={{ minWidth: 160 }}>
          <KpiStat
            label={t('insights.mtdVsPrior')}
            value={data.mtdSales}
            money
            deltaLabel={
              pct != null
                ? t('insights.mtdChange', { pct })
                : t('insights.sameDaysLastMonth', { amount: formatMoney(data.priorMonthSales ?? 0) })
            }
          />
        </Box>
      </Stack>

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography variant="h6" sx={{ mb: 2 }}>
          {t('sweep2.factorBreakdown')}
        </Typography>
        <FactorBreakdown factors={data.factors ?? []} />
      </Paper>

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography variant="h6" sx={{ mb: 1 }}>
          {t('sweep2.scoreHistory')}
        </Typography>
        {hist.length > 1 && first && last ? (
          <>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              {t('insights.historySummary', {
                first: String(first.score),
                firstDate: first.asOf,
                last: String(last.score),
                lastDate: last.asOf,
              })}
            </Typography>
            <Stack
              component="ol"
              direction="row"
              spacing={0.5}
              alignItems="flex-end"
              sx={{ height: 80, m: 0, p: 0, listStyle: 'none' }}
            >
              {hist.map((h) => {
                // F3-070: clamp — the score feeds a % height in an 80px row.
                const score = Math.min(100, Math.max(0, Number(h.score) || 0));
                return (
                  <Box
                    component="li"
                    key={h.id}
                    tabIndex={0}
                    aria-label={`${h.asOf}: ${h.score}`}
                    title={`${h.asOf}: ${h.score}`}
                    sx={{
                      flex: 1,
                      bgcolor: 'primary.main',
                      opacity: h.limitedData ? 0.35 : 0.75,
                      height: `${Math.max(8, score)}%`, // min 8% so a 0 is still visible
                      borderRadius: 0.5,
                      minWidth: 4,
                      '&:focus-visible': { outline: '2px solid', outlineColor: 'text.primary', opacity: 1 },
                    }}
                  />
                );
              })}
            </Stack>
          </>
        ) : (
          <Typography variant="body2" color="text.secondary">
            {t('insights.historyEmpty')}
          </Typography>
        )}
      </Paper>

      {hintsAllowed ? (
        <>
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
              {(hints.data ?? []).map((h) => (
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
        </>
      ) : null}
    </Stack>
  );
}
