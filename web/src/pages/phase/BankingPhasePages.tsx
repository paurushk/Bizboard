import { useEffect, useState } from 'react';
import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import FormControlLabel from '@mui/material/FormControlLabel';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import TextField from '@mui/material/TextField';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import * as api from '@/api/resources';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import type { Customer, SalesInvoice } from '@/types/domain';
import { isValidIfsc } from '@/utils/gst';
import { formatMoney, toNumber } from '@/utils/money';
import { openShareUrl } from '@/utils/safeUrl';
import { t } from '@/i18n';
import { useAuth } from '@/auth/AuthContext';
import { canCreatePayments } from '@/utils/permissions';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import {
  asRows,
  DataTable,
  PageShell,
  StatusChip,
  type Row,
} from '@/pages/phase/phaseShared';


export function BankAccountsPage() {
  const { writesBlocked } = useSubscriptionGate();
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ['bank-accounts'], queryFn: api.listBankAccounts });
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: '', accountType: 'CURRENT', ifsc: '', accountNumberMasked: '', isDefault: false });
  const [error, setError] = useState('');
  const create = useMutation({
    mutationFn: () => {
      const ifsc = form.ifsc.trim().toUpperCase();
      if (ifsc && !isValidIfsc(ifsc)) {
        throw new Error('Enter a valid IFSC (e.g. HDFC0001234).');
      }
      return api.createBankAccount({
        name: form.name,
        accountType: form.accountType,
        ifsc: ifsc || form.ifsc,
        accountNumberMasked: form.accountNumberMasked,
        isDefault: form.isDefault,
      });
    },
    onSuccess: () => {
      setOpen(false);
      setForm({ name: '', accountType: 'CURRENT', ifsc: '', accountNumberMasked: '', isDefault: false });
      setError('');
      void qc.invalidateQueries({ queryKey: ['bank-accounts'] });
    },
    onError: (e) => setError(getErrorMessage(e)),
  });
  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  return (
    <PageShell
      title={t('phase.bankAccounts')}
      subtitle={t('phase.bankAccountsSubtitle')}
      actions={
        <Button variant="contained" onClick={() => setOpen(true)} disabled={writesBlocked}>
          Add account
        </Button>
      }
    >
      <DataTable
        rows={asRows(query.data)}
        empty="No bank accounts yet. Save bank details in Company settings, or add an account here."
        columns={[
          { key: 'name', label: 'Name' },
          { key: 'accountType', label: 'Type' },
          { key: 'accountNumberMasked', label: 'Account' },
          { key: 'ifsc', label: 'IFSC' },
          { key: 'openingBalance', label: 'Opening', money: true },
          { key: 'isDefault', label: 'Default', bool: true },
        ]}
      />
      {asRows(query.data).length === 0 ? (
        <Button component={RouterLink} to="/settings/company#bank-section" sx={{ mt: 1, alignSelf: 'flex-start' }}>
          Open company bank details
        </Button>
      ) : null}
      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>New bank account</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField label="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
            <TextField select label="Type" value={form.accountType} onChange={(e) => setForm({ ...form, accountType: e.target.value })}>
              <MenuItem value="CURRENT">Current</MenuItem>
              <MenuItem value="SAVINGS">Savings</MenuItem>
              <MenuItem value="CASH_BOX">Cash box</MenuItem>
            </TextField>
            <TextField label="Masked account no." value={form.accountNumberMasked} onChange={(e) => setForm({ ...form, accountNumberMasked: e.target.value })} />
            <TextField label="IFSC" value={form.ifsc} onChange={(e) => setForm({ ...form, ifsc: e.target.value })} />
            <FormControlLabel control={<Switch checked={form.isDefault} onChange={(e) => setForm({ ...form, isDefault: e.target.checked })} />} label="Default account" />
            {error ? <HelpErrorAlert message={error} /> : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
          <Tooltip title={!form.name.trim() ? 'Enter bank account name to save' : ''}>
            <span>
              <Button variant="contained" disabled={writesBlocked || !form.name.trim() || create.isPending} onClick={() => create.mutate()}>
                Save
              </Button>
            </span>
          </Tooltip>
        </DialogActions>
      </Dialog>
    </PageShell>
  );
}

export function PaymentGatewayPage() {
  const { writesBlocked } = useSubscriptionGate();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['gateway-settings'], queryFn: api.getGatewaySettings });
  const [provider, setProvider] = useState('');
  const [testMode, setTestMode] = useState(true);
  const [requireRef, setRequireRef] = useState(false);
  const [autoMatch, setAutoMatch] = useState(false);
  const [keyId, setKeyId] = useState('');
  const [keySecret, setKeySecret] = useState('');
  const [msg, setMsg] = useState('');
  useEffect(() => {
    if (!q.data) return;
    setTestMode(Boolean(q.data.testMode ?? true));
    setRequireRef(Boolean(q.data.requirePaymentReference));
    setAutoMatch(Boolean(q.data.autoMatchBankExact));
    setProvider(String(q.data.provider ?? 'razorpay'));
  }, [q.data]);
  const m = useMutation({
    mutationFn: () =>
      api.updateGatewaySettings({
        provider: provider || q.data?.provider || 'razorpay',
        test_mode: testMode,
        require_payment_reference: requireRef,
        auto_match_bank_exact: autoMatch,
        credentials: keyId || keySecret ? { key_id: keyId, key_secret: keySecret, api_key: keyId, api_secret: keySecret } : undefined,
      }),
    onSuccess: () => {
      setMsg('Gateway settings saved');
      setKeySecret('');
      void qc.invalidateQueries({ queryKey: ['gateway-settings'] });
    },
    onError: (e) => setMsg(getErrorMessage(e)),
  });
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState message={getErrorMessage(q.error)} error={q.error} onRetry={() => void q.refetch()} />;
  const webhooks = (q.data?.webhookPaths as Record<string, string>) || {};
  return (
    <PageShell title={t('phase.paymentGateway')} subtitle={t('phase.paymentGatewaySubtitle')}>
      {msg ? <Alert severity={msg.includes('saved') ? 'success' : 'error'}>{msg}</Alert> : null}
      <Paper variant="outlined" sx={{ p: 3 }}>
        <Stack spacing={2}>
          <TextField
            select
            label="Provider"
            value={provider || String(q.data?.provider ?? 'razorpay')}
            onChange={(e) => setProvider(e.target.value)}
          >
            <MenuItem value="razorpay">Razorpay</MenuItem>
            <MenuItem value="cashfree">Cashfree</MenuItem>
            <MenuItem value="payu">PayU</MenuItem>
            <MenuItem value="sandbox">Sandbox (CI / local)</MenuItem>
          </TextField>
          <FormControlLabel
            control={<Switch checked={testMode} onChange={(e) => setTestMode(e.target.checked)} />}
            label="Test mode"
          />
          <FormControlLabel
            control={<Switch checked={requireRef} onChange={(e) => setRequireRef(e.target.checked)} />}
            label="Require payment reference (UTR) for UPI/Bank receipts"
          />
          <FormControlLabel
            control={<Switch checked={autoMatch} onChange={(e) => setAutoMatch(e.target.checked)} />}
            label="Auto-match bank lines on exact unique UTR"
          />
          <Alert severity="info">
            Credentials configured: {String(q.data?.credentialsConfigured ? 'Yes' : 'No')}. Leave secret blank to keep existing.
          </Alert>
          <TextField label="Key / App ID" value={keyId} onChange={(e) => setKeyId(e.target.value)} />
          <TextField label="Secret" type="password" value={keySecret} onChange={(e) => setKeySecret(e.target.value)} />
          <Button variant="contained" disabled={writesBlocked || m.isPending} onClick={() => m.mutate()}>
            Save settings
          </Button>
          <Typography variant="subtitle2">Webhook URLs</Typography>
          {Object.entries(webhooks).map(([k, v]) => (
            <Typography key={k} variant="body2" sx={{ fontFamily: 'monospace', wordBreak: 'break-all' }}>
              {k}: {v}
            </Typography>
          ))}
        </Stack>
      </Paper>
    </PageShell>
  );
}

export function PaymentLinksPage() {
  const { writesBlocked } = useSubscriptionGate();
  const qc = useQueryClient();
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
  });
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
          Create link
        </Button>
      }
    >
      {error ? <HelpErrorAlert message={error} /> : null}
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
                  Retry books
                </Button>
              </Stack>
            </Paper>
          ))}
        </Stack>
      ) : null}
      <DataTable
        rows={asRows(query.data)}
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
              Open
            </Button>
            {r.status !== 'PAID' && r.status !== 'CANCELLED' && r.status !== 'EXPIRED' ? (
              <>
                <Button size="small" disabled={writesBlocked} onClick={() => setShareId(Number(r.id))}>
                  Send
                </Button>
                <Button size="small" color="error" disabled={writesBlocked} onClick={() => cancel.mutate(Number(r.id))}>
                  Cancel
                </Button>
              </>
            ) : null}
            {r.status === 'PAID' ? (
              <Button size="small" color="warning" disabled={writesBlocked || refund.isPending} onClick={() => refund.mutate(Number(r.id))}>
                Refund
              </Button>
            ) : null}
          </Stack>
        )}
      />
      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Create payment link</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Autocomplete
              options={linkInvoices.data?.results ?? []}
              getOptionLabel={(o) => `${o.number ?? o.id} · ${o.customerName ?? ''}`}
              filterOptions={(opts) => opts}
              inputValue={invoiceQuery}
              onInputChange={(_, v, reason) => {
                if (reason === 'input' || reason === 'clear') setInvoiceQuery(v);
              }}
              value={invoice}
              onChange={(_, v) => setInvoice(v)}
              loading={linkInvoices.isFetching}
              renderInput={(params) => (
                <TextField {...params} label="Sales invoice (preferred)" placeholder="Type 2+ characters to search…" />
              )}
            />
            <Autocomplete
              options={linkCustomers.data?.results ?? []}
              getOptionLabel={(o) => o.name}
              filterOptions={(opts) => opts}
              inputValue={customerQuery}
              onInputChange={(_, v, reason) => {
                if (reason === 'input' || reason === 'clear') setCustomerQuery(v);
              }}
              value={customer}
              onChange={(_, v) => setCustomer(v)}
              loading={linkCustomers.isFetching}
              disabled={Boolean(invoice)}
              renderInput={(params) => (
                <TextField {...params} label="Customer (if no invoice)" placeholder="Type 2+ characters to search…" />
              )}
            />
            <TextField label="Amount" type="number" value={amount} onChange={(e) => setAmount(e.target.value)} helperText="Leave blank to use full invoice outstanding" />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button variant="contained" disabled={writesBlocked || create.isPending || (!invoice && !customer)} onClick={() => create.mutate()}>
            Create
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog open={shareId != null} onClose={() => setShareId(null)} fullWidth maxWidth="xs">
        <DialogTitle>Send payment link</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              select
              label="Channel"
              value={shareChannel}
              onChange={(e) => setShareChannel(e.target.value as 'WHATSAPP' | 'EMAIL')}
            >
              <MenuItem value="WHATSAPP">{t('common.whatsapp')}</MenuItem>
              <MenuItem value="EMAIL">Email</MenuItem>
            </TextField>
            <TextField
              label="Recipient"
              value={shareRecipient}
              onChange={(e) => setShareRecipient(e.target.value)}
              placeholder={shareChannel === 'EMAIL' ? 'customer@example.com' : '9198XXXXXXXX'}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShareId(null)}>Cancel</Button>
          <Button variant="contained" disabled={writesBlocked || !shareRecipient.trim() || share.isPending} onClick={() => share.mutate()}>
            Send
          </Button>
        </DialogActions>
      </Dialog>
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
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['bank-statements'] }),
  });
  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  return (
    <PageShell title={t('phase.bankStatements')} subtitle={t('phase.bankStatementsSubtitle')}>
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} alignItems={{ md: 'center' }}>
          <TextField select label="Bank account" value={bank} onChange={(e) => setBank(e.target.value)} sx={{ minWidth: 220 }}>
            {(accounts.data ?? []).map((a) => (
              <MenuItem key={a.id} value={String(a.id)}>
                {a.name}
              </MenuItem>
            ))}
          </TextField>
          <TextField select label="Preset" value={preset} onChange={(e) => setPreset(e.target.value)} sx={{ minWidth: 140 }}>
            <MenuItem value="generic">Generic</MenuItem>
            <MenuItem value="hdfc">HDFC</MenuItem>
            <MenuItem value="icici">ICICI</MenuItem>
            <MenuItem value="sbi">SBI</MenuItem>
          </TextField>
          <Button component="label" variant="outlined" disabled={writesBlocked}>
            {file ? file.name : 'Choose CSV'}
            <input hidden type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </Button>
          <Button variant="contained" disabled={writesBlocked || !file || !bank || upload.isPending} onClick={() => upload.mutate()}>
            Upload
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
            <Button size="small" variant="contained" disabled={writesBlocked} onClick={() => commit.mutate(Number(r.id))}>
              Commit
            </Button>
          ) : null
        }
      />
    </PageShell>
  );
}

export function BankReconPage() {
  const { user } = useAuth();
  const { writesBlocked } = useSubscriptionGate();
  const canWrite = canCreatePayments(user) && !writesBlocked;
  const qc = useQueryClient();
  const customers = useQuery({ queryKey: ['customers'], queryFn: () => api.listCustomers() });
  const health = useQuery({ queryKey: ['payment-health'], queryFn: api.getPaymentHealth });
  const query = useQuery({
    queryKey: ['payment-recon'],
    queryFn: async () => {
      const data = await api.listRecon();
      if (Array.isArray(data) && data.length && (data[0] as Row).line) return data as Row[];
      return data as Row[];
    },
  });
  const [createLine, setCreateLine] = useState<Row | null>(null);
  const [createCustomer, setCreateCustomer] = useState('');
  const confirm = useMutation({
    mutationFn: (payload: Record<string, unknown>) => api.confirmRecon(payload),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['payment-recon'] }),
  });
  const createFromLine = useMutation({
    mutationFn: () =>
      api.createReceiptFromReconLine({
        line: createLine?.id ?? (createLine as Row | null)?.id,
        customer: Number(createCustomer),
      }),
    onSuccess: () => {
      setCreateLine(null);
      setCreateCustomer('');
      void qc.invalidateQueries({ queryKey: ['payment-recon'] });
      void qc.invalidateQueries({ queryKey: ['payment-health'] });
    },
  });
  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  const rows = query.data ?? [];
  const aging = (health.data?.unmatchedAging as Record<string, number>) || {};
  return (
    <PageShell title={t('phase.bankRecon')} subtitle={t('phase.bankReconSubtitle')}>
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
      {!rows.length ? (
        <EmptyState description="No unmatched bank lines. Commit a statement to begin." />
      ) : (
        <Stack spacing={2}>
          {rows.map((item, idx) => {
            const line = (item.line || item) as Row;
            const suggestions = (item.suggestions as Row[]) || [];
            return (
              <Paper key={String(line.id ?? idx)} variant="outlined" sx={{ p: 2 }}>
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
                          Create receipt
                        </Button>
                      ) : null}
                    </Stack>
                  </Stack>
                  {!suggestions.length ? (
                    <Alert severity="warning">No confident suggestions</Alert>
                  ) : (
                    suggestions.map((s) => (
                      <Stack key={`${s.type}-${s.id}`} direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ sm: 'center' }}>
                        <Chip size="small" label={`${Math.round(Number(s.confidence))}%`} color={Number(s.confidence) >= 90 ? 'success' : 'default'} />
                        <Typography variant="body2" sx={{ flex: 1 }}>
                          {String(s.type)} {String(s.number)} · {String(s.party)} · {formatMoney(toNumber(s.amount as string | number))}
                        </Typography>
                        {canWrite ? (
                        <Button
                          size="small"
                          variant="contained"
                          disabled={confirm.isPending}
                          onClick={() =>
                            confirm.mutate({
                              line: line.id,
                              receipt: s.type === 'receipt' ? s.id : undefined,
                              supplierPayment: s.type === 'supplier_payment' ? s.id : undefined,
                              confidence: s.confidence,
                            })
                          }
                        >
                          Confirm
                        </Button>
                        ) : null}
                      </Stack>
                    ))
                  )}
                </Stack>
              </Paper>
            );
          })}
        </Stack>
      )}
      <Dialog open={Boolean(createLine)} onClose={() => setCreateLine(null)} fullWidth maxWidth="xs">
        <DialogTitle>Create receipt from bank line</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Typography variant="body2">
              {createLine
                ? `${String(createLine.txnDate)} · ${formatMoney(toNumber(createLine.amount as string | number))}`
                : ''}
            </Typography>
            <TextField
              select
              label="Customer"
              value={createCustomer}
              onChange={(e) => setCreateCustomer(e.target.value)}
            >
              {(customers.data ?? []).map((c) => (
                <MenuItem key={c.id} value={c.id}>
                  {c.name}
                </MenuItem>
              ))}
            </TextField>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateLine(null)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={!createCustomer || createFromLine.isPending}
            onClick={() => createFromLine.mutate()}
          >
            Create & match
          </Button>
        </DialogActions>
      </Dialog>
    </PageShell>
  );
}

export function CashBookPage() {
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [exportErr, setExportErr] = useState('');
  const q = useQuery({
    queryKey: ['cash-book', from, to],
    queryFn: () =>
      api.getCashBook({
        ...(from ? { date_from: from } : {}),
        ...(to ? { date_to: to } : {}),
      }),
  });
  const health = useQuery({ queryKey: ['payment-health'], queryFn: api.getPaymentHealth });
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState message={getErrorMessage(q.error)} error={q.error} onRetry={() => void q.refetch()} />;
  const data = q.data as Row;
  const rows = (data.rows as Row[]) || [];
  return (
    <PageShell
      title={t('phase.cashBook')}
      subtitle={t('phase.cashBookSubtitle')}
      actions={
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          <TextField type="date" size="small" label="From" InputLabelProps={{ shrink: true }} value={from} onChange={(e) => setFrom(e.target.value)} />
          <TextField type="date" size="small" label="To" InputLabelProps={{ shrink: true }} value={to} onChange={(e) => setTo(e.target.value)} />
          <Button
            variant="outlined"
            size="small"
            onClick={async () => {
              try {
                setExportErr('');
                const { url } = await api.downloadCashBookXlsx({
                  ...(from ? { date_from: from } : {}),
                  ...(to ? { date_to: to } : {}),
                });
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
            Export XLSX
          </Button>
        </Stack>
      }
    >
      {exportErr ? <HelpErrorAlert message={exportErr} /> : null}
      {Array.isArray(health.data?.alerts) && (health.data.alerts as Row[]).length ? (
        <Alert severity="warning">
          Payment health: {String((health.data.summary as Row)?.critical ?? 0)} critical,{' '}
          {String((health.data.summary as Row)?.warning ?? 0)} warnings
        </Alert>
      ) : null}
      <Alert severity="info">{String(data.disclaimer || 'Cash book shows document actuals.')}</Alert>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
        {[
          ['Opening', data.opening],
          ['Inflow', data.inflow],
          ['Outflow', data.outflow],
          ['Closing', data.closing],
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
        empty="No cash movements in this period."
        columns={[
          { key: 'date', label: 'Date' },
          { key: 'type', label: 'Type' },
          { key: 'number', label: 'Number' },
          { key: 'party', label: 'Party' },
          { key: 'mode', label: 'Mode' },
          { key: 'inflow', label: 'Inflow', money: true },
          { key: 'outflow', label: 'Outflow', money: true },
          { key: 'reference', label: 'Ref' },
        ]}
      />
    </PageShell>
  );
}

