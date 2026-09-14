import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { listCollectionRisk } from '@/api/resources';
import { CreditHoldChip } from '@/components/CreditHoldChip';
import { t } from '@/i18n';
import { formatMoney } from '@/utils/money';
import { isCollectionHoldStatus } from '@/utils/collectionHold';

/**
 * QOS-0038: a proactive dashboard nudge for the P1 "who owes me money"
 * motive — surfaces customers whose outstanding has aged past 30 days
 * without the owner having to open the receivables report first.
 */
export function CollectionAttentionCard() {
  const query = useQuery({
    queryKey: ['collection-risk'],
    queryFn: listCollectionRisk,
    retry: false,
  });

  if (query.isLoading || query.isError || !query.data) return null;

  const overdueRows = query.data.filter((row) => {
    const bucket31_60 = Number(row.ageing?.['31_60'] ?? 0);
    const bucket61_90 = Number(row.ageing?.['61_90'] ?? 0);
    const bucket90plus = Number(row.ageing?.['90_plus'] ?? 0);
    return bucket31_60 + bucket61_90 + bucket90plus > 0;
  });

  if (overdueRows.length === 0) {
    return null;
  }

  const total = overdueRows.reduce((sum, row) => sum + Number(row.overdueAmount || 0), 0);
  const top = [...overdueRows]
    .sort((a, b) => Number(b.overdueAmount || 0) - Number(a.overdueAmount || 0))
    .slice(0, 5);

  return (
    <Paper variant="outlined" sx={{ p: 2, borderColor: 'warning.main' }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
        <Typography variant="h6">{t('dashboard.collectionAttentionTitle')}</Typography>
        <Button component={RouterLink} to="/sales/customers" size="small">
          {t('dashboard.collectionAttentionViewAll')}
        </Button>
      </Stack>
      <Typography variant="body2" sx={{ mb: 1.5 }}>
        {t('dashboard.collectionAttentionLine', {
          count: overdueRows.length,
          amount: formatMoney(total),
        })}
      </Typography>
      <Stack spacing={0.75}>
        {top.map((row) => (
          <Stack
            key={row.customerId}
            direction="row"
            justifyContent="space-between"
            component={RouterLink}
            to={`/reports/customer-ledger?customer=${row.customerId}`}
            sx={{ color: 'text.primary', textDecoration: 'none', '&:hover': { textDecoration: 'underline' } }}
          >
            <Stack direction="row" spacing={0.75} alignItems="center" sx={{ minWidth: 0, maxWidth: 280 }}>
              <Typography variant="body2" noWrap sx={{ maxWidth: 180 }}>
                {row.customerName ?? `#${row.customerId}`}
              </Typography>
              {isCollectionHoldStatus(row.status) ? <CreditHoldChip /> : null}
            </Stack>
            <Typography variant="body2" color="warning.main">
              {formatMoney(row.overdueAmount)}
            </Typography>
          </Stack>
        ))}
      </Stack>
    </Paper>
  );
}
