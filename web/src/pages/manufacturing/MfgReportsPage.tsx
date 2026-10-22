import { useState } from 'react';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  deleteStandardCost,
  downloadReport,
  getReport,
  listStandardCosts,
  saveBlob,
  saveStandardCost,
  traceBatch,
  type BatchHit,
  type ReportSlug,
  type TraceBack,
  type TraceForward,
} from '@/api/mfg';
import { t } from '@/i18n';
import { RevaluationPanel } from './RevaluationPanel';
import { BatchPick, ErrorLine, Grid, MfgPage, NumField, ProductPick, SelectField, Stat, TabPanels, day, fyStartYear, money, qty, todayIso, useMfgRights, useRun } from './mfgShared';

const REPORTS: Array<{ slug: ReportSlug; costOnly: boolean }> = [
  { slug: 'wip', costOnly: true },
  { slug: 'work-order-cost', costOnly: true },
  { slug: 'variance', costOnly: true },
  { slug: 'yield-wastage', costOnly: false },
  { slug: 'consumption', costOnly: false },
  { slug: 'output', costOnly: false },
  { slug: 'on-time', costOnly: false },
  { slug: 'scrap-register', costOnly: true },
  { slug: 'profitability', costOnly: true },
  { slug: 'reconciliation', costOnly: true },
];

export function MfgReportsPage() {
  const { canCosts } = useMfgRights();
  return (
    <MfgPage title={t('mfg.reports.title')} subtitle={t('mfg.reports.subtitle')}>
      <TabPanels
        tabs={[
          { key: 'rep', label: t('mfg.reports.tabReports'), node: () => <Reports canCosts={canCosts} /> },
          { key: 'trace', label: t('mfg.reports.tabTrace'), node: () => <Trace /> },
          { key: 'std', label: t('mfg.reports.tabStandard'), hide: !canCosts, node: () => <StandardCosts /> },
        ]}
      />
    </MfgPage>
  );
}

/** Amounts of money in a report are named for what they hold; counts, dates and percentages are not. */
const isMoneyKey = (k: string) => /(cost|value|total|wip|variance|revenue|margin|amount|issued|returned|absorbed|received|profit|loss|bucket)/i.test(k) && !/(pct|count|qty|days|asOf|as_of)/i.test(k);

const humanize = (k: string) => k.replace(/([A-Z])/g, ' $1').replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase());

function show(v: unknown): string {
  if (v === null || v === undefined || v === '') return '—';
  if (typeof v === 'number') return qty(v);
  if (typeof v === 'object') return JSON.stringify(v);
  const s = String(v);
  if (/^-?\d+(\.\d+)?$/.test(s)) return qty(s);
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return day(s);
  return s;
}

function Reports({ canCosts }: { canCosts: boolean }) {
  const { run, error, clear } = useRun();
  const list = REPORTS.filter((r) => canCosts || !r.costOnly);
  const [slug, setSlug] = useState<ReportSlug>(list[0].slug);
  const [from, setFrom] = useState(`${fyStartYear()}-04-01`);
  const [to, setTo] = useState(todayIso());
  const params = { from, to, asOf: to };
  const q = useQuery({ queryKey: ['mfg-report', slug, from, to], queryFn: () => getReport(slug, params) });
  const data = q.data ?? {};
  const scalars = Object.entries(data).filter(([, v]) => v === null || typeof v !== 'object');
  const tables = Object.entries(data).filter(([, v]) => Array.isArray(v) && v.length > 0 && typeof v[0] === 'object') as Array<[string, Array<Record<string, unknown>>]>;
  const maps = Object.entries(data).filter(([, v]) => v && typeof v === 'object' && !Array.isArray(v)) as Array<[string, Record<string, unknown>]>;
  return (
    <Stack spacing={2}>
      <ErrorLine error={error ?? (q.isError ? t('mfg.reports.loadFailed') : null)} onClose={clear} />
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems={{ sm: 'center' }}>
        <SelectField label={t('mfg.reports.report')} value={slug} onChange={setSlug} options={list.map((r) => ({ value: r.slug, label: t(`mfg.reports.r_${r.slug}`) }))} />
        <TextField size="small" type="date" label={t('mfg.common.from')} value={from} onChange={(e) => setFrom(e.target.value)} InputLabelProps={{ shrink: true }} />
        <TextField size="small" type="date" label={t('mfg.common.to')} value={to} onChange={(e) => setTo(e.target.value)} InputLabelProps={{ shrink: true }} />
        <Button onClick={async () => { const b = await run(() => downloadReport(slug, params)); if (b) saveBlob(b, `${slug}.csv`); }}>{t('mfg.common.exportCsv')}</Button>
      </Stack>
      <Typography variant="body2" color="text.secondary">{t(`mfg.reports.h_${slug}`)}</Typography>
      <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
        {scalars.map(([k, v]) => (
          <Stat key={k} label={humanize(k)} value={isMoneyKey(k) ? money(v as string) : show(v)} />
        ))}
      </Stack>
      {maps.map(([k, v]) => (
        <Stack key={k} direction="row" spacing={2} flexWrap="wrap" useFlexGap alignItems="center">
          <Typography variant="subtitle2">{humanize(k)}</Typography>
          {Object.entries(v).map(([kk, vv]) => (
            <Stat key={kk} label={humanize(kk)} value={isMoneyKey(kk) || isMoneyKey(k) ? money(vv as string) : show(vv)} />
          ))}
        </Stack>
      ))}
      {tables.map(([k, rows]) => (
        <Stack key={k} spacing={0.5}>
          <Typography variant="subtitle2">{humanize(k)}</Typography>
          <Grid
            rows={rows}
            rowKey={(r) => JSON.stringify(r)}
            cols={Object.keys(rows[0]).filter((c) => typeof rows[0][c] !== 'object' || rows[0][c] === null).map((c) => ({ key: c, label: humanize(c), align: typeof rows[0][c] === 'number' || /^-?\d+(\.\d+)?$/.test(String(rows[0][c])) ? ('right' as const) : ('left' as const), render: (r: Record<string, unknown>) => show(r[c]) }))}
          />
        </Stack>
      ))}
      {q.data && tables.length === 0 && scalars.length === 0 && maps.length === 0 ? <Typography color="text.secondary">{t('mfg.common.nothingYet')}</Typography> : null}
    </Stack>
  );
}

function Trace() {
  const [batch, setBatch] = useState<BatchHit | null>(null);
  const [dir, setDir] = useState<'back' | 'forward'>('back');
  const result = useQuery({ queryKey: ['mfg-trace', batch?.id, dir], queryFn: () => traceBatch(batch!.id, dir), enabled: batch != null });
  const back = dir === 'back' ? (result.data as TraceBack | undefined) : undefined;
  const fwd = dir === 'forward' ? (result.data as TraceForward | undefined) : undefined;
  return (
    <Stack spacing={2}>
      <Typography variant="body2" color="text.secondary">{t('mfg.reports.traceHelp')}</Typography>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
        <BatchPick value={batch} onChange={setBatch} />
        <SelectField label={t('mfg.reports.direction')} value={dir} onChange={setDir} options={[{ value: 'back', label: t('mfg.reports.traceBack') }, { value: 'forward', label: t('mfg.reports.traceForward') }]} />
      </Stack>
      {back ? (
        <Grid
          rows={back.inputs}
          rowKey={(r) => `${r.depth}-${r.batch}-${r.serial}-${r.workOrder}`}
          empty={t('mfg.reports.noTrace')}
          cols={[
            { key: 'd', label: t('mfg.recipe.level'), render: (r) => r.depth },
            { key: 'o', label: t('mfg.reports.madeBatch'), render: (r) => r.outputBatch },
            { key: 'p', label: t('mfg.common.item'), render: (r) => r.product },
            { key: 'b', label: t('mfg.common.batchNo'), render: (r) => r.batch || r.serial },
            { key: 'q', label: t('mfg.common.quantity'), align: 'right', render: (r) => qty(r.qty) },
            { key: 's', label: t('mfg.reports.source'), render: (r) => (r.source ? `${r.source.movementType} ${r.source.number ?? ''} ${r.source.supplier ?? ''}` : '') },
          ]}
        />
      ) : null}
      {fwd ? (
        <>
          <Typography variant="subtitle2">{t('mfg.reports.madeFromIt')}</Typography>
          <Grid rows={fwd.madeFromIt} rowKey={(r) => `${r.depth}-${r.batch}`} empty={t('mfg.reports.noTrace')} cols={[{ key: 'd', label: t('mfg.recipe.level'), render: (r) => r.depth }, { key: 'p', label: t('mfg.common.item'), render: (r) => r.product }, { key: 'b', label: t('mfg.common.batchNo'), render: (r) => r.batch }, { key: 'f', label: t('mfg.reports.fromBatch'), render: (r) => r.fromBatch }]} />
          <Typography variant="subtitle2">{t('mfg.reports.sentTo')}</Typography>
          <Grid rows={fwd.sentTo} rowKey={(r) => `${r.batch}-${r.number}-${r.date}`} empty={t('mfg.reports.noTrace')} cols={[{ key: 'b', label: t('mfg.common.batchNo'), render: (r) => r.batch }, { key: 'p', label: t('mfg.common.item'), render: (r) => r.product }, { key: 'q', label: t('mfg.common.quantity'), align: 'right', render: (r) => qty(r.qty) }, { key: 'd', label: t('mfg.common.date'), render: (r) => day(r.date) }, { key: 'n', label: t('mfg.common.number'), render: (r) => r.number ?? '' }, { key: 'c', label: t('mfg.common.customer'), render: (r) => r.customer ?? '' }]} />
        </>
      ) : null}
    </Stack>
  );
}

function StandardCosts() {
  const qc = useQueryClient();
  const { canPlan } = useMfgRights();
  const { run, error, clear } = useRun();
  const q = useQuery({ queryKey: ['mfg-std-costs'], queryFn: () => listStandardCosts() });
  const [product, setProduct] = useState<number | ''>('');
  const [from, setFrom] = useState(todayIso());
  const [material, setMaterial] = useState('');
  const [labour, setLabour] = useState('');
  const [overhead, setOverhead] = useState('');
  const reload = () => void qc.invalidateQueries({ queryKey: ['mfg-std-costs'] });
  return (
    <Stack spacing={2}>
      <ErrorLine error={error} onClose={clear} />
      <Typography variant="body2" color="text.secondary">{t('mfg.reports.standardHelp')}</Typography>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} alignItems={{ md: 'center' }}>
        <ProductPick value={product} onChange={setProduct} />
        <TextField size="small" type="date" label={t('mfg.recipe.effectiveFrom')} value={from} onChange={(e) => setFrom(e.target.value)} InputLabelProps={{ shrink: true }} />
        <NumField label={t('mfg.reports.material')} value={material} onChange={setMaterial} />
        <NumField label={t('mfg.recipe.labour')} value={labour} onChange={setLabour} />
        <NumField label={t('mfg.recipe.overhead')} value={overhead} onChange={setOverhead} />
        <Button
          variant="contained"
          disabled={!canPlan || product === ''}
          onClick={async () => {
            if (await run(() => saveStandardCost(null, { product: product as number, effectiveFrom: from, material: material || '0', labour: labour || '0', overhead: overhead || '0' }))) {
              setMaterial('');
              setLabour('');
              setOverhead('');
              reload();
            }
          }}
        >
          {t('common.add')}
        </Button>
      </Stack>
      <Grid
        query={q}
        rows={q.data ?? []}
        rowKey={(r) => r.id}
        cols={[
          { key: 'p', label: t('mfg.common.item'), render: (r) => r.productName },
          { key: 'f', label: t('mfg.recipe.effectiveFrom'), render: (r) => day(r.effectiveFrom) },
          { key: 'm', label: t('mfg.reports.material'), align: 'right', render: (r) => money(r.material) },
          { key: 'l', label: t('mfg.recipe.labour'), align: 'right', render: (r) => money(r.labour) },
          { key: 'o', label: t('mfg.recipe.overhead'), align: 'right', render: (r) => money(r.overhead) },
          { key: 'u', label: t('mfg.reports.unitCost'), align: 'right', render: (r) => money(r.unitCost) },
          { key: 'x', label: '', render: (r) => <Button size="small" color="warning" disabled={!canPlan} onClick={async () => { await run(() => deleteStandardCost(r.id)); reload(); }}>{t('common.delete')}</Button> },
        ]}
      />
      <RevaluationPanel />
    </Stack>
  );
}
