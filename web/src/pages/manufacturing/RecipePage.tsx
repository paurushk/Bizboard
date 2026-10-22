import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import IconButton from '@mui/material/IconButton';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import FormControlLabel from '@mui/material/FormControlLabel';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import DeleteIcon from '@mui/icons-material/Delete';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom';
import {
  activateRecipe,
  archiveRecipe,
  getCostRollup,
  getExplosion,
  getRecipe,
  getRouting,
  getWhereUsed,
  listRecipes,
  listWorkCentres,
  reviseRecipe,
  saveRecipe,
  saveRouting,
  type Recipe,
  type RecipeExtraCost,
  type RecipeLine,
  type RecipeOutput,
  type RoutingOp,
} from '@/api/mfg';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { ErrorState, LoadingState } from '@/components/PageState';
import { getErrorMessage } from '@/api/client';
import { t } from '@/i18n';
import {
  ErrorLine,
  Grid,
  MfgPage,
  NumField,
  Pill,
  ProductPick,
  SelectField,
  TabPanels,
  WarehousePick,
  day,
  money,
  qty,
  useMasters,
  useMfgRights,
  useRun,
} from './mfgShared';

const blankLine = (): RecipeLine => ({ component: 0, qty: '1', scrapPct: '0', issueMethod: 'MANUAL' });

export function RecipePage() {
  const { id } = useParams();
  const recipeId = Number(id);
  const qc = useQueryClient();
  const nav = useNavigate();
  const { canPlan, canCosts } = useMfgRights();
  const { productName } = useMasters();
  const { run, busy, error, clear } = useRun();
  const q = useQuery({ queryKey: ['mfg-recipe', recipeId], queryFn: () => getRecipe(recipeId), enabled: Number.isFinite(recipeId) });
  // Edits sit on top of the last fetched copy; a fresh fetch (after save, revise or activate) drops them.
  const [edit, setEdit] = useState<{ base: Recipe; data: Recipe } | null>(null);
  const [reviseOpen, setReviseOpen] = useState(false);
  const dirty = !!edit && edit.base === q.data;
  const d: Recipe | null = dirty ? edit.data : (q.data ?? null);

  const revisions = useQuery({
    queryKey: ['mfg-recipe-revisions', q.data?.product],
    queryFn: () => listRecipes({ product: q.data!.product }),
    enabled: !!q.data,
  });

  if (q.isLoading || !d) {
    return <MfgPage title={t('mfg.recipe.title')}>{q.isError ? <ErrorState message={getErrorMessage(q.error)} error={q.error} onRetry={() => void q.refetch()} /> : <LoadingState />}</MfgPage>;
  }

  const editable = canPlan && d.status === 'DRAFT' && !d.isLocked;
  const patch = (p: Partial<Recipe>) => setEdit({ base: q.data!, data: { ...d, ...p } });
  const setLine = (i: number, p: Partial<RecipeLine>) => patch({ lines: d.lines.map((l, k) => (k === i ? { ...l, ...p } : l)) });
  const setOut = (i: number, p: Partial<RecipeOutput>) => patch({ outputs: d.outputs.map((l, k) => (k === i ? { ...l, ...p } : l)) });
  const extras = d.additionalCosts ?? [];
  const setExtra = (i: number, p: Partial<RecipeExtraCost>) => patch({ additionalCosts: extras.map((l, k) => (k === i ? { ...l, ...p } : l)) });

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['mfg-recipe', recipeId] });
    void qc.invalidateQueries({ queryKey: ['mfg-recipe-revisions'] });
    void qc.invalidateQueries({ queryKey: ['boms'] });
  };

  const save = async () => {
    const out = await run(() =>
      saveRecipe(d.id, {
        name: d.name,
        outputQty: d.outputQty,
        yieldPct: d.yieldPct,
        fgWarehouse: d.fgWarehouse,
        notes: d.notes,
        effectiveFrom: d.effectiveFrom,
        changeReason: d.changeReason,
        lines: d.lines,
        outputs: d.outputs,
        additionalCosts: extras,
      }),
    );
    if (out) refresh();
  };

  return (
    <MfgPage
      title={`${d.name || t('mfg.recipe.title')} · ${t('mfg.recipe.rev', { n: d.revisionNo })}`}
      subtitle={productName(d.product)}
      actions={
        <Stack direction="row" spacing={1}>
          <Button component={RouterLink} to="/manufacturing/boms">
            {t('mfg.common.back')}
          </Button>
          {d.status === 'DRAFT' ? (
            <Button
              variant="contained"
              disabled={!canPlan || busy || dirty}
              onClick={async () => {
                const out = await run(() => activateRecipe(d.id, { makeDefault: true }));
                if (out) refresh();
              }}
            >
              {t('mfg.recipe.activate')}
            </Button>
          ) : null}
          {d.status !== 'DRAFT' ? (
            <Button variant="outlined" disabled={!canPlan || busy} onClick={() => setReviseOpen(true)}>
              {t('mfg.recipe.revise')}
            </Button>
          ) : null}
          {d.status === 'ACTIVE' ? (
            <Button
              color="warning"
              disabled={!canPlan || busy}
              onClick={async () => {
                const out = await run(() => archiveRecipe(d.id));
                if (out) refresh();
              }}
            >
              {t('mfg.recipe.archive')}
            </Button>
          ) : null}
        </Stack>
      }
    >
      <ErrorLine error={error} onClose={clear} />
      <Stack direction="row" spacing={1} alignItems="center">
        <Pill value={d.status} />
        {d.isDefault ? <Pill value="DEFAULT" tone="info" /> : null}
        {d.isLocked ? <Alert severity="info" sx={{ py: 0 }}>{t('mfg.recipe.locked')}</Alert> : null}
      </Stack>

      <TabPanels
        tabs={[
          {
            key: 'basics',
            label: t('mfg.recipe.tabBasics'),
            node: () => (
              <Stack spacing={2} sx={{ maxWidth: 760 }}>
                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                  <TextField size="small" label={t('mfg.common.name')} value={d.name} disabled={!editable} onChange={(e) => patch({ name: e.target.value })} sx={{ minWidth: 240 }} />
                  <NumField label={t('mfg.recipe.batchSize')} value={d.outputQty} disabled={!editable} onChange={(v) => patch({ outputQty: v })} width={140} />
                  <NumField label={t('mfg.recipe.yieldPct')} value={d.yieldPct} disabled={!editable} onChange={(v) => patch({ yieldPct: v })} width={120} />
                </Stack>
                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                  <TextField
                    size="small"
                    type="date"
                    label={t('mfg.recipe.effectiveFrom')}
                    value={d.effectiveFrom ?? ''}
                    disabled={!editable}
                    onChange={(e) => patch({ effectiveFrom: e.target.value || null })}
                    InputLabelProps={{ shrink: true }}
                  />
                  <WarehousePick label={t('mfg.recipe.putAwayIn')} value={d.fgWarehouse} disabled={!editable} onChange={(v) => patch({ fgWarehouse: v === '' ? null : v })} />
                </Stack>
                <TextField size="small" label={t('mfg.recipe.changeReason')} value={d.changeReason} disabled={!editable} onChange={(e) => patch({ changeReason: e.target.value })} />
                <TextField size="small" multiline minRows={2} label={t('mfg.common.notes')} value={d.notes} disabled={!editable} onChange={(e) => patch({ notes: e.target.value })} />
                <Revisions rows={revisions.data ?? []} current={d.id} onOpen={(rid) => nav(`/manufacturing/boms/${rid}`)} />
              </Stack>
            ),
          },
          {
            key: 'materials',
            label: t('mfg.recipe.tabMaterials'),
            node: () => (
              <Stack spacing={1}>
                {d.lines.map((l, i) => (
                  <Paper key={l.id ?? `n${i}`} variant="outlined" sx={{ p: 1.5 }}>
                    <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} alignItems={{ md: 'center' }}>
                      <ProductPick label={t('mfg.recipe.material')} value={l.component || ''} disabled={!editable} onChange={(v) => setLine(i, { component: v === '' ? 0 : v })} />
                      <NumField label={t('mfg.common.quantity')} value={l.qty} disabled={!editable} onChange={(v) => setLine(i, { qty: v })} />
                      <NumField label={t('mfg.recipe.scrapPct')} value={l.scrapPct ?? '0'} disabled={!editable} onChange={(v) => setLine(i, { scrapPct: v })} width={100} />
                      <SelectField
                        label={t('mfg.recipe.issueMethod')}
                        value={(l.issueMethod ?? 'MANUAL') as 'MANUAL' | 'BACKFLUSH'}
                        disabled={!editable}
                        onChange={(v) => setLine(i, { issueMethod: v })}
                        options={[
                          { value: 'MANUAL', label: t('mfg.recipe.issueManual') },
                          { value: 'BACKFLUSH', label: t('mfg.recipe.issueBackflush') },
                        ]}
                      />
                      <NumField label={t('mfg.recipe.altGroup')} value={l.alternateGroup == null ? '' : String(l.alternateGroup)} disabled={!editable} onChange={(v) => setLine(i, { alternateGroup: v === '' ? null : Math.trunc(Number(v)) })} width={90} helperText={t('mfg.recipe.altHint')} />
                      <FormControlLabel control={<Switch size="small" checked={!!l.isPhantom} disabled={!editable} onChange={(e) => setLine(i, { isPhantom: e.target.checked })} />} label={t('mfg.recipe.phantom')} />
                      <FormControlLabel control={<Switch size="small" checked={!!l.isOptional} disabled={!editable} onChange={(e) => setLine(i, { isOptional: e.target.checked })} />} label={t('mfg.recipe.optional')} />
                      {editable ? (
                        <IconButton aria-label={t('common.delete')} onClick={() => patch({ lines: d.lines.filter((_, k) => k !== i) })}>
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      ) : null}
                    </Stack>
                  </Paper>
                ))}
                {editable ? <Button onClick={() => patch({ lines: [...d.lines, blankLine()] })}>{t('mfg.recipe.addMaterial')}</Button> : null}
              </Stack>
            ),
          },
          {
            key: 'outputs',
            label: t('mfg.recipe.tabOutputs'),
            node: () => (
              <Stack spacing={1}>
                <Typography variant="body2" color="text.secondary">{t('mfg.recipe.outputsHelp')}</Typography>
                {d.outputs.map((o, i) => (
                  <Paper key={o.id ?? `o${i}`} variant="outlined" sx={{ p: 1.5 }}>
                    <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} alignItems={{ md: 'center' }}>
                      <ProductPick label={t('mfg.common.item')} value={o.product || ''} disabled={!editable} onChange={(v) => setOut(i, { product: v === '' ? 0 : v })} />
                      <SelectField
                        label={t('mfg.recipe.outputKind')}
                        value={o.kind}
                        disabled={!editable}
                        onChange={(v) => setOut(i, { kind: v })}
                        options={[
                          { value: 'CO_PRODUCT', label: t('mfg.recipe.coProduct') },
                          { value: 'BY_PRODUCT', label: t('mfg.recipe.byProduct') },
                          { value: 'SCRAP', label: t('mfg.recipe.scrap') },
                        ]}
                      />
                      <NumField label={t('mfg.common.quantity')} value={o.qty} disabled={!editable} onChange={(v) => setOut(i, { qty: v })} />
                      {o.kind === 'CO_PRODUCT' ? <NumField label={t('mfg.recipe.costShare')} value={o.costSharePct ?? '0'} disabled={!editable} onChange={(v) => setOut(i, { costSharePct: v })} width={110} /> : null}
                      {editable ? (
                        <IconButton aria-label={t('common.delete')} onClick={() => patch({ outputs: d.outputs.filter((_, k) => k !== i) })}>
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      ) : null}
                    </Stack>
                  </Paper>
                ))}
                {editable ? <Button onClick={() => patch({ outputs: [...d.outputs, { product: 0, kind: 'BY_PRODUCT', qty: '1' }] })}>{t('mfg.recipe.addOutput')}</Button> : null}
              </Stack>
            ),
          },
          {
            key: 'costs',
            label: t('mfg.recipe.tabCosts'),
            node: () => (
              <Stack spacing={1}>
                <Typography variant="body2" color="text.secondary">{t('mfg.recipe.costsHelp')}</Typography>
                {extras.map((c, i) => (
                  <Stack key={c.id ?? `c${i}`} direction={{ xs: 'column', md: 'row' }} spacing={1.5}>
                    <TextField size="small" label={t('mfg.common.name')} value={c.label} disabled={!editable} onChange={(e) => setExtra(i, { label: e.target.value })} />
                    <SelectField
                      label={t('mfg.recipe.element')}
                      value={c.element}
                      disabled={!editable}
                      onChange={(v) => setExtra(i, { element: v })}
                      options={[
                        { value: 'LABOUR', label: t('mfg.recipe.labour') },
                        { value: 'OVERHEAD', label: t('mfg.recipe.overhead') },
                        { value: 'MACHINE', label: t('mfg.recipe.machine') },
                        { value: 'OTHER', label: t('mfg.recipe.otherCost') },
                      ]}
                    />
                    <SelectField
                      label={t('mfg.recipe.basis')}
                      value={c.basis}
                      disabled={!editable}
                      onChange={(v) => setExtra(i, { basis: v })}
                      options={[
                        { value: 'PER_UNIT', label: t('mfg.recipe.perUnit') },
                        { value: 'PER_BATCH', label: t('mfg.recipe.perBatch') },
                      ]}
                    />
                    <NumField label={t('mfg.common.amount')} value={c.amount} disabled={!editable} onChange={(v) => setExtra(i, { amount: v })} />
                    {editable ? (
                      <IconButton aria-label={t('common.delete')} onClick={() => patch({ additionalCosts: extras.filter((_, k) => k !== i) })}>
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    ) : null}
                  </Stack>
                ))}
                {editable ? <Button onClick={() => patch({ additionalCosts: [...extras, { label: '', element: 'LABOUR', basis: 'PER_UNIT', amount: '0' }] })}>{t('mfg.recipe.addCost')}</Button> : null}
              </Stack>
            ),
          },
          { key: 'routing', label: t('mfg.recipe.tabRouting'), node: () => <RoutingEditor bomId={d.id} editable={editable} /> },
          { key: 'view', label: t('mfg.recipe.tabExplode'), node: () => <ExplodePanel product={d.product} batch={d.outputQty} canCosts={canCosts} /> },
        ]}
      />

      {editable ? (
        <Stack direction="row" spacing={2}>
          <Button variant="contained" disabled={busy || !dirty} onClick={save}>
            {t('common.save')}
          </Button>
          {dirty ? <Typography color="text.secondary">{t('mfg.recipe.unsaved')}</Typography> : null}
        </Stack>
      ) : null}

      <ConfirmDialog
        open={reviseOpen}
        title={t('mfg.recipe.reviseTitle')}
        body={t('mfg.recipe.reviseBody')}
        requireReason={{ label: t('mfg.recipe.changeReason') }}
        onClose={() => setReviseOpen(false)}
        onConfirm={async (reason) => {
          setReviseOpen(false);
          const rev = await run(() => reviseRecipe(d.id, reason));
          if (rev) {
            refresh();
            nav(`/manufacturing/boms/${rev.id}`);
          }
        }}
      />
    </MfgPage>
  );
}

function Revisions({ rows, current, onOpen }: { rows: Recipe[]; current: number; onOpen: (id: number) => void }) {
  return (
    <Stack spacing={1}>
      <Typography variant="subtitle2">{t('mfg.recipe.revisions')}</Typography>
      <Grid
        rows={[...rows].sort((a, b) => b.revisionNo - a.revisionNo)}
        rowKey={(r) => r.id}
        onRow={(r) => (r.id === current ? undefined : onOpen(r.id))}
        cols={[
          { key: 'n', label: t('mfg.recipe.revNo'), render: (r) => `${r.revisionNo}${r.id === current ? ' ●' : ''}` },
          { key: 's', label: t('mfg.common.status'), render: (r) => <Pill value={r.status} /> },
          { key: 'f', label: t('mfg.recipe.effectiveFrom'), render: (r) => day(r.effectiveFrom) },
          { key: 'd', label: t('mfg.recipe.isDefault'), render: (r) => (r.isDefault ? t('common.yes') : '') },
          { key: 'c', label: t('mfg.recipe.changeReason'), render: (r) => r.changeReason || '—' },
        ]}
      />
    </Stack>
  );
}

function RoutingEditor({ bomId, editable }: { bomId: number; editable: boolean }) {
  const q = useQuery({ queryKey: ['mfg-routing', bomId], queryFn: () => getRouting(bomId) });
  const centres = useQuery({ queryKey: ['mfg-work-centres'], queryFn: listWorkCentres });
  const { run, busy, error, clear } = useRun();
  const [local, setLocal] = useState<{ base: unknown; ops: RoutingOp[] } | null>(null);
  const ops: RoutingOp[] = local && local.base === q.data ? local.ops : (q.data?.operations ?? []);
  const setOps = (next: RoutingOp[]) => setLocal({ base: q.data, ops: next });
  const set = (i: number, p: Partial<RoutingOp>) => setOps(ops.map((o, k) => (k === i ? { ...o, ...p } : o)));
  return (
    <Stack spacing={1}>
      <Typography variant="body2" color="text.secondary">{t('mfg.recipe.routingHelp')}</Typography>
      <ErrorLine error={error} onClose={clear} />
      {ops.map((o, i) => (
        <Stack key={o.id ?? `r${i}`} direction={{ xs: 'column', md: 'row' }} spacing={1.5}>
          <NumField label={t('mfg.recipe.step')} value={String(o.sequence)} disabled={!editable} onChange={(v) => set(i, { sequence: Math.trunc(Number(v) || 0) })} width={80} />
          <TextField size="small" label={t('mfg.common.name')} value={o.name} disabled={!editable} onChange={(e) => set(i, { name: e.target.value })} />
          <TextField select size="small" label={t('mfg.recipe.workCentre')} value={o.workCentre || ''} disabled={!editable} onChange={(e) => set(i, { workCentre: Number(e.target.value) })} sx={{ minWidth: 180 }}>
            {(centres.data ?? []).map((c) => (
              <MenuItem key={c.id} value={c.id}>{c.code} · {c.name}</MenuItem>
            ))}
          </TextField>
          <NumField label={t('mfg.recipe.setupMin')} value={o.setupMinutes} disabled={!editable} onChange={(v) => set(i, { setupMinutes: v })} width={110} />
          <NumField label={t('mfg.recipe.runMin')} value={o.runMinutesPerUnit} disabled={!editable} onChange={(v) => set(i, { runMinutesPerUnit: v })} width={130} />
          {editable ? (
            <IconButton aria-label={t('common.delete')} onClick={() => setOps(ops.filter((_, k) => k !== i))}>
              <DeleteIcon fontSize="small" />
            </IconButton>
          ) : null}
        </Stack>
      ))}
      {editable ? (
        <Stack direction="row" spacing={2}>
          <Button onClick={() => setOps([...ops, { sequence: (ops.at(-1)?.sequence ?? 0) + 10, name: '', workCentre: 0, setupMinutes: '0', runMinutesPerUnit: '0' }])}>
            {t('mfg.recipe.addStep')}
          </Button>
          <Button
            variant="contained"
            disabled={busy}
            onClick={async () => {
              const saved = await run(() => saveRouting(bomId, ops));
              if (saved) void q.refetch();
            }}
          >
            {t('mfg.recipe.saveRouting')}
          </Button>
        </Stack>
      ) : null}
    </Stack>
  );
}

function ExplodePanel({ product, batch, canCosts }: { product: number; batch: string; canCosts: boolean }) {
  const [amount, setAmount] = useState(batch || '1');
  const explode = useQuery({ queryKey: ['mfg-explode', product, amount], queryFn: () => getExplosion(product, amount || '1') });
  const used = useQuery({ queryKey: ['mfg-where-used', product], queryFn: () => getWhereUsed(product) });
  const cost = useQuery({ queryKey: ['mfg-rollup', product, amount], queryFn: () => getCostRollup(product, amount || '1'), enabled: canCosts });
  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={2} alignItems="center">
        <NumField label={t('mfg.recipe.forQty')} value={amount} onChange={setAmount} />
        {cost.data ? (
          <Typography>
            {t('mfg.recipe.rolledCost')}: <b>{money(cost.data.total)}</b> ({money(cost.data.unitCost)} / {t('mfg.recipe.unit')})
          </Typography>
        ) : null}
      </Stack>
      <Grid
        query={explode}
        rows={explode.data?.rows ?? []}
        rowKey={(r) => `${r.level}-${r.product.id}`}
        cols={[
          { key: 'l', label: t('mfg.recipe.level'), render: (r) => r.level },
          { key: 'p', label: t('mfg.common.item'), render: (r) => `${'— '.repeat(Math.max(r.level - 1, 0))}${r.product.name}${r.phantom ? ` (${t('mfg.recipe.phantom')})` : ''}` },
          { key: 'q', label: t('mfg.common.quantity'), align: 'right', render: (r) => `${qty(r.qty)} ${r.unit}` },
          { key: 'b', label: t('mfg.recipe.hasRecipe'), render: (r) => (r.hasBom ? t('common.yes') : '') },
        ]}
      />
      <Typography variant="subtitle2">{t('mfg.recipe.whereUsed')}</Typography>
      <Grid
        query={used}
        rows={used.data?.usedIn ?? []}
        empty={t('mfg.recipe.notUsed')}
        rowKey={(r) => `${r.level}-${r.productId}`}
        cols={[
          { key: 'l', label: t('mfg.recipe.level'), render: (r) => r.level },
          { key: 'p', label: t('mfg.common.item'), render: (r) => r.product },
          { key: 'q', label: t('mfg.recipe.perBatchQty'), align: 'right', render: (r) => qty(r.qtyPerBatch) },
        ]}
      />
    </Stack>
  );
}
