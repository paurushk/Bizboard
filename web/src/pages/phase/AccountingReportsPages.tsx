import { useMemo, useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import * as api from '@/api/resources';
import { ErrorState, LoadingState } from '@/components/PageState';
import { formatMoney, toNumber } from '@/utils/money';
import { t } from '@/i18n';
import { triggerBlobDownload } from '@/utils/blob';
import {
  asRows,
  DataTable,
  PageShell,
  type Row,
} from '@/pages/phase/phaseShared';

export function ChartOfAccountsPage() {
  const query = useQuery({ queryKey: ['accounts'], queryFn: api.listAccounts });
  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  return (
    <PageShell title={t('phase.chartOfAccounts')} subtitle={t('phase.chartOfAccountsSubtitle')}>
      <DataTable
        rows={asRows(query.data)}
        empty="No accounts — enable accounting in Settings."
        columns={[
          { key: 'code', label: 'Code' },
          { key: 'name', label: 'Name' },
          { key: 'type', label: 'Type' },
          { key: 'isSystem', label: 'System', bool: true },
        ]}
      />
    </PageShell>
  );
}

function AccountingReportPage({
  title,
  report,
}: {
  title: string;
  report: 'trial-balance' | 'profit-and-loss' | 'balance-sheet' | 'books-health';
}) {
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [costCenter, setCostCenter] = useState('');
  const [downloading, setDownloading] = useState(false);
  const costCenters = useQuery({
    queryKey: ['cost-centers'],
    queryFn: api.listCostCenters,
    enabled: report === 'profit-and-loss',
  });
  const reportParams = useMemo((): Record<string, string> => {
    if (report === 'profit-and-loss') {
      const params: Record<string, string> = {};
      if (from) params.from = from;
      if (to) params.to = to;
      if (costCenter) params.cost_center = costCenter;
      return params;
    }
    return to ? { as_of: to } : {};
  }, [report, from, to, costCenter]);
  const q = useQuery({
    queryKey: ['accounting-report', report, from, to, costCenter],
    queryFn: () => api.getAccountingReport(report, reportParams),
  });
  const handleDownload = async () => {
    if (report === 'books-health') return;
    setDownloading(true);
    try {
      const { url } = await api.downloadAccountingReport(report, reportParams);
      triggerBlobDownload(await fetch(url).then((r) => r.blob()), `${report}.xlsx`);
      URL.revokeObjectURL(url);
    } finally {
      setDownloading(false);
    }
  };
  if (q.isLoading) return <LoadingState />;
  if (q.isError) return <ErrorState message={getErrorMessage(q.error)} error={q.error} onRetry={() => void q.refetch()} />;
  const data = q.data as Row;
  // UXW2B-019: prefer an array shape defensively even if a report ever sends rows
  // grouped by type ({ ASSET: [...], ... }) instead of a flat list — .map() on a
  // plain object crashes the page, so flatten rather than trusting the raw value.
  const rawRows = data.rows ?? data.items ?? data.accounts ?? [];
  const rowsArray: Row[] = Array.isArray(rawRows)
    ? (rawRows as Row[])
    : Object.values(rawRows as Record<string, Row[]>).flat();
  const rows = rowsArray.map((r) => ({
    ...r,
    code: r.code ?? r.accountCode,
    name: r.name ?? r.accountName,
    type: r.type ?? r.accountType,
    debit: r.debit,
    credit: r.credit,
    balance: r.balance,
  }));
  const ar = data.ar as Row | undefined;
  const ap = data.ap as Row | undefined;
  return (
    <PageShell
      title={title}
      actions={report !== 'books-health' ? (
        <Stack direction="row" spacing={1} alignItems="center">
          {report === 'profit-and-loss' ? (
            <>
              <TextField type="date" size="small" label="From" InputLabelProps={{ shrink: true }} value={from} onChange={(e) => setFrom(e.target.value)} />
              <TextField
                select
                size="small"
                label="Cost center"
                value={costCenter}
                onChange={(e) => setCostCenter(e.target.value)}
                sx={{ minWidth: 140 }}
              >
                <MenuItem value="">All</MenuItem>
                {(costCenters.data ?? []).map((cc) => (
                  <MenuItem key={String(cc.id)} value={String(cc.id)}>
                    {String(cc.code ?? cc.name ?? cc.id)}
                  </MenuItem>
                ))}
              </TextField>
            </>
          ) : null}
          <TextField type="date" size="small" label={report === 'profit-and-loss' ? 'To' : 'As of'} InputLabelProps={{ shrink: true }} value={to} onChange={(e) => setTo(e.target.value)} />
          <Button size="small" variant="outlined" disabled={downloading} onClick={() => void handleDownload()}>
            Download XLSX
          </Button>
        </Stack>
      ) : undefined}
    >
      {report === 'books-health' ? (
        <Stack spacing={2}>
          {(ar || ap) ? (
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              {ar ? (
                <Paper sx={{ p: 2, flex: 1 }}>
                  <Typography variant="subtitle2" gutterBottom>Accounts Receivable</Typography>
                  <Typography variant="body2">GL {formatMoney(toNumber(ar.gl as string | number))}</Typography>
                  <Typography variant="body2">Ledger {formatMoney(toNumber(ar.ledger as string | number))}</Typography>
                  <Chip size="small" label={ar.healthy ? 'Healthy' : 'Mismatch'} color={ar.healthy ? 'success' : 'warning'} sx={{ mt: 1 }} />
                </Paper>
              ) : null}
              {ap ? (
                <Paper sx={{ p: 2, flex: 1 }}>
                  <Typography variant="subtitle2" gutterBottom>Accounts Payable</Typography>
                  <Typography variant="body2">GL {formatMoney(toNumber(ap.gl as string | number))}</Typography>
                  <Typography variant="body2">Ledger {formatMoney(toNumber(ap.ledger as string | number))}</Typography>
                  <Chip size="small" label={ap.healthy ? 'Healthy' : 'Mismatch'} color={ap.healthy ? 'success' : 'warning'} sx={{ mt: 1 }} />
                </Paper>
              ) : null}
            </Stack>
          ) : null}
          {((data.alerts as Row[]) || []).length ? (
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
              {((data.alerts as Row[]) || []).map((alert) => (
                <Alert key={String(alert.code)} severity={alert.severity === 'error' ? 'error' : 'warning'}>
                  {String(alert.code)} — {String(alert.message)}
                </Alert>
              ))}
            </Stack>
          ) : <Alert severity="success">No books-health alerts.</Alert>}
        </Stack>
      ) : null}
      {report === 'trial-balance' ? (
        <Alert severity={(data.balanced as boolean) ? 'success' : 'warning'}>
          Total debit {formatMoney(toNumber(data.totalDebit as string | number))} · Total credit{' '}
          {formatMoney(toNumber(data.totalCredit as string | number))}
        </Alert>
      ) : null}
      {report === 'profit-and-loss' ? (
        <Alert severity="info">
          Income {formatMoney(toNumber(data.income as string | number))} · Expenses{' '}
          {formatMoney(toNumber(data.expenses as string | number))} · Net{' '}
          {formatMoney(toNumber((data.netProfit ?? data.net) as string | number))}
        </Alert>
      ) : null}
      {report === 'balance-sheet' ? (
        <Alert severity="info">
          Inventory GL {formatMoney(toNumber((data.inventoryGl ?? data.inventory_gl) as string | number))} ·
          Valuation {formatMoney(toNumber((data.inventoryValuation ?? data.inventory_valuation) as string | number))}
          {' — '}
          {String(data.inventoryNote ?? data.inventory_note ?? '')}
        </Alert>
      ) : null}
      <DataTable
        rows={rows}
        empty="No rows — post documents with accounting enabled."
        columns={[
          { key: 'code', label: 'Code' },
          { key: 'name', label: 'Account' },
          { key: 'type', label: 'Type' },
          { key: 'debit', label: 'Debit', money: true },
          { key: 'credit', label: 'Credit', money: true },
          { key: 'balance', label: 'Balance', money: true },
        ]}
      />
    </PageShell>
  );
}

export const TrialBalancePage = () => <AccountingReportPage title={t('phase.trialBalance')} report="trial-balance" />;
export const ProfitAndLossPage = () => <AccountingReportPage title={t('phase.profitAndLoss')} report="profit-and-loss" />;
export const BalanceSheetPage = () => <AccountingReportPage title={t('phase.balanceSheet')} report="balance-sheet" />;
export const BooksHealthPage = () => <AccountingReportPage title={t('phase.booksHealth')} report="books-health" />;
