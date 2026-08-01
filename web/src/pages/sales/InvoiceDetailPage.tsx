import { useCallback, useEffect, useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Divider from '@mui/material/Divider';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink, useLocation, useParams } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import {
  cancelSalesInvoice,
  completeSalesInvoice,
  downloadInvoicePdf,
  getSalesInvoice,
  listCustomers,
  shareInvoice,
} from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { PdfStatusPoller } from '@/components/PdfStatusPoller';
import { StatusChip } from '@/components/StatusChip';
import { t } from '@/i18n';
import { printBlob, triggerBlobDownload } from '@/utils/blob';
import { formatMoney, toNumber } from '@/utils/money';
import { canCancelDocuments } from '@/utils/permissions';
import { documentStatusTone, statusLabelKey } from '@/utils/status';

export function InvoiceDetailPage() {
  const { user } = useAuth();
  const { id } = useParams();
  const location = useLocation();
  const invoiceId = Number(id);
  const qc = useQueryClient();
  const [sharePhone, setSharePhone] = useState('');
  const [shareEmail, setShareEmail] = useState('');
  const [prefilled, setPrefilled] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(
    () => (location.state as { paymentWarning?: string } | null)?.paymentWarning ?? null,
  );

  const query = useQuery({
    queryKey: ['sales-invoice', invoiceId],
    queryFn: () => getSalesInvoice(invoiceId),
    enabled: Number.isFinite(invoiceId),
  });

  const customers = useQuery({
    queryKey: ['customers'],
    queryFn: () => listCustomers(),
  });

  useEffect(() => {
    if (prefilled || !query.data) return;
    const customer = (customers.data ?? []).find((c) => c.id === query.data.customer);
    if (customer?.phone) setSharePhone(customer.phone);
    if (customer?.email) setShareEmail(customer.email);
    if (customer || customers.isFetched) setPrefilled(true);
  }, [query.data, customers.data, customers.isFetched, prefilled]);

  const completeMutation = useMutation({
    mutationFn: () => completeSalesInvoice(invoiceId),
    onSuccess: () => {
      setMessage('Invoice completed');
      void qc.invalidateQueries({ queryKey: ['sales-invoice', invoiceId] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const cancelMutation = useMutation({
    mutationFn: () => cancelSalesInvoice(invoiceId),
    onSuccess: () => {
      setMessage('Invoice cancelled');
      void qc.invalidateQueries({ queryKey: ['sales-invoice', invoiceId] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const [shareLink, setShareLink] = useState<string | null>(null);

  const shareMutation = useMutation({
    mutationFn: (payload: { channel: 'EMAIL' | 'WHATSAPP'; recipient: string }) =>
      shareInvoice(invoiceId, payload),
    onSuccess: (res) => {
      setMessage(res.shareLink ? `Share ready` : `Share ${res.status}`);
      setShareLink(res.shareLink ?? null);
      // BUG-519: window.open here is frequently blocked by popup blockers
      // since it fires from an async callback, not directly from the click;
      // the link is also rendered as a clickable fallback below.
      if (res.shareLink) window.open(res.shareLink, '_blank');
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const downloadCopy = useCallback(
    async (copy: 'ORIGINAL' | 'DUPLICATE') => {
      try {
        const blob = await downloadInvoicePdf(invoiceId, { copy });
        const base = query.data?.number ?? `invoice-${invoiceId}`;
        triggerBlobDownload(blob, `${base}_${copy.toLowerCase()}.pdf`);
      } catch (err) {
        setError(getErrorMessage(err));
      }
    },
    [invoiceId, query.data?.number],
  );

  const handlePrint = useCallback(async () => {
    try {
      const blob = await downloadInvoicePdf(invoiceId, { copy: 'ORIGINAL' });
      printBlob(blob);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }, [invoiceId]);

  if (query.isLoading) return <LoadingState />;
  if (query.isError) {
    return <ErrorState message={getErrorMessage(query.error)} onRetry={() => void query.refetch()} />;
  }
  if (!query.data) return <EmptyState />;

  const inv = query.data;
  const canAct = inv.status === 'COMPLETED' || inv.status === 'RETURNED';
  const showTax = inv.invoiceType === 'GST' || inv.invoiceType === 'TAX' || inv.invoiceType === 'RETAIL';

  return (
    <Stack spacing={2}>
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        justifyContent="space-between"
        alignItems={{ xs: 'stretch', sm: 'flex-start' }}
        spacing={1}
      >
        <Box>
          <Typography variant="h4" sx={{ fontFamily: '"IBM Plex Sans", sans-serif' }}>
            {inv.number?.trim() ? inv.number : `Draft #${inv.id}`}
          </Typography>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 0.5, flexWrap: 'wrap' }}>
            <StatusChip tone={documentStatusTone(inv.status)} labelKey={statusLabelKey(inv.status)} />
            <Chip size="small" label={inv.invoiceType} variant="outlined" />
            <Typography variant="body2" color="text.secondary">
              {inv.invoiceDate}
            </Typography>
          </Stack>
          <Typography sx={{ mt: 1 }}>{inv.customerName}</Typography>
        </Box>
        <Button component={RouterLink} to="/sales/history">
          {t('common.back')}
        </Button>
      </Stack>

      {message ? <Alert severity="success">{message}</Alert> : null}
      {error ? <Alert severity="error">{error}</Alert> : null}

      <Paper
        elevation={0}
        sx={{
          p: 1.5,
          position: 'sticky',
          top: 0,
          zIndex: 2,
          bgcolor: 'background.paper',
          borderBottom: 1,
          borderColor: 'divider',
        }}
      >
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          {inv.status === 'DRAFT' || inv.status === 'COMPLETED' ? (
            <Button
              component={RouterLink}
              to={`/sales/history/${inv.id}/edit`}
              variant="outlined"
            >
              {t('common.edit')}
            </Button>
          ) : null}
          {inv.status === 'DRAFT' ? (
            <Button
              variant="contained"
              disabled={completeMutation.isPending}
              onClick={() => completeMutation.mutate()}
            >
              {t('common.complete')}
            </Button>
          ) : null}
          {inv.status === 'COMPLETED' && canCancelDocuments(user) ? (
            <Button
              color="error"
              variant="outlined"
              disabled={cancelMutation.isPending}
              onClick={() => {
                // BUG-520: a single mis-click used to cancel a completed,
                // potentially already-shared GST invoice with no recovery.
                if (window.confirm(`Cancel invoice ${inv.number ?? inv.id}? This cannot be undone.`)) {
                  cancelMutation.mutate();
                }
              }}
            >
              {t('common.cancel')}
            </Button>
          ) : null}
          {canAct ? (
            <>
              <Button variant="outlined" onClick={() => void downloadCopy('ORIGINAL')}>
                {t('billing.downloadOriginal')}
              </Button>
              <Button variant="outlined" onClick={() => void downloadCopy('DUPLICATE')}>
                {t('billing.downloadDuplicate')}
              </Button>
              <Button variant="outlined" onClick={() => void handlePrint()}>
                {t('billing.print')}
              </Button>
            </>
          ) : null}
        </Stack>
      </Paper>

      {inv.status === 'COMPLETED' || inv.status === 'RETURNED' ? (
        <PdfStatusPoller invoiceId={inv.id} filenameBase={inv.number ?? undefined} />
      ) : null}

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
        <Paper sx={{ p: 2, flex: 1 }}>
          <Typography variant="subtitle2" color="text.secondary">
            {t('billing.paymentSummary')}
          </Typography>
          <Divider sx={{ my: 1 }} />
          <Stack spacing={0.75}>
            <Stack direction="row" justifyContent="space-between">
              <Typography>{t('billing.grandTotal')}</Typography>
              <Typography fontWeight={700}>{formatMoney(inv.grandTotal)}</Typography>
            </Stack>
            <Stack direction="row" justifyContent="space-between">
              <Typography>{t('billing.received')}</Typography>
              <Typography>{formatMoney(inv.received ?? 0)}</Typography>
            </Stack>
            <Stack direction="row" justifyContent="space-between">
              <Typography>{t('billing.balance')}</Typography>
              <Typography fontWeight={600}>{formatMoney(inv.balance ?? inv.grandTotal)}</Typography>
            </Stack>
          </Stack>
        </Paper>
        <Paper sx={{ p: 2, flex: 1 }}>
          <Typography variant="subtitle2" color="text.secondary">
            {t('billing.taxTotals')}
          </Typography>
          <Divider sx={{ my: 1 }} />
          <Stack spacing={0.75}>
            <Stack direction="row" justifyContent="space-between">
              <Typography>Taxable</Typography>
              <Typography>{formatMoney(inv.taxableTotal)}</Typography>
            </Stack>
            {showTax ? (
              <>
                <Stack direction="row" justifyContent="space-between">
                  <Typography>CGST</Typography>
                  <Typography>{formatMoney(inv.cgstTotal)}</Typography>
                </Stack>
                <Stack direction="row" justifyContent="space-between">
                  <Typography>SGST</Typography>
                  <Typography>{formatMoney(inv.sgstTotal)}</Typography>
                </Stack>
                <Stack direction="row" justifyContent="space-between">
                  <Typography>IGST</Typography>
                  <Typography>{formatMoney(inv.igstTotal)}</Typography>
                </Stack>
              </>
            ) : null}
          </Stack>
        </Paper>
      </Stack>

      <Paper sx={{ overflow: 'auto' }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>#</TableCell>
              <TableCell>{t('nav.products')}</TableCell>
              <TableCell>HSN</TableCell>
              <TableCell align="right">{t('billing.qty')}</TableCell>
              {showTax ? <TableCell align="right">MRP</TableCell> : null}
              <TableCell align="right">{t('billing.price')}</TableCell>
              {showTax ? <TableCell align="right">{t('billing.tax')}</TableCell> : null}
              <TableCell align="right">{t('common.total')}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {(inv.items ?? []).map((item, idx) => {
              const lineTax =
                toNumber(item.cgst) + toNumber(item.sgst) + toNumber(item.igst);
              return (
                <TableRow key={item.id ?? `${item.product}-${item.quantity}`}>
                  <TableCell>{idx + 1}</TableCell>
                  <TableCell>
                    {item.productName ?? item.description ?? item.product}
                    {item.unitName ? (
                      <Typography component="span" variant="caption" color="text.secondary">
                        {` · ${item.unitName}`}
                      </Typography>
                    ) : null}
                  </TableCell>
                  <TableCell>{item.hsnCode || '—'}</TableCell>
                  <TableCell align="right">{toNumber(item.quantity)}</TableCell>
                  {showTax ? (
                    <TableCell align="right">{formatMoney(item.mrp ?? 0)}</TableCell>
                  ) : null}
                  <TableCell align="right">{formatMoney(item.unitPrice)}</TableCell>
                  {showTax ? (
                    <TableCell align="right">
                      {formatMoney(lineTax)}
                      <Typography variant="caption" display="block" color="text.secondary">
                        ({toNumber(item.gstRate)}%)
                      </Typography>
                    </TableCell>
                  ) : null}
                  <TableCell align="right">{formatMoney(item.lineTotal)}</TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </Paper>

      {canAct ? (
        <Paper sx={{ p: 2 }}>
          <Typography variant="h6" sx={{ mb: 2 }}>
            {t('common.share')}
          </Typography>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <TextField
              label={t('common.whatsapp')}
              value={sharePhone}
              onChange={(e) => setSharePhone(e.target.value)}
              placeholder="9198XXXXXXXX"
              error={Boolean(sharePhone) && !/^\d{10,15}$/.test(sharePhone.replace(/\D/g, ''))}
            />
            <Button
              variant="outlined"
              disabled={
                !/^\d{10,15}$/.test(sharePhone.replace(/\D/g, '')) || shareMutation.isPending
              }
              onClick={() =>
                shareMutation.mutate({ channel: 'WHATSAPP', recipient: sharePhone })
              }
            >
              {t('common.whatsapp')}
            </Button>
            <TextField
              label={t('common.email')}
              value={shareEmail}
              onChange={(e) => setShareEmail(e.target.value)}
              error={Boolean(shareEmail) && !/^\S+@\S+\.\S+$/.test(shareEmail)}
            />
            <Button
              variant="outlined"
              disabled={!/^\S+@\S+\.\S+$/.test(shareEmail) || shareMutation.isPending}
              onClick={() => shareMutation.mutate({ channel: 'EMAIL', recipient: shareEmail })}
            >
              {t('common.email')}
            </Button>
          </Stack>
          {shareLink ? (
            <Typography variant="body2" sx={{ mt: 1 }}>
              {/* BUG-519: a popup-blocked window.open left users with no way
                  to recover the link — it's now always shown as clickable. */}
              <a href={shareLink} target="_blank" rel="noreferrer">
                {shareLink}
              </a>
            </Typography>
          ) : null}
        </Paper>
      ) : null}
    </Stack>
  );
}
