import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Divider from '@mui/material/Divider';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { jobs } from '@/api/care';
import { useAuth } from '@/auth/AuthContext';
import { ErrorState, ListSkeleton } from '@/components/PageState';
import { t } from '@/i18n';
import { formatStamp, plainNumber } from '@/care/format';
import { Field } from '@/care/kit';
import { enumLabel } from '@/utils/enumLabels';
import { formatMoney } from '@/utils/money';

/** The customer's drop-off copy of a job card (JOB-14): what was reported, what is planned, and the estimate. */
export function JobSlipPage() {
  const { id } = useParams();
  const jobId = Number(id);
  const { user } = useAuth();
  const detail = useQuery({ queryKey: ['jobs', 'detail', jobId], queryFn: () => jobs.get(jobId) });
  if (detail.isLoading) return <ListSkeleton rows={4} />;
  if (detail.isError || !detail.data) {
    return <ErrorState message={getErrorMessage(detail.error)} error={detail.error} onRetry={() => void detail.refetch()} />;
  }
  const job = detail.data;
  return (
    <Box sx={{ maxWidth: 760, mx: 'auto', p: { xs: 1, sm: 3 }, '@media print': { p: 0, maxWidth: 'none' } }}>
      <Stack direction="row" justifyContent="flex-end" sx={{ mb: 2, '@media print': { display: 'none' } }}>
        <Button variant="contained" onClick={() => window.print()}>{t('care.print.print')}</Button>
      </Stack>
      <Typography variant="overline" color="text.secondary">{user?.company?.name ?? ''}</Typography>
      <Typography variant="h4" component="h1" gutterBottom>{t('care.jobs.slipTitle')}</Typography>
      <Typography variant="h6" component="p">{job.number} · {enumLabel('jobStatus', job.status)}</Typography>
      <Divider sx={{ my: 2 }} />
      <Stack spacing={2}>
        <Stack direction="row" spacing={4} flexWrap="wrap" useFlexGap>
          <Field label={t('growth.customer')}>{job.customerName}</Field>
          <Field label={t('growth.registrationNo')}>{job.registrationNo}</Field>
          <Field label={t('growth.vehicleModel')}>{job.vehicleModel}</Field>
          <Field label={t('growth.odometer')}>{job.odometerReading ? plainNumber(job.odometerReading) : ''}</Field>
        </Stack>
        <Field label={t('growth.complaint')}><Box sx={{ whiteSpace: 'pre-wrap' }}>{job.complaint}</Box></Field>
        <Stack direction="row" spacing={4} flexWrap="wrap" useFlexGap>
          <Field label={t('care.jobs.technician')}>{job.technicianName}</Field>
          <Field label={t('care.jobs.col.booking')}>
            {job.serviceBayName ? `${job.serviceBayName} · ${formatStamp(job.scheduledStart)}` : ''}
          </Field>
        </Stack>
        <Table size="small" aria-label={t('care.jobs.estimate')}>
          <TableHead>
            <TableRow>
              <TableCell scope="col">{t('growth.product')}</TableCell>
              <TableCell scope="col" align="right">{t('growth.quantity')}</TableCell>
              <TableCell scope="col" align="right">{t('growth.unitPrice')}</TableCell>
              <TableCell scope="col" align="right">{t('care.jobs.amount')}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {(job.lines ?? []).map((line) => (
              <TableRow key={line.id}>
                <TableCell>{line.productName}</TableCell>
                <TableCell align="right">{plainNumber(line.quantity)}</TableCell>
                <TableCell align="right">{line.coveredByContract ? t('care.jobs.covered') : formatMoney(line.unitPrice)}</TableCell>
                <TableCell align="right">{formatMoney(Number(line.quantity) * Number(line.unitPrice))}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <Stack alignItems="flex-end">
          <Typography variant="body2">{t('care.jobs.subtotal')}: {formatMoney(job.subtotal)}</Typography>
          <Typography variant="body2">{t('care.jobs.gst')}: {formatMoney(job.gstTotal)}</Typography>
          <Typography variant="subtitle1" component="p">{t('care.jobs.total')}: {formatMoney(job.total)}</Typography>
        </Stack>
      </Stack>
      <Divider sx={{ my: 3 }} />
      <Typography variant="caption" color="text.secondary">{t('care.jobs.slipFooter')}</Typography>
    </Box>
  );
}
