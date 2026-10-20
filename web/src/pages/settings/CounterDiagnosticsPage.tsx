import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Chip from '@mui/material/Chip';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { PageHeader } from '@/components/insights';
import { ErrorState, LoadingState } from '@/components/PageState';
import { getShopFloorSummary, funnelCount, funnelReasons } from '@/lib/telemetry';
import { t, tOptional, useLocale } from '@/i18n';

/** Owner-only: how the counter's key journeys did over the last days. Moved off the dashboard. */
export function CounterDiagnosticsPage() {
  useLocale();
  const query = useQuery({ queryKey: ['shop-floor-telemetry'], queryFn: getShopFloorSummary, retry: false });
  return (
    <Stack spacing={2}>
      <PageHeader title={t('nav.counterDiagnostics')} subtitle={t('dashboard.shopFloor')} />
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {query.data ? (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <ShopFloorFunnel summary={query.data} />
        </Paper>
      ) : null}
    </Stack>
  );
}

function ShopFloorFunnel({ summary }: { summary: import('@/lib/telemetry').ShopFloorSummary }) {
  const funnel = summary.funnel;
  const p95 = summary.completeP95Ms ?? summary.complete_p95_ms;
  const offline = summary.offlineFlushFail ?? summary.offline_flush_fail ?? 0;
  const reasons = funnelReasons(
    funnel,
    'invoice_complete_failed_by_reason',
    'invoiceCompleteFailedByReason',
  );
  const reasonBits = Object.entries(reasons).filter(([, n]) => n > 0);
  const rows: { key: string; started: number | string; completed: number | string; failed: number }[] = [
    {
      key: 'invoice',
      started: funnelCount(funnel, 'invoice_complete_started', 'invoiceCompleteStarted'),
      completed: funnelCount(funnel, 'invoice_complete', 'invoiceComplete'),
      failed: funnelCount(funnel, 'invoice_complete_failed', 'invoiceCompleteFailed'),
    },
    {
      key: 'pdf',
      started: funnelCount(funnel, 'pdf_started', 'pdfStarted'),
      completed: '—',
      failed: funnelCount(funnel, 'pdf_failed', 'pdfFailed'),
    },
    {
      key: 'payment',
      started: funnelCount(funnel, 'payment_started', 'paymentStarted'),
      completed: funnelCount(funnel, 'payment_completed', 'paymentCompleted'),
      failed: funnelCount(funnel, 'payment_failed', 'paymentFailed'),
    },
    {
      key: 'signup',
      started: '—',
      completed: funnelCount(funnel, 'signup_completed', 'signupCompleted'),
      failed: funnelCount(funnel, 'signup_failed', 'signupFailed'),
    },
  ];
  return (
    <Stack spacing={2}>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={3}>
        <Typography variant="body2">
          {t('dashboard.completeP95')}: {p95 != null ? t('dashboard.msValue', { n: p95 }) : '—'}
        </Typography>
        <Typography variant="body2">
          {t('dashboard.offlineFails')}: {offline}
        </Typography>
      </Stack>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>{t('dashboard.journey')}</TableCell>
            <TableCell align="right">{t('dashboard.journeyStarted')}</TableCell>
            <TableCell align="right">{t('dashboard.journeyCompleted')}</TableCell>
            <TableCell align="right">{t('dashboard.journeyFailed')}</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.key}>
              <TableCell>
                {row.key === 'invoice'
                  ? t('dashboard.journeyInvoice')
                  : row.key === 'pdf'
                    ? t('dashboard.journeyPdf')
                    : row.key === 'payment'
                      ? t('dashboard.journeyPayment')
                      : t('dashboard.journeySignup')}
              </TableCell>
              <TableCell align="right">{row.started}</TableCell>
              <TableCell align="right">{row.completed}</TableCell>
              <TableCell align="right">{row.failed}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {reasonBits.length ? (
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          <Typography variant="body2" color="text.secondary">
            {t('dashboard.failedReasons')}:
          </Typography>
          {reasonBits.map(([reason, n]) => (
            <Chip key={reason} size="small" label={`${tOptional(`dashboard.failReason.${reason}`) ?? reason}: ${n}`} />
          ))}
        </Stack>
      ) : null}
    </Stack>
  );
}
