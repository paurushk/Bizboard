import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { apiClient, unwrapData } from '@/api/client';
import { getAccountingReport } from '@/api/resources';
import { t } from '@/i18n';
import { formatMoney, toNumber } from '@/utils/money';

type LedgerRow = { customerName?: string; outstanding?: string | number };

export function BooksCloseSection() {
  const trial = useQuery({
    queryKey: ['books-close', 'trial-balance'],
    queryFn: () => getAccountingReport('trial-balance'),
  });
  const profit = useQuery({
    queryKey: ['books-close', 'profit-and-loss'],
    queryFn: () => getAccountingReport('profit-and-loss'),
  });
  const ledger = useQuery({
    queryKey: ['books-close', 'customer-ledger'],
    queryFn: async () => {
      const { data } = await apiClient.get('/ledgers/customers/');
      const body = unwrapData<LedgerRow[] | { results?: LedgerRow[] }>(data);
      return Array.isArray(body) ? body : (body.results ?? []);
    },
  });
  const trialRow = (trial.data ?? {}) as { totalDebit?: string | number; totalCredit?: string | number; balanced?: boolean };
  const profitRow = (profit.data ?? {}) as { income?: string | number };
  const customers = ledger.data ?? [];
  const first = customers[0];
  const matched = trialRow.balanced === true;
  return (
    <Paper variant="outlined" sx={{ p: 2 }} data-testid="books-close">
      <Stack spacing={0.5}>
        <Typography variant="h6">{t('booksClose.title')}</Typography>
        <Typography>{t('booksClose.debit')}: {formatMoney(toNumber(trialRow.totalDebit))}</Typography>
        <Typography>{t('booksClose.credit')}: {formatMoney(toNumber(trialRow.totalCredit))}</Typography>
        <Typography data-testid="books-close-match">
          {matched ? t('booksClose.matched') : t('booksClose.notMatched')}
        </Typography>
        <Typography>{t('booksClose.income')}: {formatMoney(toNumber(profitRow.income))}</Typography>
        {first ? (
          <Typography>
            {t('booksClose.customerTotal')}: {first.customerName ?? ''} {formatMoney(toNumber(first.outstanding))}
          </Typography>
        ) : (
          <Typography>{t('booksClose.noCustomer')}</Typography>
        )}
      </Stack>
    </Paper>
  );
}
