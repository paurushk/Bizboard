import { useState } from 'react';
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
import { useMutation, useQuery } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { exportReport, getPurchaseRegister } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';
import { formatMoney } from '@/utils/money';
import { canExport } from '@/utils/permissions';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';

// F3-006: a column is a money column by its name, not by its value type.
const MONEY_COL = /(amount|total|value|balance|price|net|gross|payable|receivable|outstanding|discount|freight|charge|cess|tcs|tds|paid|due|mrp|cogs|profit|margin)/i;
const NOT_MONEY_COL = /(rate|percent|qty|quantity|count|hsn|sac|_?code$|number|invoices?$|bills?$|id$)/i;
function isMoneyColumn(key: string): boolean {
  return MONEY_COL.test(key) && !NOT_MONEY_COL.test(key);
}

function downloadBlobUrl(url: string, filename: string) {
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

function formatColumnHeader(key: string): string {
  const customMap: Record<string, string> = {
    invoice_number: 'Invoice No.',
    invoice_date: 'Date',
    bill_number: 'Bill No.',
    customer_name: 'Customer',
    supplier_name: 'Supplier',
    grand_total: 'Total Amount',
    taxable_amount: 'Taxable Amt',
    cgst_amount: 'CGST',
    sgst_amount: 'SGST',
    igst_amount: 'IGST',
    total_tax: 'Total Tax',
    net_total: 'Net Total',
    due_date: 'Due Date',
    payment_status: 'Payment Status',
    party_gstin: 'GSTIN',
  };
  if (customMap[key]) return customMap[key];
  return key
    .replace(/_/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function PurchaseReportPage() {
  const { user } = useAuth();
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const query = useQuery({
    queryKey: ['purchase-register', dateFrom, dateTo],
    queryFn: () =>
      getPurchaseRegister({ dateFrom: dateFrom || undefined, dateTo: dateTo || undefined }),
  });

  const exportMutation = useMutation({
    mutationFn: () =>
      exportReport('purchases', { dateFrom: dateFrom || undefined, dateTo: dateTo || undefined }),
    onSuccess: (r) => downloadBlobUrl(r.url, 'purchase-register.csv'),
  });

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1}>
        <Typography variant="h4">{t('nav.purchaseReports')}</Typography>
        <Stack direction="row" spacing={1} alignItems="center">
          <TextField
            type="date"
            size="small"
            label={t('common.dateFrom')}
            InputLabelProps={{ shrink: true }}
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
          />
          <TextField
            type="date"
            size="small"
            label={t('common.dateTo')}
            InputLabelProps={{ shrink: true }}
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
          />
          {canExport(user) ? (
            <Button
              variant="outlined"
              disabled={exportMutation.isPending}
              onClick={() => exportMutation.mutate()}
            >
              {t('common.export')}
            </Button>
          ) : null}
        </Stack>
      </Stack>
      {exportMutation.isError ? (
        <HelpErrorAlert error={exportMutation.error} />
      ) : null}
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {query.data?.rows?.length === 0 ? <EmptyState description={t('empty.reports')} /> : null}
      {query.data && query.data.rows.length > 0 ? (
        <Paper sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                {Object.keys(query.data.rows[0]).map((key) => (
                  <TableCell key={key}>{formatColumnHeader(key)}</TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {query.data.rows.map((row, idx) => (
                <TableRow key={idx}>
                  {Object.entries(row).map(([key, value]) => (
                    <TableCell key={key}>
                      {/* F3-006: only money-format columns whose *name* is a money field —
                          "any numeric value" also caught hsn_code / gst_rate / quantity. */}
                      {isMoneyColumn(key) && (typeof value === 'number' || typeof value === 'string')
                        ? formatMoney(value as string | number)
                        : String(value ?? '—')}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}
    </Stack>
  );
}
