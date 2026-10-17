import { useMemo, useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Tab from '@mui/material/Tab';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TablePagination from '@mui/material/TablePagination';
import TableRow from '@mui/material/TableRow';
import Tabs from '@mui/material/Tabs';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { Link as RouterLink, useSearchParams } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { exportLedgerDayBook, getDayBook, getLedgerDayBook, listAccounts } from '@/api/resources';
import { AccountSelect } from '@/components/accounting/AccountSelect';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { PageTitle } from '@/contextHelp';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { t } from '@/i18n';
import { asRows, DataTable } from '@/pages/phase/phaseShared';
import { formatMoney, toNumber } from '@/utils/money';
import { todayIso } from '@/components/billing';

function shiftDay(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + days);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function saveBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export function DayBookPage() {
  const [tab, setTab] = useState<'ledger' | 'cash'>('ledger');
  return (
    <Stack spacing={2}>
      <PageTitle>{t('nav.dayBook')}</PageTitle>
      <Tabs value={tab} onChange={(_e, v) => setTab(v)} aria-label={t('nav.dayBook')}>
        <Tab value="ledger" label={t('dayBook.tabLedger')} />
        <Tab value="cash" label={t('dayBook.tabCash')} />
      </Tabs>
      {tab === 'ledger' ? <LedgerTab /> : <CashSummaryTab />}
    </Stack>
  );
}

function LedgerTab() {
  const [search, setSearch] = useSearchParams();
  const today = todayIso();
  const [dateFrom, setDateFrom] = useState(search.get('date') ?? today);
  const [dateTo, setDateTo] = useState(search.get('date') ?? today);
  const [voucherType, setVoucherType] = useState('');
  const [account, setAccount] = useState(search.get('account') ?? '');
  const [text, setText] = useState('');
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(50);
  const [error, setError] = useState('');
  const q = useDebouncedValue(text.trim(), 300);
  const accounts = useQuery({ queryKey: ['accounts'], queryFn: listAccounts });
  const params = useMemo(() => {
    const p: Record<string, string> = { date_from: dateFrom, date_to: dateTo };
    if (voucherType) p.voucher_type = voucherType;
    if (account) p.account = account;
    if (q) p.q = q;
    return p;
  }, [dateFrom, dateTo, voucherType, account, q]);
  const query = useQuery({
    queryKey: ['day-book-ledger', params, page, pageSize],
    queryFn: () => getLedgerDayBook({ ...params, page: page + 1, page_size: pageSize }),
    // Moving to another day keeps the old rows on screen until the new ones arrive.
    placeholderData: keepPreviousData,
    retry: false,
  });
  const singleDay = dateFrom === dateTo;
  const goTo = (from: string, to: string) => {
    setDateFrom(from);
    setDateTo(to);
    setPage(0);
    const next = new URLSearchParams(search);
    if (from === to) next.set('date', from);
    else next.delete('date');
    setSearch(next, { replace: true });
  };
  const runExport = async (file: 'csv' | 'xlsx') => {
    try {
      saveBlob(await exportLedgerDayBook(params, file), `day-book.${file}`);
    } catch (e) {
      setError(getErrorMessage(e));
    }
  };

  if (query.isLoading) return <LoadingState />;
  if (query.isError && !query.data) {
    return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  }
  const data = query.data;
  const rows = data?.results ?? [];
  const unbalancedDays = (data?.dayTotals ?? []).filter((d) => !d.balanced);

  return (
    <Stack spacing={2}>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} alignItems={{ md: 'center' }}>
        {singleDay ? <Button onClick={() => goTo(shiftDay(dateFrom, -1), shiftDay(dateTo, -1))}>{t('dayBook.previousDay')}</Button> : null}
        <TextField type="date" size="small" label={t('phase.journalFrom')} InputLabelProps={{ shrink: true }} value={dateFrom} onChange={(e) => goTo(e.target.value, dateTo < e.target.value ? e.target.value : dateTo)} />
        <TextField type="date" size="small" label={t('phase.journalTo')} InputLabelProps={{ shrink: true }} value={dateTo} onChange={(e) => goTo(dateFrom > e.target.value ? e.target.value : dateFrom, e.target.value)} />
        {singleDay ? <Button onClick={() => goTo(shiftDay(dateFrom, 1), shiftDay(dateTo, 1))}>{t('dayBook.nextDay')}</Button> : null}
        <TextField select size="small" label={t('dayBook.voucherType')} value={voucherType} onChange={(e) => { setVoucherType(e.target.value); setPage(0); }} sx={{ minWidth: 180 }}>
          <MenuItem value="">{t('dayBook.allTypes')}</MenuItem>
          {(data?.voucherTypes ?? []).map((v) => <MenuItem key={v.key} value={v.key}>{v.label}</MenuItem>)}
        </TextField>
        <AccountSelect accounts={accounts.data} label={t('phase.journalAccount')} value={account} onChange={(id) => { setAccount(id); setPage(0); }} size="small" sx={{ minWidth: 220 }} />
        <TextField size="small" label={t('dayBook.search')} value={text} onChange={(e) => { setText(e.target.value); setPage(0); }} sx={{ flex: 1 }} />
      </Stack>
      <Stack direction="row" spacing={1}>
        <Button onClick={() => void runExport('csv')}>{t('phase.journalExportCsv')}</Button>
        <Button onClick={() => void runExport('xlsx')}>{t('phase.journalExportXlsx')}</Button>
      </Stack>
      {error ? <HelpErrorAlert message={error} /> : null}
      {data ? (
        <Alert severity={data.tieOut.ties ? 'success' : 'error'} data-testid="day-book-tie-out">
          {data.tieOut.ties ? t('dayBook.tiesOut') : t('dayBook.doesNotTie', { debit: formatMoney(toNumber(data.tieOut.trialBalanceDebit)), credit: formatMoney(toNumber(data.tieOut.trialBalanceCredit)) })}
        </Alert>
      ) : null}
      {unbalancedDays.length > 0 ? (
        <Alert severity="error">{t('dayBook.unbalancedDays', { days: unbalancedDays.map((d) => d.date).join(', ') })}</Alert>
      ) : null}
      {rows.length === 0 ? (
        <EmptyState description={t('dayBook.empty')} />
      ) : (
        <Paper variant="outlined" sx={{ overflowX: 'auto' }}>
          <Table size="small" aria-label={t('dayBook.tabLedger')}>
            <TableHead>
              <TableRow>
                <TableCell>{t('common.date')}</TableCell>
                <TableCell>{t('common.number')}</TableCell>
                <TableCell>{t('common.type')}</TableCell>
                <TableCell>{t('phase.journalAccount')}</TableCell>
                <TableCell>{t('dayBook.party')}</TableCell>
                <TableCell align="right">{t('phase.journalDebit')}</TableCell>
                <TableCell align="right">{t('phase.journalCredit')}</TableCell>
                <TableCell>{t('phase.journalNarration')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.id} hover>
                  <TableCell>{r.date}</TableCell>
                  <TableCell>
                    {r.sourcePath ? <RouterLink to={r.sourcePath}>{r.voucher}</RouterLink> : r.voucher}
                    {r.status === 'REVERSED' ? <Chip size="small" label={t('status.REVERSED')} sx={{ ml: 0.5 }} /> : null}
                  </TableCell>
                  <TableCell>{r.voucherTypeLabel}</TableCell>
                  <TableCell>{r.accountCode} {r.accountName}</TableCell>
                  <TableCell>{r.party}</TableCell>
                  <TableCell align="right">{toNumber(r.debit) > 0 ? formatMoney(toNumber(r.debit)) : ''}</TableCell>
                  <TableCell align="right">{toNumber(r.credit) > 0 ? formatMoney(toNumber(r.credit)) : ''}</TableCell>
                  <TableCell>{r.narration}</TableCell>
                </TableRow>
              ))}
              {data ? (
                <TableRow data-testid="day-book-totals">
                  <TableCell colSpan={5}><strong>{t('phase.journalTotal')}</strong></TableCell>
                  <TableCell align="right"><strong>{formatMoney(toNumber(data.totals.debit))}</strong></TableCell>
                  <TableCell align="right"><strong>{formatMoney(toNumber(data.totals.credit))}</strong></TableCell>
                  <TableCell>{data.totals.balanced ? t('phase.journalBalanced') : t('phase.journalNotBalanced')}</TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
          <TablePagination
            component="div" count={data?.count ?? 0} page={page} rowsPerPage={pageSize} rowsPerPageOptions={[50, 100, 200]}
            onPageChange={(_e, p) => setPage(p)} onRowsPerPageChange={(e) => { setPageSize(Number(e.target.value)); setPage(0); }}
          />
        </Paper>
      )}
    </Stack>
  );
}

function CashSummaryTab() {
  const [onDate, setOnDate] = useState(todayIso());
  const query = useQuery({
    queryKey: ['day-book', onDate],
    queryFn: () => getDayBook({ date: onDate }),
    placeholderData: keepPreviousData,
    retry: false,
  });
  const rows = useMemo(() => (query.data?.rows as Record<string, unknown>[]) ?? [], [query.data]);
  if (query.isLoading) return <LoadingState />;
  if (query.isError && !query.data) {
    return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  }
  const adjustments = (query.data?.adjustments ?? {}) as Record<string, string>;
  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={1} alignItems="center">
        <Button onClick={() => setOnDate(shiftDay(onDate, -1))}>{t('dayBook.previousDay')}</Button>
        <TextField type="date" size="small" label={t('common.date')} InputLabelProps={{ shrink: true }} value={onDate} onChange={(e) => setOnDate(e.target.value)} />
        <Button onClick={() => setOnDate(shiftDay(onDate, 1))}>{t('dayBook.nextDay')}</Button>
      </Stack>
      <Typography variant="body2" color="text.secondary">
        {String(query.data?.disclaimer ?? t('reports.dayBookDisclaimer'))}
      </Typography>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
        {[
          [t('reports.inflow'), query.data?.inflow],
          [t('reports.outflow'), query.data?.outflow],
          [t('reports.net'), query.data?.net],
        ].map(([label, val]) => (
          <Paper key={String(label)} variant="outlined" sx={{ p: 2, flex: 1 }}>
            <Typography variant="caption" color="text.secondary">{String(label)}</Typography>
            <Typography variant="h6">{formatMoney(toNumber(val as string | number))}</Typography>
          </Paper>
        ))}
      </Stack>
      {Object.values(adjustments).some((v) => toNumber(v) > 0) ? (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Typography variant="subtitle2">{t('dayBook.adjustments')}</Typography>
          <Typography variant="body2">
            {t('dayBook.adjustmentsLine', {
              returns: formatMoney(toNumber(adjustments.salesReturns)),
              credit: formatMoney(toNumber(adjustments.creditNotes)),
              debit: formatMoney(toNumber(adjustments.debitNotes)),
            })}
          </Typography>
        </Paper>
      ) : null}
      {rows.length === 0 ? <EmptyState description={t('reports.dayBookEmpty')} /> : null}
      {rows.length > 0 ? (
        <DataTable
          rows={asRows(rows)}
          empty={t('reports.dayBookEmpty')}
          columns={[
            { key: 'date', label: t('common.date') },
            { key: 'txnType', label: t('common.type') },
            { key: 'number', label: t('common.number') },
            { key: 'party', label: t('billing.customer') },
            { key: 'amount', label: t('common.total'), render: (row) => formatMoney(toNumber(row.amount as string | number)) },
            { key: 'status', label: t('common.status') },
          ]}
          actions={(row) =>
            row.sourcePath ? (
              <Typography component={RouterLink} to={String(row.sourcePath)} variant="body2" sx={{ color: 'primary.main' }}>
                {t('common.open')}
              </Typography>
            ) : null
          }
        />
      ) : null}
    </Stack>
  );
}
