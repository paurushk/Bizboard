import { useState } from 'react';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { apiClient, getErrorMessage, unwrapData } from '@/api/client';
import { DisclaimerBanner, KpiStat, PageHeader } from '@/components/insights';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { VirtualizedTable } from '@/components/VirtualizedTable';
import { t } from '@/i18n';
import { formatMoney } from '@/utils/money';

type ExposureRow = {
  invoiceId?: number;
  invoiceNumber?: string;
  invoiceDate?: string;
  hsn?: string;
  billedRate?: string;
  expectedRate?: string;
  taxDelta?: string;
  invoice_number?: string;
  invoice_date?: string;
  billed_rate?: string;
  expected_rate?: string;
  tax_delta?: string;
};

type Exposure = {
  count?: number;
  estimatedExposure?: string;
  estimated_exposure?: string;
  disclaimer?: string;
  rows?: ExposureRow[];
};

async function fetchExposure(dateFrom: string, dateTo: string) {
  const { data } = await apiClient.get('/reports/gst-rate-exposure/', {
    params: { date_from: dateFrom, date_to: dateTo },
  });
  return unwrapData<Exposure>(data);
}

export function GstRateExposurePage() {
  // F3-061: default to the current Indian FY start / local today, not a fixed
  // literal date and a UTC "to".
  const [from, setFrom] = useState(() => {
    const now = new Date();
    const fyYear = now.getMonth() >= 3 ? now.getFullYear() : now.getFullYear() - 1;
    return `${fyYear}-04-01`;
  });
  const [to, setTo] = useState(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  });
  const query = useQuery({
    queryKey: ['gst-rate-exposure', from, to],
    queryFn: () => fetchExposure(from, to),
  });
  const rows = query.data?.rows ?? [];
  const exposure = query.data?.estimatedExposure ?? query.data?.estimated_exposure ?? '0';

  return (
    <Stack spacing={2}>
      <PageHeader title={t('nav.gstRateExposure')} />
      <DisclaimerBanner>{query.data?.disclaimer || t('ims.rateDisclaimer')}</DisclaimerBanner>
      <Stack direction="row" spacing={2}>
        <TextField
          label={t('common.from')}
          type="date"
          size="small"
          value={from}
          onChange={(e) => setFrom(e.target.value)}
          InputLabelProps={{ shrink: true }}
        />
        <TextField
          label={t('common.to')}
          type="date"
          size="small"
          value={to}
          onChange={(e) => setTo(e.target.value)}
          InputLabelProps={{ shrink: true }}
        />
      </Stack>
      <KpiStat label={t('ims.estimatedExposure')} value={exposure} money dense />
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {!query.isLoading && rows.length === 0 ? <EmptyState description={t('ims.rateScanEmpty')} /> : null}
      {rows.length > 0 ? (
        // F3-017: the date range defaults to the whole fiscal year to date —
        // window the DOM rows instead of rendering them all at once.
        <Paper sx={{ overflow: 'hidden' }}>
          <VirtualizedTable rowCount={rows.length} rowHeight={52}>
            {({ rows: virtualRows, totalSize, measureElement }) => (
              <Table size="small" stickyHeader>
                <TableHead>
                  <TableRow>
                    <TableCell>{t('ims.invoice')}</TableCell>
                    <TableCell>HSN</TableCell>
                    <TableCell align="right">{t('ims.billedRate')}</TableCell>
                    <TableCell align="right">{t('ims.expectedRate')}</TableCell>
                    <TableCell align="right">{t('ims.taxDelta')}</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {virtualRows.length ? (
                    <TableRow style={{ height: virtualRows[0].start, padding: 0, border: 0 }} aria-hidden>
                      <TableCell style={{ padding: 0, border: 0 }} colSpan={5} />
                    </TableRow>
                  ) : null}
                  {virtualRows.map((vRow) => {
                    const row = rows[vRow.index];
                    return (
                      <TableRow
                        key={`${row.invoiceId}-${row.hsn}-${row.invoiceDate || row.invoice_date}`}
                        data-index={vRow.index}
                        ref={measureElement}
                      >
                        <TableCell>
                          {row.invoiceNumber || row.invoice_number}
                          <Typography variant="caption" display="block" color="text.secondary">
                            {row.invoiceDate || row.invoice_date}
                          </Typography>
                        </TableCell>
                        <TableCell>{row.hsn}</TableCell>
                        <TableCell align="right">{row.billedRate || row.billed_rate}</TableCell>
                        <TableCell align="right">{row.expectedRate || row.expected_rate}</TableCell>
                        <TableCell align="right">{formatMoney(row.taxDelta || row.tax_delta)}</TableCell>
                      </TableRow>
                    );
                  })}
                  {virtualRows.length ? (
                    <TableRow
                      style={{ height: totalSize - virtualRows[virtualRows.length - 1].end, padding: 0, border: 0 }}
                      aria-hidden
                    >
                      <TableCell style={{ padding: 0, border: 0 }} colSpan={5} />
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>
            )}
          </VirtualizedTable>
        </Paper>
      ) : null}
    </Stack>
  );
}
