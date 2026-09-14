import Alert from '@mui/material/Alert';
import { useQuery } from '@tanstack/react-query';
import { getAccountingSettings } from '@/api/resources';
import { t } from '@/i18n';

export function AccountingBackfillBanner() {
  const query = useQuery({
    queryKey: ['accounting-settings'],
    queryFn: getAccountingSettings,
    staleTime: 30_000,
  });
  const data = (query.data ?? {}) as Record<string, unknown>;
  const needed = Boolean(data.accountingBackfillNeeded ?? data.accounting_backfill_needed);
  if (!needed) return null;
  return (
    <Alert severity="warning" sx={{ mb: 2 }}>
      {t('phase.accountingBackfillNeeded')}
    </Alert>
  );
}
