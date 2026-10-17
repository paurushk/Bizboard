import { useState } from 'react';
import Button from '@mui/material/Button';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
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
import { getErrorMessage } from '@/api/client';
import { getMoneyTimeline } from '@/api/resources';
import { ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';
import { formatMoney, toNumber } from '@/utils/money';
import { StatCard } from '@/pages/money/MoneyTiles';

const RANGES = [7, 30, 60, 90] as const;

/** Money expected in and due out, by due date. Not a forecast, and says so. */
export function MoneyOutlook() {
  const [days, setDays] = useState<number>(30);
  const [openDays, setOpenDays] = useState<Set<string>>(new Set());
  const query = useQuery({ queryKey: ['money-timeline', days], queryFn: () => getMoneyTimeline(days) });
  const data = query.data;

  return (
    <Paper variant="outlined" component="section" aria-labelledby="money-outlook-title" sx={{ p: 2 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" useFlexGap flexWrap="wrap" spacing={1}>
        <Typography id="money-outlook-title" variant="h6" component="h2">
          {t('money.outlook.title')}
        </Typography>
        <TextField
          select
          size="small"
          label={t('money.outlook.range')}
          value={days}
          onChange={(event) => setDays(Number(event.target.value))}
          sx={{ minWidth: 140 }}
        >
          {RANGES.map((range) => (
            <MenuItem key={range} value={range}>
              {t('money.outlook.nextDays', { count: range })}
            </MenuItem>
          ))}
        </TextField>
      </Stack>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
        {t('money.outlook.note')}
      </Typography>

      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {data ? (
        <Stack spacing={2} sx={{ mt: 2 }}>
          <Box display="grid" gridTemplateColumns={{ xs: '1fr 1fr', md: 'repeat(4, 1fr)' }} gap={1.5}>
            <StatCard label={t('money.outlook.opening')} value={data.openingCash} />
            <StatCard label={t('money.outlook.expectedIn')} value={data.inflow} tone="success" />
            <StatCard label={t('money.outlook.dueOut')} value={data.outflow} />
            <StatCard
              label={t('money.outlook.closing')}
              value={data.closingCash}
              tone={toNumber(data.lowestBalance) < 0 ? 'error' : undefined}
              note={
                toNumber(data.lowestBalance) < 0
                  ? t('money.outlook.dipsBelowZero', { amount: formatMoney(data.lowestBalance) })
                  : t('money.outlook.lowest', { amount: formatMoney(data.lowestBalance) })
              }
            />
          </Box>
          {toNumber(data.overdueNow.in) > 0 || toNumber(data.overdueNow.out) > 0 ? (
            <Alert severity="warning" variant="outlined">
              {t('money.outlook.overdueNow', {
                owedToYou: formatMoney(data.overdueNow.in),
                youOwe: formatMoney(data.overdueNow.out),
              })}
            </Alert>
          ) : null}
          {data.timeline.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              {t('money.outlook.empty', { count: data.days })}
            </Typography>
          ) : (
            <Box
              tabIndex={0}
              role="region"
              aria-label={`${t('common.scrollableTable')}: ${t('money.outlook.title')}`}
              sx={{ overflow: 'auto' }}
            >
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>{t('common.date')}</TableCell>
                    <TableCell>{t('money.outlook.what')}</TableCell>
                    <TableCell align="right">{t('money.outlook.in')}</TableCell>
                    <TableCell align="right">{t('money.outlook.out')}</TableCell>
                    <TableCell align="right">{t('money.outlook.balance')}</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {data.timeline.map((day) => (
                    <TableRow key={day.date}>
                      <TableCell sx={{ whiteSpace: 'nowrap', verticalAlign: 'top' }}>{day.date}</TableCell>
                      <TableCell>
                        {(openDays.has(day.date) ? day.items : day.items.slice(0, 4)).map((item, index) => (
                          <Typography key={index} variant="body2">
                            {item.side === 'in' ? '+' : '−'} {item.party}
                            {item.reference ? ` · ${item.reference}` : ''} · {formatMoney(item.amount)}
                            {item.promised ? ` · ${t('money.outlook.promised')}` : ''}
                            {item.estimate ? ` · ${t('money.outlook.estimate')}` : ''}
                          </Typography>
                        ))}
                        {day.items.length > 4 ? (
                          <Button
                            size="small"
                            sx={{ p: 0, minWidth: 0, textTransform: 'none' }}
                            aria-expanded={openDays.has(day.date)}
                            onClick={() =>
                              setOpenDays((current) => {
                                const next = new Set(current);
                                if (next.has(day.date)) next.delete(day.date);
                                else next.add(day.date);
                                return next;
                              })
                            }
                          >
                            {openDays.has(day.date)
                              ? t('money.outlook.showLess')
                              : t('money.outlook.showAll', { count: day.items.length })}
                          </Button>
                        ) : null}
                      </TableCell>
                      <TableCell align="right" sx={{ verticalAlign: 'top' }}>
                        {toNumber(day.inflow) > 0 ? formatMoney(day.inflow) : '—'}
                      </TableCell>
                      <TableCell align="right" sx={{ verticalAlign: 'top' }}>
                        {toNumber(day.outflow) > 0 ? formatMoney(day.outflow) : '—'}
                      </TableCell>
                      <TableCell
                        align="right"
                        sx={{ verticalAlign: 'top', color: toNumber(day.balance) < 0 ? 'error.main' : undefined }}
                      >
                        {formatMoney(day.balance)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Box>
          )}
          {toNumber(data.beyondHorizon.in) > 0 || toNumber(data.beyondHorizon.out) > 0 ? (
            <Typography variant="caption" color="text.secondary">
              {t('money.outlook.beyond', {
                count: data.days,
                owedToYou: formatMoney(data.beyondHorizon.in),
                youOwe: formatMoney(data.beyondHorizon.out),
              })}
            </Typography>
          ) : null}
        </Stack>
      ) : null}
    </Paper>
  );
}
