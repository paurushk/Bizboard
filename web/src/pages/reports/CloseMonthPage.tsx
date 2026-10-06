import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { Link as RouterLink } from 'react-router-dom';
import { PageHeader } from '@/components/insights';
import { t } from '@/i18n';

/** One entry that links books close and GST close. Postings stay separate. */
export function CloseMonthPage() {
  return (
    <Stack spacing={1.5}>
      <PageHeader title={t('cog.closeMonth')} />
      <Typography>{t('cog.closeMonthDisclaimer')}</Typography>
      <Button component={RouterLink} to="/accounting/periods" variant="contained">{t('cog.rowBooksClose')}</Button>
      <Button component={RouterLink} to="/reports/gstr1" variant="outlined">{t('cog.rowGstClose')}</Button>
      <Button component={RouterLink} to="/reports/gstr3b" variant="text">{t('cog.rowGstClose')} 3B</Button>
    </Stack>
  );
}
