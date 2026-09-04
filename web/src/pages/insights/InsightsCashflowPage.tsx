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
import Box from '@mui/material/Box';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { getCashflowForecast } from '@/api/resources';
import { DisclaimerBanner, MoneyText, PageHeader } from '@/components/insights';
import { ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';
import { toNumber } from '@/utils/money';

export function InsightsCashflowPage() {
  const [horizon, setHorizon] = useState(14);
  const query = useQuery({
    queryKey: ['insights-cashflow', horizon],
    queryFn: () => getCashflowForecast(horizon),
  });

  if (query.isLoading) return <LoadingState />;
  if (query.isError) {
    return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  }

  const data = query.data!;
  const series = data.series ?? [];
  const maxAbs = Math.max(
    ...series.map((p) => Math.abs(toNumber(p.endingCash ?? p.cumulative))),
    1,
  );

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
            {[7, 14, 30].map((d) => (
              <MenuItem key={d} value={d}>
                {d}
              </MenuItem>
            ))}
          </TextField>
        }
      />
      <DisclaimerBanner severity="warning">{t('insights.cashflowDisclaimer')}</DisclaimerBanner>
      <Typography variant="body2" color="text.secondary">
        This is a forecast. Use the Cash Book for posted cash and bank actuals.
      </Typography>
      <Typography variant="body2" color="text.secondary">
        Mode: {data.mode} · model {data.modelVersion ?? 'v1'}
      </Typography>

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography variant="subtitle2" sx={{ mb: 1 }}>
          Ending cash / cumulative — bars above the line are positive (▲), below are a projected shortfall (▼)
        </Typography>
        {/* F3-058: draw around a real zero baseline instead of stacking every bar
            from the bottom on |value|, and encode the sign with shape + hatch
            (not colour alone) so a negative month reads in greyscale / print. */}
        <Box sx={{ position: 'relative', height: 160, px: 0.5 }}>
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
              const low = toNumber(p.low);
              const high = toNumber(p.high);
              const negative = v < 0;
              // half-height (0–50%) of the column, measured from the mid-line.
              const barHalf = Math.min(50, Math.max(2, (Math.abs(v) / maxAbs) * 50));
              const bandTopHalf = Math.min(50, (Math.abs(high) / maxAbs) * 50);
              const bandBotHalf = Math.min(50, (Math.abs(low) / maxAbs) * 50);
              return (
                <Box
                  key={p.date}
                  title={`${p.date}: ${v} [${low}–${high}]`}
                  sx={{ flex: 1, position: 'relative', height: '100%', minWidth: 4 }}
                >
                  {/* low–high uncertainty band, centred on the mid-line */}
                  <Box
                    aria-hidden
                    sx={{
                      position: 'absolute',
                      left: '15%',
                      width: '70%',
                      bottom: `calc(50% - ${bandBotHalf}%)`,
                      top: `calc(50% - ${bandTopHalf}%)`,
                      bgcolor: 'action.selected',
                      opacity: 0.4,
                      borderRadius: 0.5,
                    }}
                  />
                  <Box
                    sx={{
                      position: 'absolute',
                      left: '20%',
                      width: '60%',
                      height: `${barHalf}%`,
                      [negative ? 'top' : 'bottom']: '50%',
                      bgcolor: negative ? 'error.main' : 'success.main',
                      backgroundImage: negative
                        ? 'repeating-linear-gradient(45deg, rgba(255,255,255,0.55) 0 2px, transparent 2px 5px)'
                        : 'none',
                      borderRadius: 0.5,
                      zIndex: 1,
                    }}
                  />
                  <Typography
                    aria-hidden
                    sx={{
                      position: 'absolute',
                      left: 0,
                      right: 0,
                      textAlign: 'center',
                      fontSize: 10,
                      lineHeight: 1,
                      color: negative ? 'error.main' : 'success.main',
                      [negative ? 'bottom' : 'top']: 0,
                    }}
                  >
                    {negative ? '▼' : '▲'}
                  </Typography>
                </Box>
              );
            })}
          </Stack>
        </Box>
      </Paper>

      <Paper variant="outlined" sx={{ overflow: 'auto' }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Date</TableCell>
              <TableCell align="right">Inflow</TableCell>
              <TableCell align="right">Outflow</TableCell>
              <TableCell align="right">Net</TableCell>
              <TableCell align="right">Cumulative</TableCell>
              <TableCell align="right">Low</TableCell>
              <TableCell align="right">High</TableCell>
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
                  {/* BB-000751: show ending cash (opening balance + cumulative net), not the
                      raw net-only figure — the Low/High band beside it is derived from
                      ending cash, so showing the net-only value made the row internally
                      inconsistent (e.g. Cumulative ₹0 next to a ₹21k–29k band). */}
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
      </Paper>
    </Stack>
  );
}
