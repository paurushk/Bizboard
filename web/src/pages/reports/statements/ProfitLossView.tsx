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
import { DownloadButton, PresetChips, StatementShell } from './StatementShell';
import { ScheduleSections } from './ScheduleSections';
import type { ScheduleIii } from './statementHelpers';
import { useStatementDownload } from './useStatementDownload';

type PnlData = {
  dateFrom?: string;
  dateTo?: string;
  income?: string;
  expenses?: string;
  netProfit?: string;
  scheduleIii?: ScheduleIii;
};

export function ProfitLossView({ title }: { title: string }) {
  const { user } = useAuth();
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [costCenter, setCostCenter] = useState('');
  const books = useBooksState();
  const costCenters = useQuery({ queryKey: ['cost-centers'], queryFn: api.listCostCenters });
  const params = useMemo(() => {
    const p: Record<string, string> = {};
    if (from) p.from = from;
    if (to) p.to = to;
    if (costCenter) p.cost_center = costCenter;
    return p;
  }, [from, to, costCenter]);
  const query = useQuery({
    queryKey: ['accounting-report', 'profit-and-loss', from, to, costCenter],
    queryFn: () => api.getAccountingReport('profit-and-loss', params),
    placeholderData: keepPreviousData,
  });
  const download = useStatementDownload('profit-and-loss');
  const data = (query.isError ? undefined : query.data) as PnlData | undefined;
  const trusted = books.trusted;
  const money = (v: unknown) => (trusted ? formatMoney(toNumber(v as string | number)) : '—');
  const usedDefault = !from && !to;
  const sections = data?.scheduleIii?.sections ?? [];

  const controls = (
    <Stack spacing={1}>
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
        <TextField type="date" size="small" label={t('statements.from')} InputLabelProps={{ shrink: true }} value={from} onChange={(e) => setFrom(e.target.value)} />
        <TextField type="date" size="small" label={t('statements.to')} InputLabelProps={{ shrink: true }} value={to} onChange={(e) => setTo(e.target.value)} />
        <TextField select size="small" label={t('statements.costCenter')} value={costCenter} onChange={(e) => setCostCenter(e.target.value)} sx={{ minWidth: 140 }}>
          <MenuItem value="">{t('statements.allCostCenters')}</MenuItem>
          {(costCenters.data ?? []).map((cc) => (
            <MenuItem key={String(cc.id)} value={String(cc.id)}>{String(cc.code ?? cc.name ?? cc.id)}</MenuItem>
          ))}
        </TextField>
        {canExport(user) ? <DownloadButton busy={download.busy} onClick={() => void download.run(params)} /> : null}
      </Stack>
      <PresetChips onPick={(r) => { setFrom(r.dateFrom); setTo(r.dateTo); }} />
    </Stack>
  );

  return (
    <StatementShell title={title} controls={controls} query={query}>
      <AccountingBackfillBanner />
      {download.error ? <HelpErrorAlert message={download.error} /> : null}
      {!trusted ? <Alert severity="info">{t('statements.bookNotReady')}</Alert> : null}
      <Typography variant="body2" color="text.secondary">
        {t('statements.periodShown', { from: data?.dateFrom ?? from, to: data?.dateTo ?? to })}{' '}
        {usedDefault ? t('statements.periodDefaulted') : ''}
      </Typography>
      <Alert severity="info">
        {t('statements.income')} {money(data?.income)} · {t('statements.expenses')} {money(data?.expenses)} · {t('statements.net')} {money(data?.netProfit)}
      </Alert>
      {sections.length === 0 ? (
        <Alert severity="info">{t('statements.noSections')}</Alert>
      ) : (
        <ScheduleSections sections={sections} trusted={trusted} />
      )}
    </StatementShell>
  );
}
