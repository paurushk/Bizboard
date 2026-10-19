import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Divider from '@mui/material/Divider';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { contracts } from '@/api/care';
import { ErrorState, ListSkeleton } from '@/components/PageState';
import { useAuth } from '@/auth/AuthContext';
import { t } from '@/i18n';
import { formatDay } from '@/care/format';
import { Field } from '@/care/kit';
import { enumLabel } from '@/utils/enumLabels';
import { formatMoney } from '@/utils/money';

/** A one-page, printable certificate for a warranty, AMC or other contract (CON-12). */
export function ContractCertificatePage() {
  const { id } = useParams();
  const contractId = Number(id);
  const { user } = useAuth();
  const timeline = useQuery({ queryKey: ['contracts', 'timeline', contractId], queryFn: () => contracts.timeline(contractId) });
  if (timeline.isLoading) return <ListSkeleton rows={4} />;
  if (timeline.isError || !timeline.data) {
    return <ErrorState message={getErrorMessage(timeline.error)} error={timeline.error} onRetry={() => void timeline.refetch()} />;
  }
  const row = timeline.data.contract;
  return (
    <Box sx={{ maxWidth: 760, mx: 'auto', p: { xs: 1, sm: 3 }, '@media print': { p: 0, maxWidth: 'none' } }}>
      <Stack direction="row" justifyContent="flex-end" sx={{ mb: 2, '@media print': { display: 'none' } }}>
        <Button variant="contained" onClick={() => window.print()}>{t('care.print.print')}</Button>
      </Stack>
      <Typography variant="overline" color="text.secondary">{user?.company?.name ?? ''}</Typography>
      <Typography variant="h4" component="h1" gutterBottom>
        {t('care.contracts.certificateTitle', { type: enumLabel('contractType', row.contractType) })}
      </Typography>
      <Typography variant="h6" component="p">{row.number}</Typography>
      <Divider sx={{ my: 2 }} />
      <Stack spacing={2}>
        <Field label={t('growth.customer')}>{row.customerName}</Field>
        <Field label={t('care.contracts.col.products')}>{row.productNames.join(', ')}</Field>
        <Stack direction="row" spacing={4}>
          <Field label={t('growth.startDate')}>{formatDay(row.startDate)}</Field>
          <Field label={t('growth.endDate')}>{formatDay(row.endDate)}</Field>
          <Field label={t('growth.value')}>{row.value ? formatMoney(row.value) : ''}</Field>
        </Stack>
        {row.notes ? <Field label={t('growth.notes')}><Box sx={{ whiteSpace: 'pre-wrap' }}>{row.notes}</Box></Field> : null}
        {timeline.data.renewals.length ? (
          <Box>
            <Typography variant="caption" color="text.secondary">{t('care.contracts.renewals')}</Typography>
            {timeline.data.renewals.map((renewal) => (
              <Typography key={renewal.id} variant="body2">{formatDay(renewal.previousEndDate)} → {formatDay(renewal.newEndDate)}</Typography>
            ))}
          </Box>
        ) : null}
      </Stack>
      <Divider sx={{ my: 3 }} />
      <Typography variant="caption" color="text.secondary">{t('care.contracts.certificateFooter')}</Typography>
    </Box>
  );
}
