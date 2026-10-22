import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import {
  convertMrp,
  getAtp,
  getBoard,
  getCanMake,
  getLoad,
  getMrpRun,
  getShortages,
  listMrpRuns,
  runMrp,
  type MrpLineRow,
} from '@/api/mfg';
import { t } from '@/i18n';
import { ErrorLine, Grid, MfgPage, NumField, Pill, ProductPick, Stat, SupplierPick, TabPanels, day, qty, todayIso, useMfgRights, useRun } from './mfgShared';

export function PlanningPage() {
  return (
    <MfgPage title={t('mfg.plan.title')} subtitle={t('mfg.plan.subtitle')} flag="MFG_PLANNING">
      <TabPanels
        tabs={[
          { key: 'board', label: t('mfg.plan.tabBoard'), node: () => <Board /> },
          { key: 'short', label: t('mfg.plan.tabShortages'), node: () => <Shortages /> },
          { key: 'mrp', label: t('mfg.plan.tabMrp'), node: () => <Mrp /> },
          { key: 'load', label: t('mfg.plan.tabLoad'), hide: false, node: () => <Load /> },
          { key: 'ask', label: t('mfg.plan.tabAsk'), node: () => <Ask /> },
        ]}
      />
    </MfgPage>
  );
}

function Board() {
  const board = useQuery({ queryKey: ['mfg-board'], queryFn: getBoard });
  const rows = board.data?.orders ?? [];
  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
        <Stat label={t('mfg.plan.open')} value={rows.length} />
        <Stat label={t('mfg.plan.late')} value={rows.filter((r) => r.late).length} tone={rows.some((r) => r.late) ? 'bad' : undefined} />
        <Stat label={t('mfg.plan.dueSoon')} value={rows.filter((r) => r.dueSoon).length} tone={rows.some((r) => r.dueSoon) ? 'warn' : undefined} />
        <Stat label={t('mfg.plan.shortMaterial')} value={rows.filter((r) => r.shortMaterial).length} tone={rows.some((r) => r.shortMaterial) ? 'warn' : undefined} />
      </Stack>
      <Grid
        rows={rows}
        rowKey={(r) => r.id}
        empty={t('mfg.plan.noOpen')}
        cols={[
          { key: 'n', label: t('mfg.common.number'), render: (r) => <RouterLink to={`/manufacturing/work-orders/${r.id}`}>{r.number}</RouterLink> },
          { key: 'p', label: t('mfg.common.item'), render: (r) => r.product },
          { key: 'q', label: t('mfg.wo.made'), align: 'right', render: (r) => `${qty(r.qtyDone)} / ${qty(r.qty)}` },
          { key: 'pr', label: t('mfg.wo.priority'), align: 'right', render: (r) => r.priority },
          { key: 'd', label: t('mfg.wo.due'), render: (r) => day(r.dueDate) },
          { key: 's', label: t('mfg.common.status'), render: (r) => <Pill value={r.status} /> },
          {
            key: 'f',
            label: t('mfg.plan.flags'),
            render: (r) => (
              <Stack direction="row" spacing={0.5}>
                {r.late ? <Pill value="OVERDUE" /> : null}
                {r.dueSoon && !r.late ? <Pill value="ALERT" tone="warning" /> : null}
                {r.shortMaterial ? <Pill value="SHORT" tone="warning" /> : null}
              </Stack>
            ),
          },
          { key: 'w', label: t('mfg.wo.delayReason'), render: (r) => r.delayReason || '' },
        ]}
      />
    </Stack>
  );
}

function Shortages() {
  const q = useQuery({ queryKey: ['mfg-shortages'], queryFn: getShortages });
  return (
    <Stack spacing={2}>
      <Typography variant="body2" color="text.secondary">{t('mfg.plan.shortagesHelp')}</Typography>
      {(q.data?.orders ?? []).length === 0 ? <Alert severity="success">{t('mfg.plan.noShortages')}</Alert> : null}
      {(q.data?.orders ?? []).map((o) => (
        <Stack key={o.workOrder.id} spacing={1}>
          <Typography variant="subtitle2">
            <RouterLink to={`/manufacturing/work-orders/${o.workOrder.id}`}>{o.workOrder.number}</RouterLink> · {t('mfg.wo.due')} {day(o.workOrder.dueDate)}
          </Typography>
          <Grid
            rows={o.lines}
            rowKey={(l) => l.product.id}
            cols={[
              { key: 'p', label: t('mfg.recipe.material'), render: (l) => l.product.name },
              { key: 'n', label: t('mfg.wo.need'), align: 'right', render: (l) => qty(l.need) },
              { key: 'a', label: t('mfg.wo.held'), align: 'right', render: (l) => qty(l.allocated) },
              { key: 's', label: t('mfg.wo.short'), align: 'right', render: (l) => <b style={{ color: 'crimson' }}>{qty(l.short)}</b> },
            ]}
          />
        </Stack>
      ))}
    </Stack>
  );
}

function Mrp() {
  const qc = useQueryClient();
  const { canPlan } = useMfgRights();
  const { run, busy, error, clear } = useRun();
  const [horizon, setHorizon] = useState('30');
  const [selected, setSelected] = useState<number | null>(null);
  const [pick, setPick] = useState<Set<number>>(new Set());
  const [suppliers, setSuppliers] = useState<Record<string, number>>({});
  const [note, setNote] = useState('');
  const runs = useQuery({ queryKey: ['mfg-mrp-runs'], queryFn: listMrpRuns });
  const current = useQuery({ queryKey: ['mfg-mrp-run', selected], queryFn: () => getMrpRun(selected!), enabled: selected != null });

  const lines = (current.data?.lines ?? []).filter((l) => l.status === 'OPEN');
  const toggle = (id: number) => {
    const next = new Set(pick);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setPick(next);
  };

  return (
    <Stack spacing={2}>
      <ErrorLine error={error} onClose={clear} />
      <Typography variant="body2" color="text.secondary">{t('mfg.plan.mrpHelp')}</Typography>
      <Stack direction="row" spacing={2} alignItems="center">
        <NumField label={t('mfg.plan.horizonDays')} value={horizon} onChange={setHorizon} />
        <Button
          variant="contained"
          disabled={!canPlan || busy}
          onClick={async () => {
            const r = await run(() => runMrp(Math.max(Math.trunc(Number(horizon)) || 30, 1)));
            if (r) {
              setSelected(r.id);
              setPick(new Set());
              void qc.invalidateQueries({ queryKey: ['mfg-mrp-runs'] });
            }
          }}
        >
          {t('mfg.plan.runMrp')}
        </Button>
      </Stack>
      <Grid
        query={runs}
        rows={runs.data ?? []}
        rowKey={(r) => r.id}
        onRow={(r) => { setSelected(r.id); setPick(new Set()); }}
        cols={[
          { key: 'n', label: t('mfg.common.number'), render: (r) => r.number },
          { key: 'd', label: t('mfg.common.date'), render: (r) => day(r.asOf) },
          { key: 'h', label: t('mfg.plan.horizonDays'), align: 'right', render: (r) => r.horizonDays },
          { key: 'b', label: t('mfg.plan.toBuy'), align: 'right', render: (r) => r.summary.purchase ?? 0 },
          { key: 'm', label: t('mfg.plan.toMake'), align: 'right', render: (r) => r.summary.make ?? 0 },
        ]}
      />
      {note ? <Alert severity="success" onClose={() => setNote('')}>{note}</Alert> : null}
      {current.data ? (
        <>
          <Typography variant="subtitle2">{current.data.number}</Typography>
          <Grid<MrpLineRow>
            query={current}
            rows={current.data.lines ?? []}
            rowKey={(l) => l.id}
            cols={[
              { key: 'c', label: '', render: (l) => (l.status === 'OPEN' ? <Checkbox size="small" checked={pick.has(l.id)} onChange={() => toggle(l.id)} /> : null) },
              { key: 'p', label: t('mfg.common.item'), render: (l) => `${'— '.repeat(l.level)}${l.product.name}` },
              { key: 'k', label: t('mfg.plan.action'), render: (l) => (l.kind === 'PURCHASE' ? t('mfg.plan.buy') : t('mfg.plan.make')) },
              { key: 'g', label: t('mfg.plan.gross'), align: 'right', render: (l) => qty(l.grossQty) },
              { key: 'oh', label: t('mfg.plan.onHand'), align: 'right', render: (l) => qty(l.onHandQty) },
              { key: 'in', label: t('mfg.plan.incoming'), align: 'right', render: (l) => qty(l.incomingQty) },
              { key: 's', label: t('mfg.plan.suggested'), align: 'right', render: (l) => <b>{qty(l.suggestedQty)}</b> },
              { key: 'ob', label: t('mfg.plan.orderBy'), render: (l) => day(l.orderBy) },
              {
                key: 'sup',
                label: t('mfg.common.supplier'),
                render: (l) =>
                  l.kind === 'PURCHASE' && l.status === 'OPEN' ? (
                    l.supplier ? (
                      l.supplier.name
                    ) : (
                      <SupplierPick label="" value={suppliers[String(l.id)] ?? ''} onChange={(v) => setSuppliers({ ...suppliers, [String(l.id)]: v === '' ? 0 : v })} />
                    )
                  ) : (
                    ''
                  ),
              },
              { key: 'st', label: t('mfg.common.status'), render: (l) => (l.status === 'OPEN' ? '' : l.status === 'CONVERTED' ? `${l.convertedType} #${l.convertedId}` : l.note || l.status) },
            ]}
          />
          {lines.length ? (
            <Stack direction="row" spacing={2}>
              <Button onClick={() => setPick(new Set(lines.map((l) => l.id)))}>{t('mfg.plan.selectAll')}</Button>
              <Button
                variant="contained"
                disabled={!canPlan || busy || pick.size === 0}
                onClick={async () => {
                  const r = await run(() => convertMrp(current.data!.id, { lines: [...pick], suppliers }));
                  if (r) {
                    setNote(t('mfg.plan.converted', { po: r.purchaseOrders.length, wo: r.workOrders.length, skipped: r.skipped.length }));
                    setPick(new Set());
                    void qc.invalidateQueries({ queryKey: ['mfg-mrp-run', current.data!.id] });
                  }
                }}
              >
                {t('mfg.plan.convert')}
              </Button>
            </Stack>
          ) : null}
        </>
      ) : null}
    </Stack>
  );
}

function Load() {
  const [from, setFrom] = useState(todayIso());
  const q = useQuery({ queryKey: ['mfg-load', from], queryFn: () => getLoad(from, 14) });
  return (
    <Stack spacing={2}>
      <Typography variant="body2" color="text.secondary">{t('mfg.plan.loadHelp')}</Typography>
      <TextField size="small" type="date" label={t('mfg.common.from')} value={from} onChange={(e) => setFrom(e.target.value)} InputLabelProps={{ shrink: true }} sx={{ width: 180 }} />
      {(q.data?.workCentres ?? []).map((w) => (
        <Stack key={w.workCentre} spacing={0.5}>
          <Typography variant="subtitle2">
            {w.code} · {w.name} {w.overloadedDays ? <Pill value="OVERDUE" tone="error" /> : null}
          </Typography>
          <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
            {w.days.map((d) => (
              <Stat key={d.date} label={day(d.date)} value={`${qty(d.minutes)} / ${qty(d.capacity)}`} tone={d.overloaded ? 'bad' : undefined} />
            ))}
          </Stack>
        </Stack>
      ))}
      {q.data && q.data.workCentres.length === 0 ? <Typography color="text.secondary">{t('mfg.plan.noCentres')}</Typography> : null}
    </Stack>
  );
}

function Ask() {
  const [product, setProduct] = useState<number | ''>('');
  const [date, setDate] = useState(todayIso());
  const make = useQuery({ queryKey: ['mfg-ask-make', product], queryFn: () => getCanMake(product as number), enabled: product !== '' });
  const atp = useQuery({ queryKey: ['mfg-ask-atp', product, date], queryFn: () => getAtp(product as number, date), enabled: product !== '' });
  return (
    <Stack spacing={2}>
      <Typography variant="body2" color="text.secondary">{t('mfg.plan.askHelp')}</Typography>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
        <ProductPick value={product} onChange={setProduct} />
        <TextField size="small" type="date" label={t('mfg.plan.promiseBy')} value={date} onChange={(e) => setDate(e.target.value)} InputLabelProps={{ shrink: true }} />
      </Stack>
      {make.data ? <Stat label={t('mfg.quick.canMake')} value={`${qty(make.data.qty)}${make.data.limitedByName ? ` · ${t('mfg.quick.limitedBy')} ${make.data.limitedByName}` : ''}`} /> : null}
      {atp.data ? (
        <Stack direction="row" spacing={2}>
          <Stat label={t('mfg.plan.supply')} value={qty(atp.data.supply)} />
          <Stat label={t('mfg.plan.committed')} value={qty(atp.data.committed)} />
          <Stat label={t('mfg.plan.available')} value={qty(atp.data.available)} tone={Number(atp.data.available) > 0 ? 'good' : 'bad'} />
        </Stack>
      ) : null}
    </Stack>
  );
}
