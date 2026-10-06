import Paper from '@mui/material/Paper';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { getDemandForecast } from '@/api/osPlan';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { PageTitle } from '@/contextHelp';
import { t, useLocale } from '@/i18n';

export function DemandForecastPage() {
  useLocale();
  const forecast = useQuery({ queryKey: ['demand-forecast'], queryFn: getDemandForecast });
  const rows = forecast.data?.rows ?? [];
  return (
    <div>
      <PageTitle>{t('nav.demandForecast')}</PageTitle>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>{t('osPlan.forecastHelp')}</Typography>
      {forecast.isLoading ? <LoadingState /> : null}
      {forecast.isError ? (
        <ErrorState message={getErrorMessage(forecast.error)} error={forecast.error} onRetry={() => void forecast.refetch()} />
      ) : null}
      {!forecast.isLoading && !forecast.isError && rows.length === 0 ? (
        <EmptyState description={t('osPlan.forecastEmpty')} />
      ) : null}
      {rows.length > 0 ? (
        <Paper variant="outlined">
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('common.product')}</TableCell>
                <TableCell align="right">{t('osPlan.soldQty')}</TableCell>
                <TableCell align="right">{t('osPlan.dailyRate')}</TableCell>
                <TableCell>{t('osPlan.method')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.productId}>
                  <TableCell>{row.productName}</TableCell>
                  <TableCell align="right">{row.soldQty}</TableCell>
                  <TableCell align="right">{row.dailyRate}</TableCell>
                  <TableCell>
                    {row.method === 'trailing_mean' ? t('osPlan.trailingMean') : row.method}
                    {row.windowDays != null ? ` · ${row.windowDays}` : ''}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}
    </div>
  );
}
