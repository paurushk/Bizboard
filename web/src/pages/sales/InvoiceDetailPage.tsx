import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
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
import { Link as RouterLink, useParams } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import {
  cancelSalesInvoice,
  completeSalesInvoice,
  downloadInvoicePdf,
  getSalesInvoice,
  shareInvoice,
} from '@/api/resources';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { PdfStatusPoller } from '@/components/PdfStatusPoller';
import { StatusChip } from '@/components/StatusChip';
import { t } from '@/i18n';
import { formatMoney, toNumber } from '@/utils/money';
import { documentStatusTone, statusLabelKey } from '@/utils/status';

export function InvoiceDetailPage() {
  const { id } = useParams();
  const invoiceId = Number(id);
  const qc = useQueryClient();
  const [sharePhone, setSharePhone] = useState('');
  const [shareEmail, setShareEmail] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ['sales-invoice', invoiceId],
    queryFn: () => getSalesInvoice(invoiceId),
    enabled: Number.isFinite(invoiceId),
  });

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

  const shareMutation = useMutation({
    mutationFn: (payload: { channel: 'EMAIL' | 'WHATSAPP'; recipient: string }) =>
      shareInvoice(invoiceId, payload),
    onSuccess: (res) => {
      setMessage(res.shareLink ? `Share ready: ${res.shareLink}` : `Share ${res.status}`);
      if (res.shareLink) window.open(res.shareLink, '_blank');
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  if (query.isLoading) return <LoadingState />;
  if (query.isError) {
    return <ErrorState message={query.error.message} onRetry={() => void query.refetch()} />;
  }
  if (!query.data) return <EmptyState />;

  const inv = query.data;

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="h4">
          {inv.number ?? `Invoice #${inv.id}`}
        </Typography>
        <Button component={RouterLink} to="/sales/history">
          {t('common.back')}
        </Button>
      </Stack>
      {message ? <Alert severity="success">{message}</Alert> : null}
      {error ? <Alert severity="error">{error}</Alert> : null}

      <Paper sx={{ p: 2 }}>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems="center">
          <StatusChip tone={documentStatusTone(inv.status)} labelKey={statusLabelKey(inv.status)} />
          <Typography>{inv.customerName}</Typography>
          <Typography color="text.secondary">{inv.invoiceDate}</Typography>
          <Typography fontWeight={700}>{formatMoney(inv.grandTotal)}</Typography>
          <Stack direction="row" spacing={1} sx={{ ml: 'auto' }}>
            {inv.status === 'DRAFT' ? (
              <Button
                variant="contained"
                disabled={completeMutation.isPending}
                onClick={() => completeMutation.mutate()}
              >
                {t('common.complete')}
              </Button>
            ) : null}
            {inv.status === 'COMPLETED' ? (
              <Button
                color="error"
                variant="outlined"
                disabled={cancelMutation.isPending}
                onClick={() => cancelMutation.mutate()}
              >
                {t('common.cancel')}
              </Button>
            ) : null}
            {inv.pdfStatus === 'READY' || inv.status === 'COMPLETED' ? (
              <Button
                variant="outlined"
                onClick={() =>
                  void downloadInvoicePdf(inv.id).then((blob) => {
                    window.open(URL.createObjectURL(blob), '_blank');
                  })
                }
              >
                {t('common.download')}
              </Button>
            ) : null}
          </Stack>
        </Stack>
      </Paper>

      {inv.status === 'COMPLETED' ? <PdfStatusPoller invoiceId={inv.id} /> : null}

      <Paper sx={{ overflow: 'auto' }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>{t('nav.products')}</TableCell>
              <TableCell>{t('billing.qty')}</TableCell>
              <TableCell align="right">{t('billing.price')}</TableCell>
              <TableCell align="right">{t('common.total')}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {(inv.items ?? []).map((item) => (
              <TableRow key={item.id ?? `${item.product}-${item.quantity}`}>
                <TableCell>{item.productName ?? item.product}</TableCell>
                <TableCell>{toNumber(item.quantity)}</TableCell>
                <TableCell align="right">{formatMoney(item.unitPrice)}</TableCell>
                <TableCell align="right">{formatMoney(item.lineTotal)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Paper>

      {inv.status === 'COMPLETED' || inv.status === 'RETURNED' ? (
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
            />
            <Button
              variant="outlined"
              disabled={!sharePhone || shareMutation.isPending}
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
            />
            <Button
              variant="outlined"
              disabled={!shareEmail || shareMutation.isPending}
              onClick={() => shareMutation.mutate({ channel: 'EMAIL', recipient: shareEmail })}
            >
              {t('common.email')}
            </Button>
          </Stack>
        </Paper>
      ) : null}
    </Stack>
  );
}
