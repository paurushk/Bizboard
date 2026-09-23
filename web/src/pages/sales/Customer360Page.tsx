import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { getCustomer360 } from '@/api/osPlan';
import { ErrorState, LoadingState } from '@/components/PageState';
import { PageTitle } from '@/contextHelp';
import { t } from '@/i18n';
import { formatMoney } from '@/utils/money';

function agingAmount(aging: Record<string, string> | null | undefined, keys: string[]): string | null {
  if (!aging) return null;
  for (const key of keys) {
    if (aging[key] != null && aging[key] !== '') return aging[key];
  }
  return null;
}

export function Customer360Page() {
  const { id } = useParams();
  const customerId = Number(id);
  const query = useQuery({
    queryKey: ['customer-360', customerId],
    queryFn: () => getCustomer360(customerId),
    enabled: Number.isFinite(customerId) && customerId > 0,
  });
  const body = query.data;
  return (
    <Stack spacing={2}>
      <PageTitle>{body?.name || t('nav.customer360')}</PageTitle>
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {body ? (
        <Stack spacing={2}>
          <Paper variant="outlined" sx={{ p: 2 }}>
            <Typography variant="subtitle2">{t('osPlan.salesPattern')}</Typography>
            <Typography variant="body2">
              {t('osPlan.invoiceCount', { count: body.sales.invoices })}
              {body.sales.amount != null ? ` · ${formatMoney(body.sales.amount)}` : ''}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {body.pattern || t('osPlan.noPattern')}
            </Typography>
            {body.recommendedNextStep ? (
              <Typography variant="body2">{body.recommendedNextStep}</Typography>
            ) : null}
          </Paper>
          {body.outstanding != null || body.profit != null ? (
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Typography variant="subtitle2">{t('osPlan.money')}</Typography>
              {body.outstanding != null ? (
                <Typography variant="body2">{t('portal.outstanding')}: {formatMoney(body.outstanding)}</Typography>
              ) : null}
              {body.profit?.totals ? (
                <Typography variant="body2">
                  {t('osPlan.profit')}: {formatMoney(body.profit.totals.margin ?? 0)}
                </Typography>
              ) : null}
              {body.aging ? (
                <Stack spacing={0.5} sx={{ mt: 1 }}>
                  <Typography variant="body2">{t('osPlan.agingCurrent')}: {formatMoney(agingAmount(body.aging, ['current']) ?? 0)}</Typography>
                  <Typography variant="body2">{t('osPlan.aging130')}: {formatMoney(agingAmount(body.aging, ['130', '1_30']) ?? 0)}</Typography>
                  <Typography variant="body2">{t('osPlan.aging3160')}: {formatMoney(agingAmount(body.aging, ['3160', '31_60']) ?? 0)}</Typography>
                  <Typography variant="body2">{t('osPlan.aging6190')}: {formatMoney(agingAmount(body.aging, ['6190', '61_90']) ?? 0)}</Typography>
                  <Typography variant="body2">{t('osPlan.aging90')}: {formatMoney(agingAmount(body.aging, ['90Plus', '90_plus']) ?? 0)}</Typography>
                </Stack>
              ) : null}
            </Paper>
          ) : null}
          <Paper variant="outlined" sx={{ p: 2 }}>
            <Typography variant="subtitle2">{t('osPlan.products')}</Typography>
            <Typography variant="body2">
              {body.products.length ? body.products.join(', ') : t('osPlan.noProducts')}
            </Typography>
          </Paper>
        </Stack>
      ) : null}
    </Stack>
  );
}
