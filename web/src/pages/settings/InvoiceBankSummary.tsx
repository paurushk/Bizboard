import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import * as api from '@/api/resources';
import { t } from '@/i18n';
import type { BankAccount } from '@/types/domain';

/**
 * SET-04: the bank and UPI details printed on bills now live on a Bank Account. The Company screen
 * only shows which one is used and links to where it is edited, so there is one place to change them.
 */
export function InvoiceBankSummary() {
  const accounts = useQuery({ queryKey: ['bank-accounts', 'all'], queryFn: api.listAllBankAccounts });
  const chosen = (accounts.data ?? []).find((a: BankAccount) => a.printOnInvoices && a.isActive !== false);
  return (
    <Stack spacing={1} id="bank-section">
      <Typography variant="h6" fontWeight={600}>
        {t('banks.summaryTitle')}
      </Typography>
      <Typography variant="body2" color="text.secondary">
        {t('banks.summaryHelp')}
      </Typography>
      {accounts.isError ? (
        <Alert severity="warning">{t('banks.summaryUnavailable')}</Alert>
      ) : chosen ? (
        <Stack spacing={0.25}>
          <Typography>{chosen.name}</Typography>
          <Typography variant="body2" color="text.secondary">
            {[chosen.accountNumberMasked, chosen.ifsc, chosen.upiId].filter(Boolean).join(' · ')}
          </Typography>
        </Stack>
      ) : accounts.isLoading ? null : (
        <Alert severity="info">{t('banks.summaryNone')}</Alert>
      )}
      <Button component={RouterLink} to="/settings/bank-accounts" sx={{ alignSelf: 'flex-start' }}>
        {t('banks.summaryLink')}
      </Button>
    </Stack>
  );
}
