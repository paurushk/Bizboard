import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { getAccountingReport } from '@/api/resources';
import { ErrorState, LoadingState } from '@/components/PageState';
import { getErrorMessage } from '@/api/client';
import { t } from '@/i18n';
import { formatMoney, toNumber } from '@/utils/money';

type HealthAlert = { code?: string; message?: string };

export function BooksCloseSection() {
  const trial = useQuery({
    queryKey: ['books-close', 'trial-balance'],
    queryFn: () => getAccountingReport('trial-balance'),
  });
  const profit = useQuery({
    queryKey: ['books-close', 'profit-and-loss'],
    queryFn: () => getAccountingReport('profit-and-loss'),
  });
  const health = useQuery({
    queryKey: ['books-close', 'books-health'],
    queryFn: () => getAccountingReport('books-health'),
  });
  const trialRow = (trial.data ?? {}) as { totalDebit?: string | number; totalCredit?: string | number; balanced?: boolean };
  const profitRow = (profit.data ?? {}) as { income?: string | number };
  const healthRow = (health.data ?? {}) as { ar?: { gl?: string | number }; alerts?: HealthAlert[] };
  const docsGl = (healthRow.alerts ?? []).filter((alert) => String(alert.code ?? '').startsWith('DOCS_GL_'));
  const matched = trialRow.balanced === true;
  const loading = trial.isLoading || profit.isLoading || health.isLoading;
  const failed = trial.error ?? profit.error ?? health.error;
  // Until the books have loaded, say nothing about whether they match.
  if (loading) return <LoadingState />;
  if (failed) {
    return (
      <ErrorState
        message={getErrorMessage(failed)}
        error={failed}
        onRetry={() => {
          void trial.refetch();
          void profit.refetch();
          void health.refetch();
        }}
      />
    );
  }
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
        <Typography data-testid="books-close-ar">
          {t('booksClose.arControl')}: {formatMoney(toNumber(healthRow.ar?.gl))}
        </Typography>
        {docsGl.length ? (
          <Typography data-testid="books-close-docs-gl">{t('booksClose.docsGl')}</Typography>
        ) : null}
      </Stack>
    </Paper>
  );
}
