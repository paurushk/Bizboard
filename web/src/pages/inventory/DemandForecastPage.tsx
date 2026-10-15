import Paper from '@mui/material/Paper';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Button from '@mui/material/Button';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { getDemandForecast } from '@/api/osPlan';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { PageTitle } from '@/contextHelp';
import { t, useLocale } from '@/i18n';
import { enumLabel } from '@/utils/enumLabels';

export function DemandForecastPage() {
  useLocale();
  const forecast = useQuery({ queryKey: ['demand-forecast'], queryFn: getDemandForecast });
  const rows = forecast.data?.rows ?? [];
  return (
    <div>
      <PageTitle>{t('nav.demandForecast')}</PageTitle>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>{t('osPlan.forecastHelp')}</Typography>
      <Button component={RouterLink} to="/inventory/purchase-planning" size="small" sx={{ mb: 2 }}>
        {t('osPlan.openPlanning')}
      </Button>
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
                <TableCell align="right">{t('common.actions')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.productId}>
                  <TableCell>{row.productName}</TableCell>
                  <TableCell align="right">{row.soldQty}</TableCell>
                  <TableCell align="right">{row.dailyRate}</TableCell>
                  <TableCell>
                    {enumLabel('forecastMethod', row.method)}
                    {row.windowDays != null ? ` · ${row.windowDays}` : ''}
                  </TableCell>
                  <TableCell align="right">
                    <Button
                      size="small"
                      component={RouterLink}
                      aria-label={t('osPlan.planPurchaseFor', { name: row.productName })}
                      // Suggest a month of cover; the order screen lets them change it.
                      to={`/purchases/orders/new?product=${row.productId}&qty=${Math.max(1, Math.ceil(Number(row.dailyRate || 0) * 30))}`}
                    >
                      {t('osPlan.planPurchase')}
                    </Button>
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
