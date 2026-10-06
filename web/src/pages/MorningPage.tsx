import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { getCompany, listAttentionRows, listLowStock } from '@/api/resources';
import { ErrorState, LoadingState } from '@/components/PageState';
import { safeAppPath } from '@/utils/safeUrl';
import { PageHeader } from '@/components/insights';
import { t } from '@/i18n';

/** Morning list of attention, overdue, and low stock already on the dashboard. */
export function MorningPage() {
  const company = useQuery({ queryKey: ['company'], queryFn: getCompany });
  const attention = useQuery({ queryKey: ['attention-rows'], queryFn: () => listAttentionRows() });
  const low = useQuery({ queryKey: ['low-stock'], queryFn: listLowStock });
  const rows = attention.data ?? [];
  const overdue = rows.filter((row) => row.overdue);
  // "All quiet" is only true once both lists have loaded. While they load, or when one failed,
  // an empty list means nothing.
  const loading = attention.isLoading || low.isLoading;
  const failed = attention.isError ? attention : low.isError ? low : null;
  const quiet = !loading && !failed && rows.length === 0 && (low.data ?? []).length === 0;
  const emptyCompany = !company.isLoading && !company.data?.name;

  return (
    <Stack spacing={1.5}>
      <PageHeader title={t('cog.morningTitle')} />
      {loading ? <LoadingState /> : null}
      {failed ? (
        <ErrorState message={getErrorMessage(failed.error)} error={failed.error} onRetry={() => void failed.refetch()} />
      ) : null}
      {emptyCompany ? (
        <Button component={RouterLink} to="/setup" variant="contained">{t('cog.setupBlock')}</Button>
      ) : null}
      {quiet && !emptyCompany ? (
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          <Typography>{t('cog.morningQuiet')}</Typography>
          <Button component={RouterLink} to="/sales/new" variant="contained">{t('cog.newBill')}</Button>
          <Button component={RouterLink} to="/pos" variant="outlined">{t('cog.openPos')}</Button>
        </Stack>
      ) : null}
      <Button component={RouterLink} to="/attention" variant="text">{t('cog.dues')} ({overdue.length})</Button>
      {(low.data ?? []).slice(0, 8).map((row) => (
        <Typography key={`${row.product}-${row.warehouse ?? 0}`} variant="body2">
          {t('cog.lowStock')}: {row.productName} {String(row.available)}
        </Typography>
      ))}
      {rows.slice(0, 8).map((row) => (
        <Button key={row.dedupeKey} component={RouterLink} to={safeAppPath(row.actionHref, '/attention')} variant="text">
          {row.title || row.code}
        </Button>
      ))}
    </Stack>
  );
}
