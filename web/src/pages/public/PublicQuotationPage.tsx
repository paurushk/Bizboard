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
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { downloadPublicQuotationPdf, getPublicQuotation } from '@/api/resources';
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

/** A shared quotation, opened from a link without signing in. */
export function PublicQuotationPage() {
  const { token = '' } = useParams();
  const query = useQuery({
    queryKey: ['public-quotation', token],
    queryFn: () => getPublicQuotation(token),
    enabled: Boolean(token),
    retry: false,
  });

  if (query.isLoading) {
    return (
      <Stack minHeight="100vh" alignItems="center" justifyContent="center">
        <Typography>{t('common.loading')}</Typography>
      </Stack>
    );
  }

  if (query.isError || !query.data) {
    const gone = axios.isAxiosError(query.error) && query.error.response?.status === 410;
    return (
      <Stack minHeight="100vh" alignItems="center" justifyContent="center" p={2}>
        <Alert severity="warning">
          {gone ? t('phase1.publicQuotationExpired') : t('phase1.publicQuotationUnavailable')}
        </Alert>
      </Stack>
    );
  }

  const data = query.data;
  const billTo = asRecord(data.billTo ?? data.bill_to);
  const totals = asRecord(data.totals);
  const lines = (Array.isArray(data.lines) ? data.lines : []) as Array<Record<string, unknown>>;
  const validUntil = pick(data, 'validUntil', 'valid_until');
  const number = pick(data, 'number') || 'quotation';

  return (
    <Box minHeight="100vh" sx={{ bgcolor: 'grey.100', p: { xs: 2, sm: 4 } }}>
      <Paper sx={{ maxWidth: 880, mx: 'auto', p: { xs: 2, sm: 3 } }}>
        <Stack spacing={2}>
          <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" spacing={1}>
            <Typography variant="h5" component="h1">
              {pick(data, 'sellerName', 'seller_name')}
            </Typography>
            <Box>
              <Typography variant="h6">{pick(data, 'number') || '—'}</Typography>
              <Typography variant="body2" color="text.secondary">
                {pick(data, 'quotationDate', 'quotation_date')}
              </Typography>
              {validUntil ? (
                <Typography variant="body2" fontWeight={700}>
                  {t('phase1.publicQuotationValidUntil', { date: validUntil })}
                </Typography>
              ) : null}
            </Box>
          </Stack>

          <Box>
            <Typography variant="subtitle2">{t('invoiceDetail.billTo')}</Typography>
            <Typography>{pick(billTo, 'name')}</Typography>
            <Typography variant="body2">{pick(billTo, 'address')}</Typography>
          </Box>

          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('common.product')}</TableCell>
                <TableCell align="right">{t('common.qty')}</TableCell>
                <TableCell align="right">{t('invoiceDetail.rate')}</TableCell>
                <TableCell align="right">{t('common.total')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {lines.map((line, idx) => (
                <TableRow key={idx}>
                  <TableCell>{pick(line, 'name')}</TableCell>
                  <TableCell align="right">{pick(line, 'qty')}</TableCell>
                  <TableCell align="right">{formatMoney(toNumber(line.rate as string | number))}</TableCell>
                  <TableCell align="right">{formatMoney(toNumber(line.amount as string | number))}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          <Stack direction="row" justifyContent="flex-end">
            <Typography variant="h6">
              {t('common.total')} {formatMoney(toNumber((totals.grandTotal ?? totals.grand_total) as string | number))}
            </Typography>
          </Stack>

          {pick(data, 'notes') ? <Typography variant="body2">{pick(data, 'notes')}</Typography> : null}
          {pick(data, 'terms') ? (
            <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: 'pre-wrap' }}>
              {pick(data, 'terms')}
            </Typography>
          ) : null}

          <Stack direction="row" spacing={1}>
            <Button
              variant="contained"
              onClick={() => void downloadPublicQuotationPdf(token).then((blob) => triggerBlobDownload(blob, `${number}.pdf`))}
            >
              {t('phase1.publicQuotationDownload')}
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
