import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Tab from '@mui/material/Tab';
import Tabs from '@mui/material/Tabs';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import {
  downloadTcsWorksheet,
  downloadTdsWorksheet,
  getTaxWorksheetPreview,
  type TaxWorksheetKind,
} from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { showEmpty } from '@/utils/queryState';
import { t, useLocale } from '@/i18n';
import { PageShell, DataTable } from '@/pages/phase/phaseShared';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { formatMoney, toNumber } from '@/utils/money';
import { canExport } from '@/utils/permissions';

const PERIOD_RE = /^\d{4}-(0[1-9]|1[0-2])$/;

function currentPeriod(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

export function TdsTcsReportsPage() {
  useLocale();
  const { user } = useAuth();
  const [period, setPeriod] = useState(currentPeriod);
  const [kind, setKind] = useState<TaxWorksheetKind>('tds');
  const [error, setError] = useState('');
  const validPeriod = PERIOD_RE.test(period);

  const preview = useQuery({
    queryKey: ['tax-worksheet', kind, period],
    queryFn: () => getTaxWorksheetPreview(kind, period),
    enabled: validPeriod,
    placeholderData: keepPreviousData,
  });

  const download = async () => {
    setError('');
    try {
      const blob = kind === 'tds' ? await downloadTdsWorksheet(period) : await downloadTcsWorksheet(period);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = kind === 'tds' ? `tds-26q-${period}.csv` : `tcs-27eq-${period}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10_000);
    } catch (e) {
      setError(getErrorMessage(e) || t('reports.tdsDownloadFailed'));
    }
  };

  const data = preview.data;
  const rows = (data?.rows ?? []).map((r, i) => ({ id: `${r.invoice}-${i}`, ...r }));
  const partyKey = kind === 'tds' ? 'supplier' : 'customer';
  const amountKey = kind === 'tds' ? 'tds_amount' : 'tcs_amount';

  return (
    <PageShell title={t('reports.tdsTitle')} subtitle={t('reports.tdsSubtitle')}>
      <Alert severity="info">{t('reports.tdsInfo')}</Alert>
      {error ? <HelpErrorAlert message={error} /> : null}
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={2}>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ sm: 'center' }}>
            <Tabs value={kind} onChange={(_, v: TaxWorksheetKind) => setKind(v)} aria-label={t('reports.tdsTitle')}>
              <Tab value="tds" label={t('reports.tdsTabTds')} />
              <Tab value="tcs" label={t('reports.tdsTabTcs')} />
            </Tabs>
            <TextField
              size="small"
              type="month"
              label={t('reports.tdsPeriod')}
              value={period}
              onChange={(e) => { if (e.target.value) setPeriod(e.target.value); }}
              error={!validPeriod}
              helperText={validPeriod ? undefined : t('reports.tdsInvalidPeriod')}
              InputLabelProps={{ shrink: true }}
            />
            {canExport(user) ? (
              <Button variant="contained" disabled={!validPeriod || preview.isError} onClick={() => void download()}>
                {kind === 'tds' ? t('reports.tdsDownload26q') : t('reports.tdsDownload27eq')}
              </Button>
            ) : (
              <Typography variant="body2" color="text.secondary">{t('reports.tdsNeedsExport')}</Typography>
            )}
          </Stack>
          <Typography variant="body2" color="text.secondary">{t('reports.tdsOwnerOnly')}</Typography>
        </Stack>
      </Paper>

      {preview.isLoading && validPeriod ? <LoadingState /> : null}
      {preview.isError ? (
        <ErrorState message={getErrorMessage(preview.error)} error={preview.error} onRetry={() => void preview.refetch()} />
      ) : null}
      {showEmpty(preview, rows.length) ? <EmptyState description={t('reports.tdsEmptyMonth')} /> : null}
      {!preview.isError && data && rows.length > 0 ? (
        <Stack spacing={2}>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <Paper variant="outlined" sx={{ p: 2, flex: 1 }}>
              <Typography variant="caption" color="text.secondary">{t('reports.tdsTotalTaxable')}</Typography>
              <Typography variant="h6">{formatMoney(toNumber(data.totals.taxable))}</Typography>
            </Paper>
            <Paper variant="outlined" sx={{ p: 2, flex: 1 }}>
              <Typography variant="caption" color="text.secondary">
                {kind === 'tds' ? t('reports.tdsTotalTds') : t('reports.tdsTotalTcs')}
              </Typography>
              <Typography variant="h6">{formatMoney(toNumber(data.totals.amount))}</Typography>
            </Paper>
            <Paper variant="outlined" sx={{ p: 2, flex: 1 }}>
              <Typography variant="caption" color="text.secondary">{t('reports.tdsRows')}</Typography>
              <Typography variant="h6">{data.count}</Typography>
            </Paper>
          </Stack>
          <DataTable
            rows={data.bySection.map((s) => ({ id: s.section || '-', ...s }))}
            empty={t('reports.tdsEmptyMonth')}
            columns={[
              { key: 'section', label: t('reports.tdsColSection') },
              { key: 'count', label: t('reports.tdsRows') },
              { key: 'taxable', label: t('reports.tdsTotalTaxable'), money: true },
              { key: 'amount', label: kind === 'tds' ? t('reports.tdsTotalTds') : t('reports.tdsTotalTcs'), money: true },
            ]}
          />
          <DataTable
            rows={rows}
            empty={t('reports.tdsEmptyMonth')}
            columns={[
              { key: 'date', label: t('common.date') },
              { key: 'invoice', label: t('common.number') },
              { key: partyKey, label: kind === 'tds' ? t('common.supplier') : t('common.customer') },
              { key: 'section', label: t('reports.tdsColSection') },
              { key: 'rate', label: t('reports.tdsColRate') },
              { key: 'taxable', label: t('reports.tdsTotalTaxable'), money: true },
              { key: amountKey, label: kind === 'tds' ? t('reports.tdsTotalTds') : t('reports.tdsTotalTcs'), money: true },
            ]}
          />
        </Stack>
      ) : null}
    </PageShell>
  );
}
