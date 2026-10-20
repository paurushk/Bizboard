import Accordion from '@mui/material/Accordion';
import AccordionDetails from '@mui/material/AccordionDetails';
import AccordionSummary from '@mui/material/AccordionSummary';
import Box from '@mui/material/Box';
import Link from '@mui/material/Link';
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
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { getCashflowForecast } from '@/api/resources';
import { DisclaimerBanner, MoneyText, PageHeader, useMaskedText } from '@/components/insights';
import { ErrorState, LoadingState } from '@/components/PageState';
import { AiConsentOffScreen, useAiConsentOn } from '@/components/insights/AiConsentGate';
import { t } from '@/i18n';
import { formatMoney, toNumber } from '@/utils/money';

const HORIZONS = [7, 14, 30, 90];

export function InsightsCashflowPage() {
  const mask = useMaskedText();
  const consentOn = useAiConsentOn();
  const [horizon, setHorizon] = useState(14);
  const query = useQuery({
    queryKey: ['insights-cashflow', horizon],
    queryFn: () => getCashflowForecast(horizon),
    enabled: consentOn,
  });

  if (!consentOn) return <AiConsentOffScreen title={t('nav.insightsCashflow')} />;
  if (query.isLoading) return <LoadingState />;
  if (query.isError) {
    return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  }

  const data = query.data!;
  const meta = data.meta ?? {};
  const series = data.series ?? [];
  const absolute = data.mode === 'absolute';
  // The scale covers the bars and the scenario range, so nothing is clipped.
  const maxAbs = Math.max(
    ...series.flatMap((p) => [
      Math.abs(toNumber(p.endingCash)),
      Math.abs(toNumber(p.low)),
      Math.abs(toNumber(p.high)),
    ]),
    1,
  );
  // Signed position: 0 sits on the mid-line, positive values rise above it, negative fall below it.
  const pos = (v: number) => 50 + (v / maxAbs) * 50;
  const lowest = series.length
    ? series.reduce((a, b) => (toNumber(b.endingCash) < toNumber(a.endingCash) ? b : a))
    : null;
  const overdueAp = toNumber(meta.overduePayables) + toNumber(meta.undatedPayables);
  const chartLabel = lowest
    ? mask(t(absolute ? 'insights.lowestCash' : 'insights.lowestNet', {
        amount: formatMoney(lowest.endingCash),
        date: lowest.date,
      }))
    : '';

  return (
    <Stack spacing={2}>
      <PageHeader
        title={t('nav.insightsCashflow')}
        controls={
          <TextField
            select
            size="small"
            label={t('insights.horizon')}
            value={horizon}
            onChange={(e) => setHorizon(Number(e.target.value))}
            sx={{ minWidth: 120 }}
          >
            {HORIZONS.map((d) => (
              <MenuItem key={d} value={d}>
                {d}
              </MenuItem>
            ))}
          </TextField>
        }
      />
      <DisclaimerBanner severity="warning">{meta.disclaimer || t('insights.cashflowDisclaimer')}</DisclaimerBanner>
      <DisclaimerBanner>{t('honesty.insightsNotBooks')}</DisclaimerBanner>
      <Typography variant="body2" color="text.secondary">
        {t('insights.forecastNote')}
      </Typography>

      {chartLabel ? (
        <Typography variant="h6" component="p">
          {chartLabel}
        </Typography>
      ) : null}
      {absolute ? (
        meta.startingCash && meta.baselineAsOf ? (
          <Typography variant="body2" color="text.secondary">
            {t('insights.startingCash', { amount: formatMoney(meta.startingCash), date: meta.baselineAsOf })}
          </Typography>
        ) : null
      ) : (
        <Typography variant="body2" color="text.secondary">
          {t('insights.relativeNote')}{' '}
          <Link component={RouterLink} to="/settings/ai">
            {t('insights.setOpening')}
          </Link>
        </Typography>
      )}
      {overdueAp > 0 ? (
        <Typography variant="body2" color="text.secondary">
          {t('insights.overdueIncluded', { amount: formatMoney(overdueAp) })}
        </Typography>
      ) : null}
      {meta.excluded && meta.excluded.length > 0 ? (
        <Typography variant="body2" color="text.secondary">
          {t('insights.notIncluded', { items: meta.excluded.join(', ') })}
        </Typography>
      ) : null}
      <Typography variant="body2" color="text.secondary">
        {t('insights.scenarioNote')}
      </Typography>

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography variant="subtitle2" sx={{ mb: 1 }}>
          {t('insights.chartTitle')}
        </Typography>
        {/* F3-058: signed bars around a real zero line, with shape and hatch (not colour alone)
            marking a shortfall so it reads in greyscale and print. The scenario range is drawn
            from its own signed low and high. */}
        <Box role="img" aria-label={chartLabel || t('nav.insightsCashflow')} sx={{ position: 'relative', height: 160, px: 0.5 }}>
          <Box
            aria-hidden
            sx={{
              position: 'absolute',
              left: 0,
              right: 0,
              top: '50%',
              borderTop: '1px dashed',
              borderColor: 'divider',
              zIndex: 2,
            }}
          />
          <Stack direction="row" spacing={0.5} sx={{ height: '100%' }}>
            {series.map((p) => {
              const v = toNumber(p.endingCash);
              const lo = toNumber(p.low);
              const hi = toNumber(p.high);
              const negative = v < 0;
              const bandBottom = Math.min(pos(lo), pos(hi));
              const bandHeight = Math.abs(pos(hi) - pos(lo));
              const barHeight = Math.max(1, Math.abs(pos(v) - 50));
              return (
                <Box
                  key={p.date}
                  title={mask(`${p.date}: ${formatMoney(v)} (${formatMoney(lo)} to ${formatMoney(hi)})`)}
                  sx={{ flex: 1, position: 'relative', height: '100%', minWidth: 4 }}
                >
                  <Box
                    aria-hidden
                    sx={{
                      position: 'absolute',
                      left: '15%',
                      width: '70%',
                      bottom: `${bandBottom}%`,
                      height: `${bandHeight}%`,
                      bgcolor: 'action.selected',
                      opacity: 0.45,
                      borderRadius: 0.5,
                    }}
                  />
                  <Box
                    aria-hidden
                    sx={{
                      position: 'absolute',
                      left: '20%',
                      width: '60%',
                      height: `${barHeight}%`,
                      bottom: negative ? `${pos(v)}%` : '50%',
                      bgcolor: negative ? 'error.main' : 'success.main',
                      backgroundImage: negative
                        ? 'repeating-linear-gradient(45deg, rgba(255,255,255,0.55) 0 2px, transparent 2px 5px)'
                        : 'none',
                      borderRadius: 0.5,
                      zIndex: 1,
                    }}
                  />
                </Box>
              );
            })}
          </Stack>
        </Box>
      </Paper>

      <Accordion variant="outlined" disableGutters>
        <AccordionSummary>
          <Typography variant="subtitle2">{t('insights.dailyDetail')}</Typography>
        </AccordionSummary>
        <AccordionDetails sx={{ p: 0 }}>
          <Box tabIndex={0} role="region" aria-label={t('common.scrollableTable')} sx={{ overflow: 'auto' }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>{t('sweep2.date')}</TableCell>
                  <TableCell align="right">{t('sweep2.inflow')}</TableCell>
                  <TableCell align="right">{t('sweep2.outflow')}</TableCell>
                  <TableCell align="right">{t('sweep2.net')}</TableCell>
                  <TableCell align="right">{t('sweep2.cumulative')}</TableCell>
                  <TableCell align="right">{t('sweep2.low')}</TableCell>
                  <TableCell align="right">{t('sweep2.high')}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {series.map((p) => (
                  <TableRow key={p.date} hover>
                    <TableCell>{p.date}</TableCell>
                    <TableCell align="right">
                      <MoneyText value={p.inflow} />
                    </TableCell>
                    <TableCell align="right">
                      <MoneyText value={p.outflow} />
                    </TableCell>
                    <TableCell align="right">
                      <MoneyText value={p.net} />
                    </TableCell>
                    <TableCell align="right">
                      {/* BB-000751: ending cash, so the row agrees with the range beside it. */}
                      <MoneyText value={p.endingCash} />
                    </TableCell>
                    <TableCell align="right">
                      <MoneyText value={p.low} />
                    </TableCell>
                    <TableCell align="right">
                      <MoneyText value={p.high} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Box>
        </AccordionDetails>
      </Accordion>
    </Stack>
  );
}
