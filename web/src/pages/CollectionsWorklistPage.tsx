import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Paper from '@mui/material/Paper';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import Stack from '@mui/material/Stack';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { getErrorMessage } from '@/api/client';
import { listCollectionsWorklist, listOpenInvoices } from '@/api/osPlan';
import { listPaymentPromises, resolvePaymentPromise } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { PageTitle } from '@/contextHelp';
import { isRuntimeFlagEnabled } from '@/config/featureFlags';
import { t } from '@/i18n';
import { todayIso } from '@/components/billing/lineHelpers';
import { formatMoney } from '@/utils/money';
import { canManagePaymentPromises } from '@/utils/permissions';


export function CollectionsWorklistPage() {
  const predictive = isRuntimeFlagEnabled('ENABLE_PREDICTIVE_DUNNING');
  const query = useQuery({
    queryKey: ['collections-worklist'],
    queryFn: listCollectionsWorklist,
    enabled: predictive,
  });
  const openInvoices = useQuery({ queryKey: ['collections-open-invoices'], queryFn: listOpenInvoices });
  const { user } = useAuth();
  const canResolve = canManagePaymentPromises(user);
  const qc = useQueryClient();
  const [promiseMessage, setPromiseMessage] = useState<string | null>(null);
  const promisesQuery = useQuery({
    queryKey: ['payment-promises', 'worklist'],
    // No params defaults to open (unresolved) promises company-wide, per the API.
    queryFn: () => listPaymentPromises(),
  });
  const promiseList = Array.isArray(promisesQuery.data) ? promisesQuery.data : [];
  const promises = [...promiseList].sort((a, b) =>
    a.promisedDate.localeCompare(b.promisedDate),
  );
  const resolveMutation = useMutation({
    mutationFn: (id: number) => resolvePaymentPromise(id),
    onSuccess: () => {
      setPromiseMessage(t('billing.paymentPromiseResolved'));
      void qc.invalidateQueries({ queryKey: ['payment-promises', 'worklist'] });
    },
  });
  const today = todayIso();
  return (
    <Stack spacing={2}>
      <PageTitle>{t('nav.collections')}</PageTitle>
      <Typography variant="body2" color="text.secondary">{t('osPlan.collectionsHelp')}</Typography>
      <Typography variant="body2" color="text.secondary">{t('osPlan.screenOnly')}</Typography>
      <Typography variant="h6">{t('osPlan.openInvoices')}</Typography>
      {(openInvoices.data?.length ?? 0) > 0 ? (
        <Paper variant="outlined" sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('billing.customer')}</TableCell>
                <TableCell>{t('common.number')}</TableCell>
                <TableCell align="right">{t('osPlan.daysOverdue')}</TableCell>
                <TableCell align="right">{t('osPlan.amountReceived')}</TableCell>
                <TableCell align="right">{t('osPlan.invoiceBalance')}</TableCell>
                <TableCell align="right">{t('osPlan.customerTotal')}</TableCell>
                <TableCell>{t('osPlan.remind')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {openInvoices.data!.map((row) => (
                <TableRow key={row.invoiceId}>
                  <TableCell>{row.customerName}</TableCell>
                  <TableCell>{row.invoiceNumber}</TableCell>
                  <TableCell align="right">{row.daysOverdue}</TableCell>
                  <TableCell align="right">{formatMoney(row.amountReceived)}</TableCell>
                  <TableCell align="right">{formatMoney(row.outstanding)}</TableCell>
                  <TableCell align="right">{formatMoney(row.customerOutstanding)}</TableCell>
                  <TableCell>
                    <Stack spacing={0.5}>
                      <Typography variant="body2">
                        {row.customerPhone || t('osPlan.noPhone')}
                      </Typography>
                      <Stack direction="row" spacing={1}>
                        <Button
                          size="small"
                          disabled={!(row.remindUrl || row.remindMessage)}
                          onClick={() => {
                            const link = row.remindUrl || row.remindMessage || '';
                            if (!link) return;
                            const done = () => setPromiseMessage(t('osPlan.remindCopied'));
                            const copy = navigator.clipboard?.writeText(link);
                            if (copy) void copy.then(done, () => setPromiseMessage(link));
                            else setPromiseMessage(link);
                          }}
                        >
                          {t('osPlan.copyRemindLink')}
                        </Button>
                        {row.remindUrl ? (
                          <Button size="small" component="a" href={row.remindUrl} target="_blank" rel="noreferrer">
                            {t('osPlan.remind')}
                          </Button>
                        ) : null}
                      </Stack>
                    </Stack>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}
      {predictive && query.isLoading ? <LoadingState /> : null}
      {predictive && query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {predictive && !query.isLoading && !query.isError && (query.data?.length ?? 0) === 0 ? (
        <EmptyState description={t('osPlan.collectionsEmpty')} />
      ) : null}
      {predictive && (query.data?.length ?? 0) > 0 ? (
        <Paper variant="outlined" sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('billing.customer')}</TableCell>
                <TableCell>{t('common.number')}</TableCell>
                <TableCell>{t('osPlan.dueDate')}</TableCell>
                <TableCell align="right">{t('portal.outstanding')}</TableCell>
                <TableCell align="right">{t('osPlan.predictedLate')}</TableCell>
                <TableCell>{t('osPlan.confidence')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {query.data!.map((row) => (
                <TableRow key={row.invoiceId}>
                  <TableCell>{row.customerName}</TableCell>
                  <TableCell>{row.invoiceNumber}</TableCell>
                  <TableCell>{row.dueDate}</TableCell>
                  <TableCell align="right">{formatMoney(row.outstanding)}</TableCell>
                  <TableCell align="right">
                    {row.predictedDaysLate == null ? '—' : t('osPlan.daysLate', { count: row.predictedDaysLate })}
                  </TableCell>
                  <TableCell>{row.confident ? t('osPlan.confident') : t('osPlan.notEnoughHistory')}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}

      <Typography variant="h6" sx={{ mt: 2 }}>{t('osPlan.paymentPromisesTitle')}</Typography>
      {promiseMessage ? (
        <Alert severity="success" role="status" onClose={() => setPromiseMessage(null)}>
          {promiseMessage}
        </Alert>
      ) : null}
      {promisesQuery.isLoading ? <LoadingState /> : null}
      {promisesQuery.isError ? (
        <ErrorState
          message={getErrorMessage(promisesQuery.error)}
          error={promisesQuery.error}
          onRetry={() => void promisesQuery.refetch()}
        />
      ) : null}
      {!promisesQuery.isLoading && !promisesQuery.isError && promises.length === 0 ? (
        <EmptyState description={t('osPlan.paymentPromisesEmpty')} />
      ) : null}
      {promises.length > 0 ? (
        <Paper variant="outlined" sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('billing.customer')}</TableCell>
                <TableCell>{t('billing.paymentPromiseDateLabel')}</TableCell>
                <TableCell>{t('osPlan.promiseAmount')}</TableCell>
                <TableCell>{t('common.notes')}</TableCell>
                <TableCell>{t('common.number')}</TableCell>
                <TableCell align="right">{t('common.actions')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {promises.map((promise) => {
                // Same rule as the server: a promise for today is due, not overdue.
                const overdue = promise.promisedDate < today;
                const dueToday = promise.promisedDate === today;
                return (
                  <TableRow key={promise.id} hover sx={overdue ? { bgcolor: 'warning.light' } : undefined}>
                    <TableCell>{promise.customerName ?? promise.customer}</TableCell>
                    <TableCell>
                      <Stack direction="row" spacing={1} alignItems="center">
                        <Typography variant="body2">{promise.promisedDate}</Typography>
                        {overdue ? <Chip size="small" color="warning" label={t('osPlan.overdue')} /> : null}
                        {dueToday ? <Chip size="small" color="info" label={t('osPlan.dueToday')} /> : null}
                      </Stack>
                    </TableCell>
                    <TableCell>
                      {promise.amountLabel
                        || (promise.promisedAmount != null && promise.promisedAmount !== ''
                          ? formatMoney(promise.promisedAmount)
                          : t('osPlan.amountNotRecorded'))}
                      {promise.broken ? ` · ${t('osPlan.overdue')}` : ''}
                    </TableCell>
                    <TableCell>{promise.note || '—'}</TableCell>
                    <TableCell>{promise.invoiceNumber || '—'}</TableCell>
                    <TableCell align="right">
                      {canResolve ? (
                        <Button
                          size="small"
                          variant="outlined"
                          disabled={resolveMutation.isPending}
                          onClick={() => resolveMutation.mutate(promise.id)}
                        >
                          {t('billing.paymentPromiseResolve')}
                        </Button>
                      ) : null}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </Paper>
      ) : null}
      {resolveMutation.isError ? (
        <ErrorState message={getErrorMessage(resolveMutation.error)} error={resolveMutation.error} />
      ) : null}
    </Stack>
  );
}
