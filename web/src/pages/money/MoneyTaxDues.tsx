import Chip from '@mui/material/Chip';
import Link from '@mui/material/Link';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { getMoneyStatutory } from '@/api/resources';
import { ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';
import { moneyLinkHref } from '@/lib/moneyLinks';
import { formatMoney } from '@/utils/money';

/** TDS deducted and the GST estimate, with due dates. Amounts are estimates for the CA to confirm. */
export function MoneyTaxDues() {
  const query = useQuery({ queryKey: ['money-statutory'], queryFn: getMoneyStatutory });
  const data = query.data;
  return (
    <Paper variant="outlined" component="section" aria-labelledby="money-tax-title" sx={{ p: 2 }}>
      <Typography id="money-tax-title" variant="h6" component="h2">
        {t('money.tax.title')}
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
        {t('money.tax.note')}
      </Typography>
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {data ? (
        <Stack spacing={1} sx={{ mt: 1.5 }}>
          {data.items.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              {t('money.tax.empty')}
            </Typography>
          ) : (
            <Table size="small" aria-label={t('money.tax.title')}>
              <TableHead>
                <TableRow>
                  <TableCell>{t('money.tax.what')}</TableCell>
                  <TableCell>{t('money.tax.period')}</TableCell>
                  <TableCell>{t('money.tax.dueBy')}</TableCell>
                  <TableCell align="right">{t('common.amount')}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {data.items.map((item) => (
                  <TableRow key={`${item.kind}-${item.period}`}>
                    <TableCell>
                      <Link component={RouterLink} to={moneyLinkHref(item.link)}>
                        {item.kind === 'tds_payable' ? t('money.tax.tds') : t('money.tax.gst')}
                      </Link>
                      {item.estimate ? (
                        <Chip size="small" variant="outlined" label={t('money.tax.estimate')} sx={{ ml: 1 }} />
                      ) : null}
                    </TableCell>
                    <TableCell>{item.period}</TableCell>
                    <TableCell>{item.dueDate}</TableCell>
                    <TableCell align="right">
                      {item.amount === null ? t('money.unavailable') : formatMoney(item.amount)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
          {data.unavailable.length > 0 ? (
            <Typography variant="caption" color="text.secondary">
              {t('money.tax.unavailable')}
            </Typography>
          ) : null}
        </Stack>
      ) : null}
    </Paper>
  );
}
