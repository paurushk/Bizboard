import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Link from '@mui/material/Link';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import LinearProgress from '@mui/material/LinearProgress';
import { Link as RouterLink, useSearchParams } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import * as api from '@/api/resources';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { MoneyHandoffBar } from '@/components/MoneyHandoffBar';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { useCustomerSearch } from '@/hooks/usePartySearch';
import type { Customer, SalesInvoice } from '@/types/domain';
import { formatMoney, toNumber } from '@/utils/money';
import { openShareUrl } from '@/utils/safeUrl';
import { t } from '@/i18n';
import { useAuth } from '@/auth/AuthContext';
import { canCreatePayments, canExport } from '@/utils/permissions';
import { cashBookRowPath } from '@/pages/reports/ledgerLinks';
import { useReportPeriod } from '@/utils/useReportPeriod';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import {
  asRows,
  DataTable,
  PageShell,
  StatusChip,
  type Row,
} from '@/pages/phase/phaseShared';


export function PaymentLinksPage() {
  const { writesBlocked } = useSubscriptionGate();
  const qc = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  // The Money hub links here with ?status=open (links a customer can still pay).
  const [openOnly, setOpenOnly] = useState(() => searchParams.get('status') === 'open');
  const [nowMs] = useState(() => Date.now());
  const query = useQuery({
    queryKey: ['payment-links'],
    queryFn: () => api.listAllPaymentLinks(),
  });
  const [open, setOpen] = useState(false);
  const [amount, setAmount] = useState('');
  // UXW2B-020: pick customer/invoice by name/number instead of asking for a raw
  // internal id a shopkeeper has no way to know — same searchable-picker pattern
  // used by the Credit Note / Sales Return / Receipts "source document" fields.
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [customerQuery, setCustomerQuery] = useState('');
  const debouncedCustomerQuery = useDebouncedValue(customerQuery, 300);
  const [invoice, setInvoice] = useState<SalesInvoice | null>(null);
  const [invoiceQuery, setInvoiceQuery] = useState('');
  const debouncedInvoiceQuery = useDebouncedValue(invoiceQuery, 300);
  const [error, setError] = useState('');
  const linkCustomers = useQuery({
    queryKey: ['payment-link-customers', debouncedCustomerQuery],
    queryFn: () => api.listCustomersPage({ q: debouncedCustomerQuery, pageSize: 50 }),
    enabled: debouncedCustomerQuery.trim().length >= 2,
  });
  const linkInvoices = useQuery({
    queryKey: ['payment-link-invoices', debouncedInvoiceQuery],
    queryFn: () => api.listSalesInvoicesPage({ status: 'COMPLETED', q: debouncedInvoiceQuery, pageSize: 50 }),
    enabled: debouncedInvoiceQuery.trim().length >= 2,
  });
  const create = useMutation({
    mutationFn: () =>
      api.createPaymentLink({
        amount: Number(amount) || undefined,
        customer: customer ? customer.id : undefined,
        salesInvoice: invoice ? invoice.id : undefined,
      }),
    onSuccess: () => {
      setOpen(false);
      setAmount('');
      setCustomer(null);
      setCustomerQuery('');
      setInvoice(null);
      setInvoiceQuery('');
      void qc.invalidateQueries({ queryKey: ['payment-links'] });
    },
    onError: (e) => setError(getErrorMessage(e)),
  });
  const cancel = useMutation({
    mutationFn: (id: number) => api.cancelPaymentLink(id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['payment-links'] }),
    onError: (e) => setError(getErrorMessage(e)),
  });
  // F2-003 / F3-003: Refund moves real money and Cancel voids a live link —
  // both require an explicit confirmation with the amount + customer shown.
  const [confirmLink, setConfirmLink] = useState<{ mode: 'refund' | 'cancel'; row: Row } | null>(null);
  const [shareId, setShareId] = useState<number | null>(null);
  const [shareRecipient, setShareRecipient] = useState('');
  const [shareChannel, setShareChannel] = useState<'WHATSAPP' | 'EMAIL'>('WHATSAPP');
  const holding = useQuery({
    queryKey: ['gateway-holding'],
    queryFn: async () => (await api.listGatewayPaymentsPage({ status: 'CAPTURED_PENDING_BOOKS', pageSize: 50 })).results,
  });
  const retryBooks = useMutation({
    mutationFn: (id: number) => api.retryGatewayPaymentBooks(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['gateway-holding'] });
      void qc.invalidateQueries({ queryKey: ['payment-links'] });
      void qc.invalidateQueries({ queryKey: ['payment-health'] });
    },
    onError: (e) => setError(getErrorMessage(e)),
  });
  const share = useMutation({
    mutationFn: () =>
      api.sharePaymentLink(Number(shareId), { channel: shareChannel, recipient: shareRecipient }),
    onSuccess: (res) => {
      setShareId(null);
      setShareRecipient('');
      if (res.shareLink) {
        try {
          openShareUrl(String(res.shareLink));
        } catch {
          /* blocked unsafe URL — dialog already closed */
        }
      }
      void qc.invalidateQueries({ queryKey: ['payment-links'] });
    },
    onError: (e) => setError(getErrorMessage(e)),
  });
  const refund = useMutation({
    mutationFn: async (linkId: number) => {
      const gps = await api.listGatewayPayments(linkId);
      const captured = gps.find((g) => String(g.status) === 'CAPTURED');
      if (!captured) throw new Error('No captured gateway payment to refund');
      return api.refundGatewayPayment(Number(captured.id));
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['payment-links'] }),
    onError: (e) => setError(getErrorMessage(e)),
  });
  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  return (
    <PageShell
      title={t('phase.paymentLinks')}
      subtitle={t('phase.paymentLinksSubtitle')}
      actions={
        <Button variant="contained" onClick={() => setOpen(true)} disabled={writesBlocked}>
          {t('sweep2.createLink')}
        </Button>
      }
    >
      {error ? <HelpErrorAlert message={error} /> : null}
      <MoneyHandoffBar
        filterLabel={openOnly ? t('money.filters.linksOpen') : t('money.filters.gatewayWaiting')}
        onShowAll={() => {
          setOpenOnly(false);
          setSearchParams({}, { replace: true });
        }}
      />
      {holding.data && holding.data.length ? (
        <Alert severity="warning" sx={{ mb: 2 }}>
          {holding.data.length} capture(s) paid at the gateway — receipt pending books. Retry after the period is open.
        </Alert>
      ) : null}
      {holding.data && holding.data.length ? (
        <Stack spacing={1} sx={{ mb: 2 }}>
          {holding.data.map((row) => (
            <Paper key={String(row.id)} variant="outlined" sx={{ p: 1.5 }}>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems="center" justifyContent="space-between">
                <Typography variant="body2">
                  {String(row.providerPaymentId || row.provider_payment_id || row.id)} · {String(row.holdingReason || row.holding_reason || 'holding')} · {formatMoney(String(row.amount ?? 0))}
                </Typography>
                <Button
                  size="small"
                  variant="outlined"
                  disabled={writesBlocked || retryBooks.isPending}
                  onClick={() => retryBooks.mutate(Number(row.id))}
                >
                  {t('sweep2.retryBooks')}
                </Button>
              </Stack>
            </Paper>
          ))}
        </Stack>
      ) : null}
      <DataTable
        rows={asRows(query.data).filter((r) => {
          if (!openOnly) return true;
          const status = String(r.status);
          if (status !== 'CREATED' && status !== 'SENT' && status !== 'PARTIALLY_PAID') return false;
          const expires = r.expiresAt ? Date.parse(String(r.expiresAt)) : NaN;
          return Number.isNaN(expires) || expires > nowMs;
        })}
        empty="No payment links yet."
        columns={[
          { key: 'invoiceNumber', label: 'Invoice' },
          { key: 'customerName', label: 'Customer' },
          { key: 'amount', label: 'Amount', money: true },
          { key: 'status', label: 'Status', status: true },
          { key: 'provider', label: 'Provider' },
          { key: 'expiresAt', label: 'Expires' },
        ]}
        actions={(r) => (
          <Stack direction="row" spacing={1} justifyContent="flex-end" flexWrap="wrap" useFlexGap>
            <Button size="small" href={`/pay/${String(r.token)}`} target="_blank" rel="noreferrer">
              {t('sweep2.open')}
            </Button>
            {r.status !== 'PAID' && r.status !== 'CANCELLED' && r.status !== 'EXPIRED' ? (
              <>
                <Button size="small" disabled={writesBlocked} onClick={() => setShareId(Number(r.id))}>
                  {t('sweep2.send')}
                </Button>
                <Button size="small" color="error" disabled={writesBlocked} onClick={() => setConfirmLink({ mode: 'cancel', row: r })}>
                  {t('sweep2.cancel')}
                </Button>
              </>
            ) : null}
            {r.status === 'PAID' ? (
              <Button
                size="small"
                color="warning"
                disabled={writesBlocked || refund.isPending}
                onClick={() => setConfirmLink({ mode: 'refund', row: r })}
              >
                {t('sweep2.refund')}
              </Button>
            ) : null}
          </Stack>
        )}
      />
      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{t('sweep2.createPaymentLink')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Autocomplete
              options={linkInvoices.data?.results ?? []}
              getOptionLabel={(o) => `${o.number ?? o.id} · ${o.customerName ?? ''}`}
              filterOptions={(opts) => opts}
              inputValue={invoiceQuery}
              onInputChange={(_, v, reason) => {
                if (reason === 'input' || reason === 'clear' || reason === 'reset') setInvoiceQuery(v);
              }}
              value={invoice}
              onChange={(_, v) => setInvoice(v)}
              loading={linkInvoices.isFetching}
              renderInput={(params) => (
                <TextField {...params} label={t('sweep.salesInvoicePreferred')} placeholder={t('sweep.typeToSearch')} />
              )}
            />
            <Autocomplete
              options={linkCustomers.data?.results ?? []}
              getOptionLabel={(o) => o.name}
              filterOptions={(opts) => opts}
              inputValue={customerQuery}
              onInputChange={(_, v, reason) => {
                if (reason === 'input' || reason === 'clear' || reason === 'reset') setCustomerQuery(v);
              }}
              value={customer}
              onChange={(_, v) => setCustomer(v)}
              loading={linkCustomers.isFetching}
              disabled={Boolean(invoice)}
              renderInput={(params) => (
                <TextField {...params} label={t('sweep.customerIfNoInvoice')} placeholder={t('sweep.typeToSearch')} />
              )}
            />
            <TextField
              label={t('sweep.amount')}
              type="number"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              inputProps={{ min: 0, step: 'any', inputMode: 'decimal' }}
              error={amount !== '' && !(Number(amount) > 0)}
              helperText={
                amount !== '' && !(Number(amount) > 0)
                  ? 'Enter a positive amount or leave blank.'
                  : 'Leave blank to use full invoice outstanding'
              }
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>{t('sweep2.cancel')}</Button>
          <Button
            variant="contained"
            disabled={
              writesBlocked ||
              create.isPending ||
              (!invoice && !customer) ||
              (amount !== '' && !(Number(amount) > 0))
            }
            onClick={() => create.mutate()}
          >
            {t('sweep2.create')}
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog open={shareId != null} onClose={() => setShareId(null)} fullWidth maxWidth="xs">
        <DialogTitle>{t('sweep2.sendPaymentLink')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              select
              label={t('sweep.channel')}
              value={shareChannel}
              onChange={(e) => setShareChannel(e.target.value as 'WHATSAPP' | 'EMAIL')}
            >
              <MenuItem value="WHATSAPP">{t('common.whatsapp')}</MenuItem>
              <MenuItem value="EMAIL">{t('sweep2.email')}</MenuItem>
            </TextField>
            <TextField
              label={t('sweep.recipient')}
              value={shareRecipient}
              onChange={(e) => setShareRecipient(e.target.value)}
              placeholder={shareChannel === 'EMAIL' ? 'customer@example.com' : '9198XXXXXXXX'}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShareId(null)}>{t('sweep2.cancel')}</Button>
          <Button variant="contained" disabled={writesBlocked || !shareRecipient.trim() || share.isPending} onClick={() => share.mutate()}>
            {t('sweep2.send')}
          </Button>
        </DialogActions>
      </Dialog>
      <ConfirmDialog
        open={confirmLink !== null}
        title={confirmLink?.mode === 'refund' ? 'Refund this payment?' : 'Cancel this payment link?'}
        body={
          confirmLink?.mode === 'refund'
            ? `This issues a real refund of ${formatMoney(
                toNumber(String(confirmLink?.row.amount ?? '')),
              )} to ${String(confirmLink?.row.customerName ?? 'the customer')}. This cannot be undone.`
            : `Link ${String(confirmLink?.row.token ?? '')} for ${formatMoney(
                toNumber(String(confirmLink?.row.amount ?? '')),
              )} will be voided and can no longer be paid.`
        }
        confirmLabel={confirmLink?.mode === 'refund' ? 'Refund' : 'Cancel link'}
        confirmColor="error"
        confirming={confirmLink?.mode === 'refund' ? refund.isPending : cancel.isPending}
        onClose={() => setConfirmLink(null)}
        onConfirm={() => {
          if (!confirmLink) return;
          const id = Number(confirmLink.row.id);
          if (confirmLink.mode === 'refund') refund.mutate(id);
          else cancel.mutate(id);
          setConfirmLink(null);
        }}
      />
    </PageShell>
  );
}

export function BankStatementsPage() {
  const { writesBlocked } = useSubscriptionGate();
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: ['bank-statements'],
    queryFn: async () => (await api.listBankStatementsPage()).results,
  });
  const accounts = useQuery({ queryKey: ['bank-accounts'], queryFn: api.listBankAccounts });
  const [file, setFile] = useState<File | null>(null);
  const [bank, setBank] = useState('');
  const [preset, setPreset] = useState('generic');
  const [error, setError] = useState('');
  const upload = useMutation({
    mutationFn: () => {
      const data = new FormData();
      data.append('file', file!);
      data.append('bank_account', bank);
      data.append('preset', preset);
      return api.uploadBankStatement(data);
    },
    onSuccess: () => {
      setFile(null);
      void qc.invalidateQueries({ queryKey: ['bank-statements'] });
    },
    onError: (e) => setError(getErrorMessage(e)),
  });
  const commit = useMutation({
    mutationFn: (id: number) => api.commitBankStatement(id),
    onSuccess: () => {
      setError('');
      void qc.invalidateQueries({ queryKey: ['bank-statements'] });
    },
    onError: (e) => setError(getErrorMessage(e)),
  });
  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  return (
    <PageShell title={t('phase.bankStatements')} subtitle={t('phase.bankStatementsSubtitle')}>
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} alignItems={{ md: 'center' }}>
          <TextField select label={t('sweep.bankAccount')} value={bank} onChange={(e) => setBank(e.target.value)} sx={{ minWidth: 220 }}>
            {(accounts.data ?? []).map((a) => (
              <MenuItem key={a.id} value={String(a.id)}>
                {a.name}
              </MenuItem>
            ))}
          </TextField>
          <TextField select label={t('sweep.preset')} value={preset} onChange={(e) => setPreset(e.target.value)} sx={{ minWidth: 140 }}>
            <MenuItem value="generic">{t('sweep2.generic')}</MenuItem>
            <MenuItem value="hdfc">HDFC</MenuItem>
            <MenuItem value="icici">ICICI</MenuItem>
            <MenuItem value="sbi">SBI</MenuItem>
          </TextField>
          <Button component="label" variant="outlined" disabled={writesBlocked}>
            {file ? file.name : 'Choose CSV'}
            <input hidden type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </Button>
          <Button variant="contained" disabled={writesBlocked || !file || !bank || upload.isPending} onClick={() => upload.mutate()}>
            {t('sweep2.upload')}
          </Button>
        </Stack>
        {error ? <HelpErrorAlert message={error} sx={{ mt: 2 }} /> : null}
      </Paper>
      <DataTable
        rows={asRows(query.data)}
        empty="No statements uploaded."
        columns={[
          { key: 'bankAccountName', label: 'Account' },
          { key: 'periodStart', label: 'From' },
          { key: 'periodEnd', label: 'To' },
          { key: 'sourceFilename', label: 'File' },
          { key: 'status', label: 'Status', status: true },
          { key: 'unmatchedCount', label: 'Unmatched' },
        ]}
        actions={(r) =>
          r.status === 'PREVIEW' ? (
            <Button size="small" variant="contained" disabled={writesBlocked} onClick={() => {
              if (!window.confirm(t('phase.confirmCommitStatement'))) return;
              commit.mutate(Number(r.id));
            }}>
              {t('sweep2.commit')}
            </Button>
          ) : null
        }
      />
    </PageShell>
  );
}

/** The reconciliation queue endpoint returns at most this many lines. */
const RECON_QUEUE_CAP = 100;

export function BankReconPage() {
  const { user } = useAuth();
  const { writesBlocked } = useSubscriptionGate();
  const canWrite = canCreatePayments(user) && !writesBlocked;
  const qc = useQueryClient();
  const health = useQuery({ queryKey: ['payment-health'], queryFn: api.getPaymentHealth });
  // BB-100 F7: reconciliation is for people who record payments; others would only get a 403.
  const mayRecon = canCreatePayments(user);
  const query = useQuery({
    queryKey: ['payment-recon'],
    queryFn: () => api.listRecon() as Promise<Row[]>,
    enabled: mayRecon,
  });
  const [searchParams, setSearchParams] = useSearchParams();
  const focusLine = Number(searchParams.get('line')) || null;
  // The Money hub links here with money in (credits) or money out (debits) only.
  const [direction, setDirection] = useState<'' | 'credit' | 'debit'>(() => {
    const raw = searchParams.get('direction');
    return raw === 'credit' || raw === 'debit' ? raw : '';
  });
  const review = useQuery({ queryKey: ['payment-recon-review'], queryFn: api.listReconNeedsReview, enabled: mayRecon });
  const matchReturn = useMutation({
    mutationFn: (payload: { line: number; receipt: number }) => api.matchReconReturn(payload),
    onSuccess: () => {
      setReconErr('');
      setBulkAcceptMsg(t('receipts.reviewMatched'));
      void qc.invalidateQueries({ queryKey: ['payment-recon'] });
      void qc.invalidateQueries({ queryKey: ['payment-recon-review'] });
    },
    onError: (e) => setReconErr(getErrorMessage(e)),
  });
  const [createLine, setCreateLine] = useState<Row | null>(null);
  const [createCustomer, setCreateCustomer] = useState<Customer | null>(null);
  // F2-025: search-as-you-type instead of loading every customer up front.
  const createCustomerSearch = useCustomerSearch({ selected: createCustomer });
  const [reconErr, setReconErr] = useState('');
  const [bulkAcceptMsg, setBulkAcceptMsg] = useState('');
  const confirm = useMutation({
    mutationFn: (payload: Record<string, unknown>) => api.confirmRecon(payload),
    onSuccess: () => {
      setReconErr('');
      void qc.invalidateQueries({ queryKey: ['payment-recon'] });
    },
    onError: (e) => setReconErr(getErrorMessage(e)),
  });
  // QOS-0039: accept every EXACT-class suggestion in one click instead of
  // confirming high-confidence matches one by one; fuzzy ones stay for
  // manual review. Undoable per-line via the existing unmatch action.
  const bulkAcceptExact = useMutation({
    mutationFn: () => api.bulkAcceptExactMatches(),
    onSuccess: (result) => {
      setReconErr('');
      setBulkAcceptMsg(
        result.accepted_count > 0
          ? t('phase.bulkAcceptExactAccepted', { count: result.accepted_count })
          : t('phase.bulkAcceptExactNone'),
      );
      void qc.invalidateQueries({ queryKey: ['payment-recon'] });
      void qc.invalidateQueries({ queryKey: ['payment-health'] });
    },
    onError: (e) => setReconErr(getErrorMessage(e)),
  });
  const createFromLine = useMutation({
    mutationFn: () =>
      api.createReceiptFromReconLine({
        line: createLine?.id,
        customer: createCustomer?.id,
      }),
    onSuccess: () => {
      setReconErr('');
      setCreateLine(null);
      setCreateCustomer(null);
      void qc.invalidateQueries({ queryKey: ['payment-recon'] });
      void qc.invalidateQueries({ queryKey: ['payment-health'] });
    },
    onError: (e) => setReconErr(getErrorMessage(e)),
  });
  // Matching is never applied on page load: confirming a bank line posts money. A person
  // confirms each suggestion, or uses "accept exact matches" for the unambiguous ones.
  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  const allRows = query.data ?? [];
  const rows = direction
    ? allRows.filter((item) => {
        const amount = Number(((item.line || item) as Row).amount);
        return direction === 'credit' ? amount > 0 : amount < 0;
      })
    : allRows;
  // The server sends the oldest lines first and stops at this many.
  const queueCapped = allRows.length >= RECON_QUEUE_CAP;
  const aging = (health.data?.unmatchedAging as Record<string, number>) || {};
  return (
    <PageShell
      title={t('phase.bankRecon')}
      subtitle={t('phase.bankReconSubtitle')}
      actions={
        canWrite && rows.length > 0 ? (
          <Button
            variant="outlined"
            size="small"
            disabled={bulkAcceptExact.isPending}
            onClick={() => {
              setBulkAcceptMsg('');
              bulkAcceptExact.mutate();
            }}
          >
            {t('phase.bulkAcceptExact')}
          </Button>
        ) : null
      }
    >
      <MoneyHandoffBar
        filterLabel={direction === 'debit' ? t('money.filters.bankDebits') : t('money.filters.bankCredits')}
        onShowAll={() => {
          setDirection('');
          setSearchParams({}, { replace: true });
        }}
      />
      {queueCapped ? (
        <Alert severity="info" sx={{ mb: 1 }}>
          {t('money.recon.capped', { count: RECON_QUEUE_CAP })}
        </Alert>
      ) : null}
      {reconErr ? (
        <Alert severity="error" sx={{ mb: 1 }} onClose={() => setReconErr('')}>
          {reconErr}
        </Alert>
      ) : null}
      {bulkAcceptMsg ? (
        <Alert severity="success" sx={{ mb: 1 }} onClose={() => setBulkAcceptMsg('')}>
          {bulkAcceptMsg}
        </Alert>
      ) : null}
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ mb: 1 }}>
        {[
          ['0–7 days', aging.days_0_7 ?? aging.days07 ?? 0],
          ['8–30 days', aging.days_8_30 ?? aging.days830 ?? 0],
          ['30+ days', aging.days_30_plus ?? aging.days30Plus ?? 0],
        ].map(([label, count]) => (
          <Paper key={String(label)} variant="outlined" sx={{ p: 1.5, flex: 1 }}>
            <Typography variant="caption" color="text.secondary">
              Unmatched {label}
            </Typography>
            <Typography variant="h6">{String(count)}</Typography>
          </Paper>
        ))}
      </Stack>
      {Array.isArray(health.data?.alerts) && (health.data.alerts as Row[]).length ? (
        <Stack spacing={1} sx={{ mb: 1 }}>
          {(health.data.alerts as Row[]).slice(0, 5).map((a, i) => (
            <Alert key={i} severity={String(a.severity) === 'critical' ? 'error' : 'warning'}>
              {String(a.message || a.code)}
            </Alert>
          ))}
        </Stack>
      ) : null}
      {(review.data?.length ?? 0) > 0 ? (
        <Paper variant="outlined" sx={{ p: 2, mb: 2, borderColor: 'warning.main' }}>
          <Typography variant="subtitle2" component="h2">
            {t('receipts.reviewTitle')}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            {t('receipts.reviewIntro')}
          </Typography>
          <Stack spacing={1}>
            {review.data!.map((item) => {
              // The bank's return of a cheque is a debit line for the same amount.
              const returnLine = rows
                .map((r) => (r.line || r) as Row)
                .find(
                  (l) =>
                    Number(l.amount) < 0 &&
                    String(l.matchStatus) !== 'MATCHED' &&
                    Math.abs(Math.abs(Number(l.amount)) - Math.abs(Number(item.lineAmount))) < 0.01,
                );
              return (
                <Stack key={item.match} direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ sm: 'center' }}>
                  <Typography variant="body2" sx={{ flex: 1 }}>
                    {item.receiptNumber} · {item.customerName} · {formatMoney(item.lineAmount)} · {item.lineDate}
                  </Typography>
                  {returnLine && canWrite ? (
                    <Button
                      size="small"
                      variant="contained"
                      disabled={matchReturn.isPending}
                      onClick={() => matchReturn.mutate({ line: Number(returnLine.id), receipt: item.receipt })}
                    >
                      {t('receipts.reviewMatchReturn')}
                    </Button>
                  ) : (
                    <Typography variant="caption" color="text.secondary">
                      {t('receipts.reviewNoReturnLine')}
                    </Typography>
                  )}
                </Stack>
              );
            })}
          </Stack>
        </Paper>
      ) : null}
      {!rows.length ? (
        <EmptyState description="No unmatched bank lines. Commit a statement to begin." />
      ) : (
        <Stack spacing={2}>
          {rows.map((item, idx) => {
            const line = (item.line || item) as Row;
            const suggestions = (item.suggestions as Row[]) || [];
            return (
              <Paper
                key={String(line.id ?? idx)}
                variant="outlined"
                sx={{ p: 2, ...(focusLine != null && Number(line.id) === focusLine ? { borderColor: 'primary.main', borderWidth: 2 } : {}) }}
              >
                <Stack spacing={1.5}>
                  <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" gap={1}>
                    <Box>
                      <Typography fontWeight={600}>
                        {String(line.txnDate ?? '')} · {formatMoney(toNumber(line.amount as string | number))}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        {String(line.narration || '—')} {line.utr ? `· UTR ${String(line.utr)}` : ''}
                      </Typography>
                    </Box>
                    <Stack direction="row" spacing={1} alignItems="center">
                      <StatusChip value={line.matchStatus} />
                      {Number(line.amount) > 0 && canWrite ? (
                        <Button size="small" variant="outlined" onClick={() => setCreateLine(line)}>
                          {t('sweep2.createReceipt')}
                        </Button>
                      ) : null}
                    </Stack>
                  </Stack>
                  {/* F2-014: once a line is MATCHED, drop all match actions — a
                      second confirm double-books it. */}
                  {String(line.matchStatus) === 'MATCHED' ? null : !suggestions.length ? (
                    <Alert severity="warning">{t('sweep2.noConfidentSuggestions')}</Alert>
                  ) : (
                    suggestions.map((s) => {
                      const lineAmt = toNumber(line.amount as string | number);
                      const sugAmt = toNumber(s.amount as string | number);
                      const amountsDiffer = Math.abs(lineAmt - sugAmt) > 0.01;
                      return (
                      <Stack key={`${s.type}-${s.id}`} direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ sm: 'center' }}>
                        <Chip size="small" label={`${Math.round(Number(s.confidence))}%`} color={Number(s.confidence) >= 90 ? 'success' : 'default'} />
                        <Typography variant="body2" sx={{ flex: 1 }}>
                          {String(s.type)} {String(s.number)} · {String(s.party)} · {formatMoney(sugAmt)}
                          {amountsDiffer ? (
                            <Typography component="span" variant="caption" color="warning.main" sx={{ ml: 1 }}>
                              (differs from bank line by {formatMoney(Math.abs(lineAmt - sugAmt))})
                            </Typography>
                          ) : null}
                        </Typography>
                        {canWrite ? (
                        <Button
                          size="small"
                          variant="contained"
                          disabled={confirm.isPending}
                          onClick={() => {
                            if (
                              amountsDiffer &&
                              !window.confirm(
                                `The bank line is ${formatMoney(lineAmt)} but this ${String(s.type)} is ${formatMoney(sugAmt)}. Match them anyway?`,
                              )
                            ) {
                              return;
                            }
                            confirm.mutate({
                              line: line.id,
                              receipt: s.type === 'receipt' ? s.id : undefined,
                              supplierPayment: s.type === 'supplier_payment' ? s.id : undefined,
                              confidence: s.confidence,
                            });
                          }}
                        >
                          {t('sweep2.confirm')}
                        </Button>
                        ) : null}
                      </Stack>
                      );
                    })
                  )}
                </Stack>
              </Paper>
            );
          })}
        </Stack>
      )}
      <Dialog open={Boolean(createLine)} onClose={() => setCreateLine(null)} fullWidth maxWidth="xs">
        <DialogTitle>{t('sweep2.createReceiptFromBank')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Typography variant="body2">
              {createLine
                ? `${String(createLine.txnDate)} · ${formatMoney(toNumber(createLine.amount as string | number))}`
                : ''}
            </Typography>
            <Autocomplete
              options={createCustomerSearch.options.filter((o: Customer) => !o.isPosWalkIn)}
              getOptionLabel={(o: Customer) => o.name}
              isOptionEqualToValue={(o, v) => o.id === v.id}
              value={createCustomer}
              onChange={(_, v) => setCreateCustomer(v)}
              onInputChange={(_, v) => createCustomerSearch.setQuery(v)}
              filterOptions={(opts) => opts}
              loading={createCustomerSearch.isFetching}
              renderInput={(params) => (
                <TextField
                  {...params}
                  label={t('sweep.customer')}
                  helperText={!createCustomerSearch.enabled ? t('common.typeToSearch') : undefined}
                />
              )}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateLine(null)}>{t('sweep2.cancel')}</Button>
          <Button
            variant="contained"
            disabled={!createCustomer || createFromLine.isPending}
            onClick={() => createFromLine.mutate()}
          >
            {t('sweep2.createAndMatch')}
          </Button>
        </DialogActions>
      </Dialog>
    </PageShell>
  );
}

export function CashBookPage() {
  const { user } = useAuth();
  // RPT-06: opens on this month and remembers the last choice; a backwards range is not sent.
  const { dateFrom: from, dateTo: to, setDateFrom: setFrom, setDateTo: setTo, invalid } = useReportPeriod('cash-book', 'thisMonth');
  const [exportErr, setExportErr] = useState('');
  // The API can narrow the book to one bank account; "All" is cash and every account together.
  const [bankAccount, setBankAccount] = useState('');
  const banks = useQuery({ queryKey: ['bank-accounts'], queryFn: api.listBankAccounts });
  const rangeParams = {
    ...(from ? { date_from: from } : {}),
    ...(to ? { date_to: to } : {}),
    ...(bankAccount ? { bank_account: bankAccount } : {}),
  };
  const q = useQuery({
    enabled: !invalid,
    queryKey: ['cash-book', from, to, bankAccount],
    queryFn: () => api.getCashBook(rangeParams),
    // RPT-05: keep the last result and the date boxes on screen while a new range loads.
    placeholderData: keepPreviousData,
  });
  const health = useQuery({ queryKey: ['payment-health'], queryFn: api.getPaymentHealth });
  const failed = q.isError;
  const ready = Boolean(q.data) && !failed;
  const data = (ready ? q.data : {}) as Row;
  const rows = (data.rows as Row[]) || [];
  return (
    <PageShell
      title={t('phase.cashBook')}
      subtitle={t('phase.cashBookSubtitle')}
      actions={
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          <TextField type="date" size="small" label={t('sweep.from')} InputLabelProps={{ shrink: true }} value={from} onChange={(e) => setFrom(e.target.value)} />
          <TextField type="date" size="small" label={t('sweep.to')} InputLabelProps={{ shrink: true }} value={to} onChange={(e) => setTo(e.target.value)} error={invalid} helperText={invalid ? t('salesSummary.rangeBackwards') : undefined} />
          <TextField select size="small" label={t('sweep.bankAccount')} value={bankAccount} onChange={(e) => setBankAccount(e.target.value)} sx={{ minWidth: 180 }}>
            <MenuItem value="">{t('reportLabels.allAccounts')}</MenuItem>
            {(banks.data ?? []).map((b) => (
              <MenuItem key={b.id} value={String(b.id)}>{b.name}</MenuItem>
            ))}
          </TextField>
          {canExport(user) ? (
          <Button
            variant="outlined"
            size="small"
            onClick={async () => {
              try {
                setExportErr('');
                const { url } = await api.downloadCashBookXlsx(rangeParams);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'cash-book.xlsx';
                a.click();
                URL.revokeObjectURL(url);
              } catch (e) {
                setExportErr(getErrorMessage(e));
              }
            }}
          >
            {t('sweep2.exportXlsx')}
          </Button>
          ) : null}
        </Stack>
      }
    >
      {q.isFetching ? <LinearProgress aria-label={t('common.loading')} /> : null}
      {q.isLoading ? <LoadingState /> : null}
      {failed ? (
        <ErrorState message={getErrorMessage(q.error)} error={q.error} onRetry={() => void q.refetch()} />
      ) : null}
      {exportErr ? <HelpErrorAlert message={exportErr} /> : null}
      {Array.isArray(health.data?.alerts) && (health.data.alerts as Row[]).length ? (
        <Alert severity="warning">
          {t('reportLabels.paymentHealth', {
            critical: String((health.data.summary as Row)?.critical ?? 0),
            warning: String((health.data.summary as Row)?.warning ?? 0),
          })}
        </Alert>
      ) : null}
      {ready ? (
        <>
      <Alert severity="info">{String(data.disclaimer || t('reportLabels.cashDisclaimer'))}</Alert>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
        {[
          [t('reportLabels.opening'), data.opening],
          [t('reportLabels.inflow'), data.inflow],
          [t('reportLabels.outflow'), data.outflow],
          [t('reportLabels.closing'), data.closing],
        ].map(([label, val]) => (
          <Paper key={String(label)} variant="outlined" sx={{ p: 2, flex: 1 }}>
            <Typography variant="caption" color="text.secondary">
              {String(label)}
            </Typography>
            <Typography variant="h6">{formatMoney(toNumber(val as string | number))}</Typography>
          </Paper>
        ))}
      </Stack>
      <DataTable
        rows={rows}
        empty={t('reportLabels.noCashMovements')}
        // F3-016: an unbounded date range can return every cash movement —
        // window the DOM rows instead of rendering them all at once.
        virtualized
        columns={[
          { key: 'date', label: t('reportLabels.date') },
          { key: 'type', label: t('reportLabels.type') },
          {
            key: 'number',
            label: t('reportLabels.number'),
            // RPT-11: open the receipt or payment behind the row.
            render: (row: Row) => {
              const link = cashBookRowPath(row);
              return link ? <Link component={RouterLink} to={link}>{String(row.number ?? '')}</Link> : String(row.number ?? '—');
            },
          },
          { key: 'party', label: t('reportLabels.party') },
          { key: 'mode', label: t('reportLabels.mode') },
          { key: 'inflow', label: t('reportLabels.inflow'), money: true },
          { key: 'outflow', label: t('reportLabels.outflow'), money: true },
          { key: 'reference', label: t('reportLabels.ref') },
        ]}
      />
        </>
      ) : null}
    </PageShell>
  );
}

