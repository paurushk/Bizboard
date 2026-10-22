import { useMemo, useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Link from '@mui/material/Link';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import * as api from '@/api/resources';
import { ErrorState, LoadingState } from '@/components/PageState';
import { formatMoney, toNumber } from '@/utils/money';
import { t, tOptional } from '@/i18n';
import { useAuth } from '@/auth/AuthContext';
import { canExport } from '@/utils/permissions';
import { AccountingBackfillBanner, useBooksState } from '@/components/AccountingBackfillBanner';
import { dateRangeForPreset } from '@/components/HistoryFilterBar';
import { trialBalanceRowPath } from '@/pages/reports/ledgerLinks';
import { BalanceSheetView } from '@/pages/reports/statements/BalanceSheetView';
import { ProfitLossView } from '@/pages/reports/statements/ProfitLossView';
import {
  DataTable,
  PageShell,
  type Row,
} from '@/pages/phase/phaseShared';

function AccountingReportPage({
  title,
  report,
}: {
  title: string;
  report: 'trial-balance' | 'books-health';
}) {
  const { user } = useAuth();
  const [to, setTo] = useState('');
  const [downloading, setDownloading] = useState(false);
  const [dlError, setDlError] = useState<string | null>(null);
  const reportParams = useMemo((): Record<string, string> => (to ? { as_of: to } : {}), [to]);
  const q = useQuery({
    queryKey: ['accounting-report', report, to],
    queryFn: () => api.getAccountingReport(report, reportParams),
    // F3-069: keep the prior report on screen while a date change
    // refetches, so the page does not flash a full-height spinner each edit.
    placeholderData: keepPreviousData,
  });
  const handleDownload = async () => {
    if (report === 'books-health') return;
    setDownloading(true);
    setDlError(null);
    try {
      const { url } = await api.downloadAccountingReport(report, reportParams);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${report}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10_000);
    } catch (err) {
      setDlError(getErrorMessage(err));
    } finally {
      setDownloading(false);
    }
  };
  const books = useBooksState();
  const money = (value: unknown) => (books.trusted ? formatMoney(toNumber(value as string | number)) : '—');
  if (q.isLoading) return <LoadingState />;
  if (q.isError && !q.data) return <ErrorState message={getErrorMessage(q.error)} error={q.error} onRetry={() => void q.refetch()} />;
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
  // RPT-01: the trial balance ends with its own totals, and untrusted books mask the table like the banner.
  const tableRows = report === 'trial-balance' && rows.length
    ? [...rows, { id: 'total', code: '', name: t('statements.total'), type: '', debit: data.totalDebit, credit: data.totalCredit, balance: '' }]
    : rows;
  const moneyColumn = (key: string, label: string) =>
    books.trusted ? { key, label, money: true } : { key, label, render: () => '—' };
  // The ledger lines behind a trial balance row: this financial year up to the as-of date (or today).
  const ledgerRange = dateRangeForPreset('currentFY');
  const ar = data.ar as Row | undefined;
  const ap = data.ap as Row | undefined;
  return (
    <PageShell
      title={title}
      actions={report !== 'books-health' ? (
        <Stack direction="row" spacing={1} alignItems="center">
          <TextField type="date" size="small" label={t('statements.asOf')} InputLabelProps={{ shrink: true }} value={to} onChange={(e) => setTo(e.target.value)} />
          {canExport(user) ? (
            <Button size="small" variant="outlined" disabled={downloading} onClick={() => void handleDownload()}>
              {t('sweep2.downloadXlsx')}
            </Button>
          ) : null}
          {dlError ? <ErrorState message={dlError} error={new Error(dlError)} /> : null}
        </Stack>
      ) : undefined}
    >
      <AccountingBackfillBanner />
      {report === 'books-health' ? (
        <Stack spacing={2}>
          {(ar || ap) ? (
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              {ar ? (
                <Paper sx={{ p: 2, flex: 1 }}>
                  <Typography variant="subtitle2" gutterBottom>{t('sweep2.accountsReceivable')}</Typography>
                  <Typography variant="body2">{t('statements.gl')} {money(ar.gl)}</Typography>
                  <Typography variant="body2">{t('statements.ledger')} {money(ar.ledger)}</Typography>
                  <Chip size="small" label={ar.healthy ? t('statements.healthy') : t('statements.mismatch')} color={ar.healthy ? 'success' : 'warning'} sx={{ mt: 1 }} />
                </Paper>
              ) : null}
              {ap ? (
                <Paper sx={{ p: 2, flex: 1 }}>
                  <Typography variant="subtitle2" gutterBottom>{t('sweep2.accountsPayable')}</Typography>
                  <Typography variant="body2">{t('statements.gl')} {money(ap.gl)}</Typography>
                  <Typography variant="body2">{t('statements.ledger')} {money(ap.ledger)}</Typography>
                  <Chip size="small" label={ap.healthy ? t('statements.healthy') : t('statements.mismatch')} color={ap.healthy ? 'success' : 'warning'} sx={{ mt: 1 }} />
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
          ) : <Alert severity="success">{t('sweep2.noBooksHealthAlerts')}</Alert>}
        </Stack>
      ) : null}
      {report === 'trial-balance' ? (
        <Alert severity={(data.balanced as boolean) ? 'success' : 'warning'}>
          {t('statements.totalDebit')} {money(data.totalDebit)} · {t('statements.totalCredit')} {money(data.totalCredit)}
        </Alert>
      ) : null}
      {report === 'trial-balance' && ((data.ledgerGaps as Row[]) || []).length ? (
        // WP-F3: flag-gated postings that are off for this company are not in these totals.
        <Alert severity="info" data-testid="ledger-gaps">
          <Typography variant="subtitle2">{t('statements.ledgerGapsTitle')}</Typography>
          <Typography variant="body2">{t('statements.ledgerGapsBody')}</Typography>
          <ul style={{ margin: 0, paddingLeft: 20 }}>
            {((data.ledgerGaps as Row[]) || []).map((gap) => (
              <li key={String(gap.flag)}>
                <Typography variant="body2">
                  {tOptional(`statements.ledgerGap_${String(gap.flag)}`) ?? String(gap.note || gap.flag)}
                </Typography>
              </li>
            ))}
          </ul>
        </Alert>
      ) : null}
      <DataTable
        rows={tableRows}
        empty={t('statements.noRows')}
        columns={[
          {
            key: 'code',
            label: t('statements.code'),
            // RPT-11: an account code opens the ledger lines behind it.
            render: (row: Row) => {
              const link = report === 'trial-balance' ? trialBalanceRowPath(row.accountId, ledgerRange.dateFrom, to || ledgerRange.dateTo) : null;
              return link ? <Link component={RouterLink} to={link}>{String(row.code ?? '')}</Link> : String(row.code ?? '—');
            },
          },
          { key: 'name', label: t('statements.account') },
          { key: 'type', label: t('statements.type') },
          moneyColumn('debit', t('statements.debit')),
          moneyColumn('credit', t('statements.credit')),
          moneyColumn('balance', t('statements.balance')),
        ]}
      />
    </PageShell>
  );
}

export const TrialBalancePage = () => <AccountingReportPage title={t('phase.trialBalance')} report="trial-balance" />;
export const ProfitAndLossPage = () => <ProfitLossView title={t('phase.profitAndLoss')} />;
export const BalanceSheetPage = () => <BalanceSheetView title={t('phase.balanceSheet')} />;
export const BooksHealthPage = () => <AccountingReportPage title={t('phase.booksHealth')} report="books-health" />;
