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
    return <ErrorState message={getErrorMessage(query.error)} onRetry={() => void query.refetch()} />;
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
          Ending cash / cumulative (band = low–high)
        </Typography>
        <Stack direction="row" spacing={0.5} alignItems="flex-end" sx={{ height: 140 }}>
          {series.map((p) => {
            const v = toNumber(p.endingCash);
            const low = toNumber(p.low);
            const high = toNumber(p.high);
            const h = Math.max(4, (Math.abs(v) / maxAbs) * 100);
            const bandTop = Math.max(4, (Math.abs(high) / maxAbs) * 100);
            const bandBot = Math.max(2, (Math.abs(low) / maxAbs) * 100);
            return (
              <Box
                key={p.date}
                title={`${p.date}: ${v} [${low}–${high}]`}
                sx={{
                  flex: 1,
                  position: 'relative',
                  height: '100%',
                  display: 'flex',
                  alignItems: 'flex-end',
                  minWidth: 3,
                }}
              >
                <Box
                  sx={{
                    position: 'absolute',
                    bottom: 0,
                    left: '20%',
                    width: '60%',
                    height: `${bandTop}%`,
                    bgcolor: 'action.selected',
                    borderRadius: 0.5,
                    opacity: 0.5,
                  }}
                />
                <Box
                  sx={{
                    position: 'absolute',
                    bottom: 0,
                    left: '20%',
                    width: '60%',
                    height: `${bandBot}%`,
                    bgcolor: 'background.paper',
                    borderRadius: 0.5,
                    opacity: 0.35,
                  }}
                />
                <Box
                  sx={{
                    width: '100%',
                    height: `${h}%`,
                    bgcolor: v >= 0 ? 'success.main' : 'error.main',
                    opacity: 0.9,
                    borderRadius: 0.5,
                    zIndex: 1,
                  }}
                />
              </Box>
            );
          })}
        </Stack>
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
