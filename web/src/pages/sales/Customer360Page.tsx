import { useState } from 'react';
import Button from '@mui/material/Button';
import MenuItem from '@mui/material/MenuItem';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { contractTimeline, issueReferralCode, listContractsPage, listTicketsPage } from '@/api/growth';
import { getCustomer360 } from '@/api/osPlan';
import { createPaymentPromise, listPaymentPromises, repeatLastInvoice, resolvePaymentPromise } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { isRuntimeFlagEnabled } from '@/config/featureFlags';
import { isComplaintsEnabled, isContractsEnabled, isReferralsEnabled, isSupportTicketsEnabled } from '@/config/features';
import { ErrorState, LoadingState } from '@/components/PageState';
import { PageTitle } from '@/contextHelp';
import { t } from '@/i18n';
import { todayIso } from '@/components/billing/lineHelpers';
import { formatMoney } from '@/utils/money';
import { canManagePaymentPromises } from '@/utils/permissions';

function agingAmount(aging: Record<string, string> | null | undefined, keys: string[]): string | null {
  if (!aging) return null;
  for (const key of keys) {
    if (aging[key] != null && aging[key] !== '') return aging[key];
  }
  return null;
}

// Same "a few days out, editable" default as InvoiceDetailPage's promise-to-pay dialog.
function defaultPromiseDate(): string {
  const d = new Date();
  d.setDate(d.getDate() + 3);
  return todayIso(d);
}

export function Customer360Page() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const qc = useQueryClient();
  const customerId = Number(id);
  const customerIdValid = Number.isFinite(customerId) && customerId > 0;
  const query = useQuery({
    queryKey: ['customer-360', customerId],
    queryFn: () => getCustomer360(customerId),
    enabled: customerIdValid,
  });
  const [repeatError, setRepeatError] = useState('');
  const repeatMutation = useMutation({
    mutationFn: () => repeatLastInvoice(customerId),
    onSuccess: (draft) => navigate(`/sales/history/${draft.id}/edit`),
    onError: (err) => setRepeatError(getErrorMessage(err)),
  });
  const canPromise = canManagePaymentPromises(user);
  const [promiseOpen, setPromiseOpen] = useState(false);
  const [promiseDate, setPromiseDate] = useState(() => defaultPromiseDate());
  const [promiseNote, setPromiseNote] = useState('');
  const [promiseAmount, setPromiseAmount] = useState('');
  const [promiseError, setPromiseError] = useState('');
  // F2-050 pattern (see InvoiceDetailPage): no confirmed customer-scoped
  // backend filter for /payments/promises/, so we fetch open promises
  // company-wide and filter to this customer client-side. Follow-up: if a
  // company accumulates many open promises this becomes wasteful — add a
  // `?customer=` filter to PaymentPromiseViewSet then, rather than doing it
  // speculatively here.
  const paymentPromises = useQuery({
    queryKey: ['payment-promises', 'customer', customerId],
    queryFn: () => listPaymentPromises({ customer: customerId }),
    enabled: customerIdValid,
  });
  const promiseList = Array.isArray(paymentPromises.data) ? paymentPromises.data : [];
  const customerPromises = promiseList.filter((p) => p.customer === customerId);
  const createPromiseMutation = useMutation({
    mutationFn: () =>
      createPaymentPromise({
        customer: customerId,
        promisedDate: promiseDate,
        promisedAmount: promiseAmount.trim(),
        note: promiseNote.trim() || undefined,
      }),
    onSuccess: () => {
      setPromiseOpen(false);
      setPromiseNote('');
      setPromiseError('');
      void qc.invalidateQueries({ queryKey: ['payment-promises', 'customer', customerId] });
    },
    onError: (err) => setPromiseError(getErrorMessage(err)),
  });
  const resolvePromiseMutation = useMutation({
    mutationFn: (promiseId: number) => resolvePaymentPromise(promiseId),
    onSuccess: () => {
      setPromiseError('');
      void qc.invalidateQueries({ queryKey: ['payment-promises', 'customer', customerId] });
    },
    onError: (err) => setPromiseError(getErrorMessage(err)),
  });
  const showComplaints = isRuntimeFlagEnabled('ENABLE_CUSTOMER_360') && isComplaintsEnabled();
  const showTickets = isRuntimeFlagEnabled('ENABLE_CUSTOMER_360') && isSupportTicketsEnabled();
  const showContracts = isRuntimeFlagEnabled('ENABLE_CUSTOMER_360') && isContractsEnabled();
  const showReferral = isReferralsEnabled();
  const [issuedCode, setIssuedCode] = useState('');
  const [issueError, setIssueError] = useState('');
  const [issuing, setIssuing] = useState(false);
  const [rewardType, setRewardType] = useState('FLAT');
  const [rewardValue, setRewardValue] = useState('0');
  const tickets = useQuery({
    queryKey: ['customer-tickets', customerId],
    queryFn: () => listTicketsPage({ customer: customerId, pageSize: 20 }),
    enabled: showTickets && customerIdValid,
  });
  const contracts = useQuery({
    queryKey: ['customer-contracts', customerId],
    queryFn: () => listContractsPage({ customer: customerId, pageSize: 20 }),
    enabled: showContracts && customerIdValid,
  });
  const body = query.data;
  return (
    <Stack spacing={2}>
      <PageTitle>{body?.name || t('nav.customer360')}</PageTitle>
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {body ? (
        <Stack spacing={2}>
          <Paper variant="outlined" sx={{ p: 2 }}>
            <Typography variant="subtitle2">{t('osPlan.salesPattern')}</Typography>
            <Typography variant="body2">
              {t('osPlan.invoiceCount', { count: body.sales.invoices })}
              {body.sales.amount != null ? ` · ${formatMoney(body.sales.amount)}` : ''}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {body.pattern || t('osPlan.noPattern')}
            </Typography>
            {body.recommendedNextStep ? (
              <Typography variant="body2">{body.recommendedNextStep}</Typography>
            ) : null}
            <Button
              size="small"
              variant="outlined"
              sx={{ mt: 1 }}
              disabled={repeatMutation.isPending}
              onClick={() => {
                setRepeatError('');
                repeatMutation.mutate();
              }}
            >
              {t('billing.repeatLastInvoice')}
            </Button>
            {repeatError ? (
              <Typography color="error" variant="body2" sx={{ mt: 0.5 }}>
                {repeatError}
              </Typography>
            ) : null}
          </Paper>
          {body.outstanding != null || body.profit != null ? (
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Typography variant="subtitle2">{t('osPlan.money')}</Typography>
              {body.outstanding != null ? (
                <Typography variant="body2">{t('portal.outstanding')}: {formatMoney(body.outstanding)}</Typography>
              ) : null}
              {body.profit?.totals ? (
                <Typography variant="body2">
                  {t('osPlan.profit')}: {formatMoney(body.profit.totals.margin ?? 0)}
                </Typography>
              ) : null}
              {body.aging ? (
                <Stack spacing={0.5} sx={{ mt: 1 }}>
                  <Typography variant="body2">{t('osPlan.agingCurrent')}: {formatMoney(agingAmount(body.aging, ['current']) ?? 0)}</Typography>
                  <Typography variant="body2">{t('osPlan.aging130')}: {formatMoney(agingAmount(body.aging, ['130', '1_30']) ?? 0)}</Typography>
                  <Typography variant="body2">{t('osPlan.aging3160')}: {formatMoney(agingAmount(body.aging, ['3160', '31_60']) ?? 0)}</Typography>
                  <Typography variant="body2">{t('osPlan.aging6190')}: {formatMoney(agingAmount(body.aging, ['6190', '61_90']) ?? 0)}</Typography>
                  <Typography variant="body2">{t('osPlan.aging90')}: {formatMoney(agingAmount(body.aging, ['90Plus', '90_plus']) ?? 0)}</Typography>
                  {agingAmount(body.aging, ['advances_and_other', 'advancesAndOther']) != null ? (
                    <Typography variant="body2">
                      {t('osPlan.agingOther')}: {formatMoney(agingAmount(body.aging, ['advances_and_other', 'advancesAndOther']) ?? 0)}
                    </Typography>
                  ) : null}
                </Stack>
              ) : null}
            </Paper>
          ) : null}
          <Paper variant="outlined" sx={{ p: 2 }}>
            <Typography variant="subtitle2">{t('billing.paymentPromiseTitle')}</Typography>
            {paymentPromises.isLoading ? <LoadingState /> : null}
            {customerPromises.length ? (
              <Stack spacing={1} sx={{ mt: 1 }}>
                {customerPromises.map((promise) => (
                  <Stack key={promise.id} direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                    <Typography variant="body2">
                      {t('billing.paymentPromiseExisting', { date: promise.promisedDate })}
                      {' · '}
                      {promise.amountLabel
                        || (promise.promisedAmount != null && promise.promisedAmount !== ''
                          ? formatMoney(promise.promisedAmount)
                          : t('osPlan.amountNotRecorded'))}
                      {promise.invoiceNumber
                        ? ` ${t('billing.paymentPromiseForInvoice', { number: promise.invoiceNumber })}`
                        : ''}
                    </Typography>
                    {promise.note ? (
                      <Typography variant="body2" color="text.secondary">
                        {promise.note}
                      </Typography>
                    ) : null}
                    {canPromise ? (
                      <Button
                        size="small"
                        variant="outlined"
                        disabled={resolvePromiseMutation.isPending}
                        onClick={() => {
                          setPromiseError('');
                          resolvePromiseMutation.mutate(promise.id);
                        }}
                      >
                        {t('billing.paymentPromiseResolve')}
                      </Button>
                    ) : null}
                  </Stack>
                ))}
              </Stack>
            ) : !paymentPromises.isLoading ? (
              <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                {t('billing.paymentPromiseEmpty')}
              </Typography>
            ) : null}
            {canPromise ? (
              <Button
                size="small"
                variant="outlined"
                sx={{ mt: 1 }}
                onClick={() => {
                  setPromiseDate(defaultPromiseDate());
                  setPromiseNote('');
                  setPromiseAmount('');
                  setPromiseError('');
                  setPromiseOpen(true);
                }}
              >
                {t('billing.paymentPromiseLog')}
              </Button>
            ) : null}
            {promiseError ? (
              <Typography color="error" variant="body2" sx={{ mt: 0.5 }}>
                {promiseError}
              </Typography>
            ) : null}
          </Paper>
          {showComplaints && body.complaints ? (
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Typography variant="subtitle2">{t('customer360.complaints')}</Typography>
              {body.complaints.length === 0 ? (
                <Typography variant="body2" color="text.secondary">{t('customer360.none')}</Typography>
              ) : body.complaints.map((row) => (
                <Typography key={row.id} variant="body2">
                  {row.number || row.id} · {String(row.category || '').replaceAll('_', ' ')} · {String(row.status || '').replaceAll('_', ' ')}
                </Typography>
              ))}
            </Paper>
          ) : null}
          {showTickets ? (
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Typography variant="subtitle2">{t('growth.support')}</Typography>
              {(tickets.data?.results ?? []).map((row) => {
                const breached = row.slaDueAt && ['OPEN', 'IN_PROGRESS', 'WAITING'].includes(row.status) && new Date(row.slaDueAt).getTime() < Date.now();
                return (
                  <Typography key={row.id} variant="body2">
                    {row.number} · {row.subject} · {row.status.replaceAll('_', ' ')} · {row.priority}
                    {row.assigneeName ? ` · ${row.assigneeName}` : ` · ${t('growth.unassigned')}`}
                    {breached ? ` · ${t('growth.slaBreached')}` : row.slaDueAt ? ` · ${t('growth.sla')} ${new Date(row.slaDueAt).toLocaleString()}` : ''}
                  </Typography>
                );
              })}
            </Paper>
          ) : null}
          {showContracts ? (
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Typography variant="subtitle2">{t('growth.serviceHistory')}</Typography>
              {(contracts.data?.results ?? []).map((row) => (
                <ContractHistory key={row.id} contractId={row.id} />
              ))}
            </Paper>
          ) : null}
          {showReferral ? (
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Typography variant="subtitle2">{t('nav.referrals')}</Typography>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ mt: 1 }} alignItems={{ sm: 'center' }}>
                <TextField select size="small" label={t('growth.rewardType')} value={rewardType} onChange={(e) => setRewardType(e.target.value)} sx={{ minWidth: 140 }}>
                  <MenuItem value="FLAT">{t('osPlan.rewardFixed')}</MenuItem>
                  <MenuItem value="PERCENT">{t('osPlan.rewardPercent')}</MenuItem>
                </TextField>
                <TextField size="small" label={t('growth.rewardValue')} value={rewardValue} onChange={(e) => setRewardValue(e.target.value)} />
                <Button size="small" disabled={issuing} onClick={() => {
                  setIssuing(true);
                  setIssueError('');
                  void issueReferralCode({
                    referrer_customer: customerId,
                    reward_type: rewardType,
                    reward_value: rewardValue || '0',
                  })
                    .then((row) => setIssuedCode(row.code))
                    .catch((err) => setIssueError(getErrorMessage(err)))
                    .finally(() => setIssuing(false));
                }}>
                  {t('growth.issueCode')}
                </Button>
              </Stack>
              {issuedCode ? <Typography variant="body2">{t('growth.issuedFor')}: {issuedCode}</Typography> : null}
              {issueError ? <Typography color="error" variant="body2">{issueError}</Typography> : null}
            </Paper>
          ) : null}
          <Paper variant="outlined" sx={{ p: 2 }}>
            <Typography variant="subtitle2">{t('osPlan.products')}</Typography>
            <Typography variant="body2">
              {body.products.length ? body.products.join(', ') : t('osPlan.noProducts')}
            </Typography>
          </Paper>
          <Dialog open={promiseOpen} onClose={() => setPromiseOpen(false)} fullWidth maxWidth="sm">
            <DialogTitle>{t('billing.paymentPromiseLog')}</DialogTitle>
            <DialogContent>
              <Stack spacing={2} sx={{ mt: 1 }}>
                <TextField
                  type="date"
                  label={t('billing.paymentPromiseDateLabel')}
                  value={promiseDate}
                  onChange={(e) => setPromiseDate(e.target.value)}
                  InputLabelProps={{ shrink: true }}
                  fullWidth
                />
                <TextField
                  label={t('osPlan.promiseAmount')}
                  value={promiseAmount}
                  onChange={(e) => setPromiseAmount(e.target.value)}
                  fullWidth
                  required
                />
                <TextField
                  label={t('billing.paymentPromiseNoteLabel')}
                  value={promiseNote}
                  onChange={(e) => setPromiseNote(e.target.value)}
                  multiline
                  minRows={2}
                  fullWidth
                />
              </Stack>
            </DialogContent>
            <DialogActions>
              <Button onClick={() => setPromiseOpen(false)}>{t('common.cancel')}</Button>
              <Button
                variant="contained"
                disabled={!promiseDate.trim() || !(Number(promiseAmount) > 0) || createPromiseMutation.isPending}
                onClick={() => createPromiseMutation.mutate()}
              >
                {t('billing.paymentPromiseSave')}
              </Button>
            </DialogActions>
          </Dialog>
        </Stack>
      ) : null}
    </Stack>
  );
}

function ContractHistory({ contractId }: { contractId: number }) {
  const timeline = useQuery({
    queryKey: ['customer-contract-timeline', contractId],
    queryFn: () => contractTimeline(contractId),
  });
  const row = timeline.data?.contract;
  if (!row) return null;
  return (
    <Stack spacing={0.5} sx={{ mt: 1 }}>
      <Typography variant="body2">
        {row.number} · {row.contractType} · {row.status} · {t('growth.warrantyPeriod')} {row.startDate} – {row.endDate}
      </Typography>
      {(timeline.data?.events ?? []).map((event) => (
        <Typography key={event.id} variant="caption">{event.occurredAt} · {event.notes}</Typography>
      ))}
    </Stack>
  );
}
