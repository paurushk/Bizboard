import { useMemo, useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import FormControlLabel from '@mui/material/FormControlLabel';
import Checkbox from '@mui/material/Checkbox';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { exportReport, getPurchaseRegister } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { dateRangeForPreset } from '@/components/HistoryFilterBar';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { PageTitle } from '@/contextHelp';
import { t } from '@/i18n';
import { formatMoney, toNumber } from '@/utils/money';
import { canExport } from '@/utils/permissions';
import { downloadReportUrl, formatColumnHeader, isMoneyColumn } from '@/utils/reportFormat';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { DataTable } from '@/pages/phase/phaseShared';

/** The columns a person reads a purchase register by, in reading order. */
const CORE_COLUMNS: Array<{ key: string; label: string; money?: boolean; status?: boolean }> = [
  { key: 'number', label: 'reports.regColNumber' },
  { key: 'date', label: 'reports.regColDate' },
  { key: 'supplier', label: 'reports.regColSupplier' },
  { key: 'status', label: 'reports.regColStatus', status: true },
  { key: 'taxable', label: 'reports.regColTaxable', money: true },
  { key: 'grand_total', label: 'reports.regColTotal', money: true },
];

function lastMonthRange(now = new Date()): { dateFrom: string; dateTo: string } {
  const iso = (d: Date) =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  return {
    dateFrom: iso(new Date(now.getFullYear(), now.getMonth() - 1, 1)),
    dateTo: iso(new Date(now.getFullYear(), now.getMonth(), 0)),
  };
}

export function PurchaseReportPage() {
  const { user } = useAuth();
  // Opening on the whole register is slow and rarely what anyone wants: start on this financial year.
  const initial = useMemo(() => dateRangeForPreset('currentFY'), []);
  const [dateFrom, setDateFrom] = useState(initial.dateFrom);
  const [dateTo, setDateTo] = useState(initial.dateTo);
  const [allColumns, setAllColumns] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const query = useQuery({
    queryKey: ['purchase-register', dateFrom, dateTo],
    queryFn: () =>
      getPurchaseRegister({ dateFrom: dateFrom || undefined, dateTo: dateTo || undefined }),
  });

  const exportMutation = useMutation({
    mutationFn: () =>
      exportReport('purchases', { dateFrom: dateFrom || undefined, dateTo: dateTo || undefined }),
    onSuccess: (r) => {
      downloadReportUrl(r.url, 'purchase-register.csv');
      setNotice(t('reports.regExported'));
    },
  });

  const rows = useMemo(() => query.data?.rows ?? [], [query.data]);

  // F3-017: an unbounded date range can return the entire register —
  // window the DOM rows via phaseShared.DataTable's virtualized mode.
  const columns = useMemo(() => {
    if (!allColumns) {
      return CORE_COLUMNS.map((c) => ({ ...c, label: t(c.label) }));
    }
    return (rows[0] ? Object.keys(rows[0]).filter((key) => key !== 'id') : []).map((key) => ({
      key,
      label: formatColumnHeader(key),
      money: isMoneyColumn(key),
    }));
  }, [allColumns, rows]);

  const totals = useMemo(() => {
    let taxable = 0;
    let tax = 0;
    let grand = 0;
    for (const r of rows) {
      taxable += toNumber(r.taxable as string | number);
      tax += toNumber(r.cgst as string | number) + toNumber(r.sgst as string | number) + toNumber(r.igst as string | number);
      grand += toNumber(r.grand_total as string | number);
    }
    return { count: rows.length, taxable, tax, grand };
  }, [rows]);

  const applyRange = (range: { dateFrom: string; dateTo: string }) => {
    setDateFrom(range.dateFrom);
    setDateTo(range.dateTo);
  };

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1}>
        <PageTitle>{t('nav.purchaseReports')}</PageTitle>
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
          <Chip size="small" label={t('history.preset.thisMonth')} onClick={() => applyRange(dateRangeForPreset('thisMonth'))} />
          <Chip size="small" label={t('history.preset.lastMonth')} onClick={() => applyRange(lastMonthRange())} />
          {(['currentFY', 'previousFY', 'q1', 'q2', 'q3', 'q4'] as const).map((preset) => (
            <Chip key={preset} size="small" label={t(`history.preset.${preset}`)} onClick={() => applyRange(dateRangeForPreset(preset))} />
          ))}
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
              onClick={() => {
                setNotice(null);
                exportMutation.mutate();
              }}
            >
              {t('common.export')}
            </Button>
          ) : null}
        </Stack>
      </Stack>
      {notice ? (
        <Alert severity="success" onClose={() => setNotice(null)}>
          {notice}
        </Alert>
      ) : null}
      {exportMutation.isError ? (
        <HelpErrorAlert error={exportMutation.error} />
      ) : null}
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {query.data?.rows?.length === 0 ? <EmptyState description={t('empty.reports')} /> : null}
      {rows.length > 0 ? (
        <>
          <Stack direction="row" spacing={3} flexWrap="wrap" useFlexGap alignItems="center" aria-label={t('reports.regBills')}>
            <Typography variant="body2">
              {t('reports.regBills')}: <strong>{totals.count}</strong>
            </Typography>
            <Typography variant="body2">
              {t('reports.regTaxable')}: <strong>{formatMoney(totals.taxable)}</strong>
            </Typography>
            <Typography variant="body2">
              {t('reports.regTax')}: <strong>{formatMoney(totals.tax)}</strong>
            </Typography>
            <Typography variant="body2">
              {t('reports.regGrand')}: <strong>{formatMoney(totals.grand)}</strong>
            </Typography>
            <FormControlLabel
              control={<Checkbox size="small" checked={allColumns} onChange={(e) => setAllColumns(e.target.checked)} />}
              label={t('reports.regAllColumns')}
            />
          </Stack>
          <DataTable rows={rows} columns={columns} empty={t('empty.reports')} virtualized />
        </>
      ) : null}
    </Stack>
  );
}
