import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardActionArea from '@mui/material/CardActionArea';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';
import Paper from '@mui/material/Paper';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import Stack from '@mui/material/Stack';
import WhatsAppIcon from '@mui/icons-material/WhatsApp';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { getErrorMessage } from '@/api/client';
import { listCollectionsWorklist, listOpenInvoices, type OpenInvoiceRow } from '@/api/osPlan';
import { getCompany, listPaymentPromises, resolvePaymentPromise } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { PageTitle } from '@/contextHelp';
import { isRuntimeFlagEnabled } from '@/config/featureFlags';
import { t } from '@/i18n';
import { todayIso } from '@/components/billing/lineHelpers';
import { formatMoney, toNumber } from '@/utils/money';
import { openShareUrl } from '@/utils/safeUrl';
import { canManagePaymentPromises } from '@/utils/permissions';
import {
  type AgingCohort,
  buildDunningMessage,
  buildUpiUri,
  buildWhatsAppShareUrl,
  getAgingCohort,
} from '@/utils/upi';


const COHORT_CARDS: Array<{
  id: AgingCohort;
  labelKey: string;
  labelColor: string;
  selectedBorder: string;
}> = [
  { id: 'UPCOMING', labelKey: 'osPlan.cohortUpcoming', labelColor: 'text.secondary', selectedBorder: 'primary.main' },
  { id: 'OVERDUE_1_15', labelKey: 'osPlan.cohortOverdueEarly', labelColor: 'warning.main', selectedBorder: 'warning.main' },
  { id: 'OVERDUE_16_45', labelKey: 'osPlan.cohortOverdueFirm', labelColor: 'error.main', selectedBorder: 'error.light' },
  { id: 'CRITICAL_45_PLUS', labelKey: 'osPlan.cohortCritical', labelColor: 'error.dark', selectedBorder: 'error.main' },
];

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
  const companyQuery = useQuery({ queryKey: ['company'], queryFn: getCompany });
  const company = companyQuery.data;

  const [selectedCohort, setSelectedCohort] = useState<AgingCohort | null>(null);
  const [nudgeRow, setNudgeRow] = useState<OpenInvoiceRow | null>(null);
  const [nudgeMessage, setNudgeMessage] = useState<string>('');

  const rows = useMemo(() => openInvoices.data ?? [], [openInvoices.data]);
  const cohortCounts = useMemo(() => {
    const totals: Record<AgingCohort, { count: number; amount: number }> = {
      UPCOMING: { count: 0, amount: 0 },
      OVERDUE_1_15: { count: 0, amount: 0 },
      OVERDUE_16_45: { count: 0, amount: 0 },
      CRITICAL_45_PLUS: { count: 0, amount: 0 },
    };
    for (const r of rows) {
      const bucket = totals[getAgingCohort(r.daysOverdue)];
      bucket.count += 1;
      bucket.amount += toNumber(r.outstanding);
    }
    return totals;
  }, [rows]);

  const filteredRows = useMemo(() => {
    if (!selectedCohort) return rows;
    return rows.filter((r) => getAgingCohort(r.daysOverdue) === selectedCohort);
  }, [rows, selectedCohort]);

  const handleOpenNudge = (row: OpenInvoiceRow) => {
    const upiUri = company?.upiId
      ? buildUpiUri({
          pa: company.upiId,
          pn: company.name,
          am: row.outstanding,
          tn: `Inv_${row.invoiceNumber}`,
        })
      : '';
    const msg = buildDunningMessage({
      customerName: row.customerName,
      companyName: company?.name || t('app.name'),
      invoiceNumber: row.invoiceNumber,
      amount: row.outstanding,
      daysOverdue: row.daysOverdue,
      upiUri: upiUri || undefined,
    });
    setNudgeRow(row);
    setNudgeMessage(msg);
  };

  const today = todayIso();
  return (
    <Stack spacing={2}>
      <PageTitle>{t('nav.collections')}</PageTitle>
      <Typography variant="body2" color="text.secondary">{t('osPlan.collectionsHelp')}</Typography>
      <Typography variant="body2" color="text.secondary">{t('osPlan.screenOnly')}</Typography>

      {/* Aging cohorts: one card per bucket; clicking filters the list below. */}
      {rows.length > 0 ? (
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ mb: 1 }}>
          {COHORT_CARDS.map((card) => {
            const selected = selectedCohort === card.id;
            return (
              <Card
                key={card.id}
                variant="outlined"
                sx={{
                  flex: 1,
                  cursor: 'pointer',
                  borderColor: selected ? card.selectedBorder : 'divider',
                  bgcolor: selected ? 'action.selected' : 'background.paper',
                }}
              >
                <CardActionArea
                  onClick={() => setSelectedCohort((c) => (c === card.id ? null : card.id))}
                  aria-pressed={selected}
                  sx={{ p: 1.5 }}
                >
                  <Typography variant="caption" color={card.labelColor} fontWeight={700}>
                    {t(card.labelKey)}
                  </Typography>
                  <Typography variant="h6">{formatMoney(cohortCounts[card.id].amount)}</Typography>
                  <Typography variant="caption" color="text.secondary">
                    {t('osPlan.invoiceCount', { count: cohortCounts[card.id].count })}
                  </Typography>
                </CardActionArea>
              </Card>
            );
          })}
        </Stack>
      ) : null}

      <Typography variant="h6">{t('osPlan.openInvoices')}</Typography>
      {filteredRows.length > 0 ? (
        <Paper variant="outlined" tabIndex={0} role="region" aria-label={t('common.scrollableTable')} sx={{ overflow: 'auto' }}>
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
              {filteredRows.map((row) => (
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
                      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                        <Button
                          size="small"
                          variant="outlined"
                          color="success"
                          startIcon={<WhatsAppIcon />}
                          onClick={() => handleOpenNudge(row)}
                        >
                          {t('osPlan.nudgeButton')}
                        </Button>
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

      {/* WhatsApp Nudge Dialog */}
      <Dialog open={Boolean(nudgeRow)} onClose={() => setNudgeRow(null)} maxWidth="sm" fullWidth>
        <DialogTitle>
          {t('osPlan.nudgeTitle', { name: nudgeRow?.customerName ?? '' })}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Typography variant="body2" color="text.secondary">
              {t('osPlan.nudgeSummary', {
                number: nudgeRow?.invoiceNumber ?? '',
                days: nudgeRow?.daysOverdue ?? 0,
                amount: formatMoney(nudgeRow?.outstanding ?? 0),
              })}
            </Typography>
            <TextField
              label={t('sweep.whatsappPreview')}
              multiline
              rows={8}
              fullWidth
              value={nudgeMessage}
              onChange={(e) => setNudgeMessage(e.target.value)}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setNudgeRow(null)}>{t('common.close')}</Button>
          <Button
            variant="outlined"
            onClick={() => {
              void navigator.clipboard?.writeText(nudgeMessage);
              setPromiseMessage(t('osPlan.remindCopied'));
            }}
          >
            {t('osPlan.copyText')}
          </Button>
          <Button
            variant="contained"
            color="success"
            startIcon={<WhatsAppIcon />}
            onClick={() => {
              if (nudgeRow?.customerPhone) {
                openShareUrl(buildWhatsAppShareUrl(nudgeRow.customerPhone, nudgeMessage));
              } else {
                openShareUrl(`https://wa.me/?text=${encodeURIComponent(nudgeMessage)}`);
              }
            }}
          >
            {t('osPlan.sendWhatsapp')}
          </Button>
        </DialogActions>
      </Dialog>
      {predictive && query.isLoading ? <LoadingState /> : null}
      {predictive && query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {predictive && !query.isLoading && !query.isError && (query.data?.length ?? 0) === 0 ? (
        <EmptyState description={t('osPlan.collectionsEmpty')} />
      ) : null}
      {predictive && (query.data?.length ?? 0) > 0 ? (
        <Paper variant="outlined" tabIndex={0} role="region" aria-label={t('common.scrollableTable')} sx={{ overflow: 'auto' }}>
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
        <Paper variant="outlined" tabIndex={0} role="region" aria-label={t('common.scrollableTable')} sx={{ overflow: 'auto' }}>
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
