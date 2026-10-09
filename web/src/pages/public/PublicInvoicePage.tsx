import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { useState } from 'react';
import { downloadPublicInvoicePdf, getPublicInvoice, payPublicInvoice } from '@/api/resources';
import { getErrorMessage } from '@/api/client';
import { t } from '@/i18n';
import { triggerBlobDownload } from '@/utils/blob';
import { formatMoney, toNumber } from '@/utils/money';

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? (value as Record<string, unknown>) : {};
}

function pick(row: Record<string, unknown>, ...keys: string[]): string {
  for (const key of keys) {
    const value = row[key];
    if (value != null && String(value).trim()) return String(value);
  }
  return '';
}

export function PublicInvoicePage() {
  const { token = '' } = useParams();
  const navigate = useNavigate();
  const [payError, setPayError] = useState<string | null>(null);
  const query = useQuery({
    queryKey: ['public-invoice', token],
    queryFn: () => getPublicInvoice(token),
    enabled: Boolean(token),
    retry: false,
  });

  const download = async () => {
    const blob = await downloadPublicInvoicePdf(token);
    const number = pick(asRecord(query.data), 'number') || 'invoice';
    triggerBlobDownload(blob, `${number}.pdf`);
  };

  if (query.isLoading) {
    return (
      <Stack minHeight="100vh" alignItems="center" justifyContent="center">
        <Typography>{t('common.loading')}</Typography>
      </Stack>
    );
  }

  if (query.isError || !query.data) {
    return (
      <Stack minHeight="100vh" alignItems="center" justifyContent="center" p={2}>
        <Alert severity="warning">{t('invoiceDetail.publicUnavailable')}</Alert>
      </Stack>
    );
  }

  const data = query.data;
  const billTo = asRecord(data.billTo ?? data.bill_to);
  const shipTo = asRecord(data.shipTo ?? data.ship_to);
  const totals = asRecord(data.totals);
  const lines = (Array.isArray(data.lines) ? data.lines : Array.isArray(data.items) ? data.items : []) as Array<
    Record<string, unknown>
  >;
  const status = pick(data, 'status').toUpperCase();
  const unpaid = toNumber((data.unpaid ?? data.balance ?? totals.unpaid) as string | number);
  const grand = pick(totals, 'grandTotal', 'grand_total') || pick(data, 'grandTotal', 'grand_total');
  const paidLabel =
    status === 'CANCELLED'
      ? t('invoiceDetail.cancelledLabel')
      : unpaid <= 0.01
        ? t('invoiceDetail.paidLabel')
        : t('invoiceDetail.unpaidLabel');

  return (
    <Box minHeight="100vh" sx={{ bgcolor: 'grey.100', p: { xs: 2, sm: 4 } }}>
      <Paper sx={{ maxWidth: 880, mx: 'auto', p: { xs: 2, sm: 3 } }}>
        <Stack spacing={2}>
          <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" spacing={1}>
            <Box>
              <Typography variant="h5" component="h1">
                {pick(data, 'sellerName', 'seller_name') || t('invoiceDetail.seller')}
              </Typography>
              {pick(data, 'sellerGstin', 'seller_gstin') ? (
                <Typography variant="body2" color="text.secondary">
                  {pick(data, 'sellerGstin', 'seller_gstin')}
                </Typography>
              ) : null}
            </Box>
            <Box>
              <Typography variant="h6">{pick(data, 'number') || '—'}</Typography>
              <Typography variant="body2" color="text.secondary">
                {pick(data, 'invoiceDate', 'invoice_date')}
              </Typography>
              <Typography fontWeight={700}>{paidLabel}</Typography>
            </Box>
          </Stack>

          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <Box flex={1}>
              <Typography variant="subtitle2">{t('invoiceDetail.billTo')}</Typography>
              <Typography>{pick(billTo, 'name') || pick(data, 'customerName', 'customer_name')}</Typography>
              <Typography variant="body2">{pick(billTo, 'address') || pick(data, 'customerAddress')}</Typography>
              {pick(billTo, 'gstin') ? <Typography variant="body2">{pick(billTo, 'gstin')}</Typography> : null}
              {pick(data, 'placeOfSupply', 'place_of_supply') ? (
                <Typography variant="body2" color="text.secondary">
                  {pick(data, 'placeOfSupply', 'place_of_supply')}
                </Typography>
              ) : null}
            </Box>
            <Box flex={1}>
              <Typography variant="subtitle2">{t('invoiceDetail.shipTo')}</Typography>
              <Typography>{pick(shipTo, 'name')}</Typography>
              <Typography variant="body2">{pick(shipTo, 'address')}</Typography>
            </Box>
          </Stack>

          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('common.product')}</TableCell>
                <TableCell>{t('invoiceDetail.hsn')}</TableCell>
                <TableCell align="right">{t('common.qty')}</TableCell>
                <TableCell align="right">{t('invoiceDetail.rate')}</TableCell>
                <TableCell align="right">{t('billing.tax')}</TableCell>
                <TableCell align="right">{t('common.total')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {lines.map((line, idx) => (
                <TableRow key={idx}>
                  <TableCell>{pick(line, 'name', 'productName', 'description')}</TableCell>
                  <TableCell>{pick(line, 'hsn', 'hsnCode') || '—'}</TableCell>
                  <TableCell align="right">{pick(line, 'qty', 'quantity')}</TableCell>
                  <TableCell align="right">{formatMoney(toNumber((line.rate ?? line.unitPrice) as string | number))}</TableCell>
                  <TableCell align="right">{formatMoney(toNumber(line.tax as string | number))}</TableCell>
                  <TableCell align="right">{formatMoney(toNumber((line.amount ?? line.lineTotal) as string | number))}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          <Stack direction="row" justifyContent="flex-end">
            <Typography variant="h6">
              {t('common.total')} {formatMoney(grand || 0)}
            </Typography>
          </Stack>

          {payError ? <Alert severity="warning">{payError}</Alert> : null}
          <Stack direction="row" spacing={1}>
            {status === 'COMPLETED' && unpaid > 0.01 ? (
              <Button
                variant="contained"
                onClick={() => {
                  setPayError(null);
                  void payPublicInvoice(token)
                    .then((res) => {
                      if (res.path.startsWith('/pay/')) navigate(res.path);
                      else setPayError(t('invoiceDetail.publicUnavailable'));
                    })
                    .catch((err) => setPayError(getErrorMessage(err)));
                }}
              >
                {t('invoiceDetail.payNow')}
              </Button>
            ) : null}
            <Button variant="outlined" onClick={() => void download()}>
              {t('invoiceDetail.downloadPdf')}
            </Button>
            <Button variant="outlined" onClick={() => window.print()}>
              {t('invoiceDetail.printPdf')}
            </Button>
          </Stack>
        </Stack>
      </Paper>
    </Box>
  );
}
