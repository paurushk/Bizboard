import { useMemo, useState } from 'react';
import Alert from '@mui/material/Alert';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import * as api from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { AccountingBackfillBanner, useBooksState } from '@/components/AccountingBackfillBanner';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { t } from '@/i18n';
import { formatMoney, toNumber } from '@/utils/money';
import { canExport } from '@/utils/permissions';
import { DownloadButton, StatementShell } from './StatementShell';
import { ScheduleSections } from './ScheduleSections';
import { splitBalanceSheet, type ScheduleIii } from './statementHelpers';
import { useStatementDownload } from './useStatementDownload';

function todayIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

type BalanceSheetData = {
  asOf?: string;
  asOfDefaulted?: boolean;
  equationHolds?: boolean;
  scheduleIii?: ScheduleIii;
  inventoryGl?: string;
  inventoryValuation?: string;
  inventoryNote?: string;
};

export function BalanceSheetView({ title }: { title: string }) {
  const { user } = useAuth();
  // The screen asks for today, so people always see a real date; the API still falls back to year end.
  const [asOf, setAsOf] = useState(todayIso);
  const [costCenter, setCostCenter] = useState('');
  const books = useBooksState();
  const costCenters = useQuery({ queryKey: ['cost-centers'], queryFn: api.listCostCenters });
  const params = useMemo(() => {
    const p: Record<string, string> = {};
    if (asOf) p.as_of = asOf;
    if (costCenter) p.cost_center = costCenter;
    return p;
  }, [asOf, costCenter]);
  const query = useQuery({
    queryKey: ['accounting-report', 'balance-sheet', asOf, costCenter],
    queryFn: () => api.getAccountingReport('balance-sheet', params),
    placeholderData: keepPreviousData,
  });
  const download = useStatementDownload('balance-sheet');

  const data = (query.isError ? undefined : query.data) as BalanceSheetData | undefined;
  const split = splitBalanceSheet(data?.scheduleIii);
  const trusted = books.trusted;
  const money = (v: number) => (trusted ? formatMoney(v) : '—');
  const balanced = data?.equationHolds === true;

  const controls = (
    <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
      <TextField type="date" size="small" label={t('statements.asOf')} InputLabelProps={{ shrink: true }} value={asOf} onChange={(e) => setAsOf(e.target.value)} />
      <TextField select size="small" label={t('statements.costCenter')} value={costCenter} onChange={(e) => setCostCenter(e.target.value)} sx={{ minWidth: 140 }}>
        <MenuItem value="">{t('statements.allCostCenters')}</MenuItem>
        {(costCenters.data ?? []).map((cc) => (
          <MenuItem key={String(cc.id)} value={String(cc.id)}>{String(cc.code ?? cc.name ?? cc.id)}</MenuItem>
        ))}
      </TextField>
      {canExport(user) ? <DownloadButton busy={download.busy} onClick={() => void download.run(params)} /> : null}
    </Stack>
  );

  return (
    <StatementShell title={title} controls={controls} query={query}>
      <AccountingBackfillBanner />
      {download.error ? <HelpErrorAlert message={download.error} /> : null}
      {!trusted ? <Alert severity="info">{t('statements.bookNotReady')}</Alert> : null}
      <Typography variant="body2" color="text.secondary">
        {t('statements.asOfShown', { date: data?.asOf ?? asOf })}{' '}
        {data?.asOfDefaulted ? t('statements.asOfDefaulted') : ''}
      </Typography>
      {split.assets.length + split.equityAndLiabilities.length === 0 ? (
        <Alert severity="info">{t('statements.noSections')}</Alert>
      ) : (
        <>
          <Alert severity={balanced ? 'success' : 'warning'}>
            {balanced ? t('statements.checkOk') : t('statements.checkOff', { amount: money(Math.abs(split.difference)) })}
          </Alert>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems="flex-start">
            <Stack sx={{ flex: 1, width: '100%' }}>
              <ScheduleSections sections={split.assets} trusted={trusted} totalLabel={t('statements.totalAssets')} totalValue={split.totalAssets} />
            </Stack>
            <Stack sx={{ flex: 1, width: '100%' }}>
              <ScheduleSections
                sections={split.equityAndLiabilities}
                trusted={trusted}
                totalLabel={t('statements.totalEquityLiabilities')}
                totalValue={split.totalEquityLiabilities}
              />
            </Stack>
          </Stack>
        </>
      )}
      {data?.inventoryGl !== undefined ? (
        <Alert severity="info">
          {t('statements.inventoryBooks')} {money(toNumber(data.inventoryGl))} · {t('statements.inventoryStock')} {money(toNumber(data.inventoryValuation))}
          {data.inventoryNote ? ` — ${data.inventoryNote}` : ''}
        </Alert>
      ) : null}
    </StatementShell>
  );
}
