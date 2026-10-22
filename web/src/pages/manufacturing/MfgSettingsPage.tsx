import { useRef, useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import FormControlLabel from '@mui/material/FormControlLabel';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  downloadRecipeExport,
  downloadRecipeTemplate,
  getMfgSettings,
  importRecipes,
  saveBlob,
  updateMfgSettings,
  type ImportResult,
  type MfgSettings,
} from '@/api/mfg';
import { isRuntimeFlagEnabled } from '@/config/featureFlags';
import { t } from '@/i18n';
import { ErrorLine, Grid, MfgPage, NumField, SelectField, WarehousePick, useMfgRights, useRun } from './mfgShared';
import { useAuth } from '@/auth/AuthContext';

const FLAGS = [
  ['MFG_PLANNING', 'mfg.settings.flagPlanning'],
  ['MFG_QUALITY', 'mfg.settings.flagQuality'],
  ['MFG_JOB_WORK', 'mfg.settings.flagJobWork'],
  ['MFG_COSTING_GL', 'mfg.settings.flagCostingGl'],
  ['MFG_SHOP_FLOOR', 'mfg.settings.flagShopFloor'],
] as const;

export function MfgSettingsPage() {
  const qc = useQueryClient();
  const { canPlan } = useMfgRights();
  const { user } = useAuth();
  const { run, busy, error, clear } = useRun();
  const q = useQuery({ queryKey: ['mfg-settings'], queryFn: getMfgSettings });
  const [edit, setEdit] = useState<{ base: MfgSettings; data: MfgSettings } | null>(null);
  const [saved, setSaved] = useState(false);
  const s: MfgSettings | null = edit && edit.base === q.data ? edit.data : (q.data ?? null);
  if (!s) return <MfgPage title={t('mfg.settings.title')}>{null}</MfgPage>;
  const set = (p: Partial<MfgSettings>) => { setEdit({ base: q.data!, data: { ...s, ...p } }); setSaved(false); };
  const save = async () => {
    const out = await run(() => updateMfgSettings(s));
    if (out) {
      setSaved(true);
      void qc.invalidateQueries({ queryKey: ['mfg-settings'] });
    }
  };
  const tabletUrl = `${window.location.origin}/floor?company=${user?.companyId ?? ''}`;
  return (
    <MfgPage title={t('mfg.settings.title')} subtitle={t('mfg.settings.subtitle')}>
      <ErrorLine error={error} onClose={clear} />
      {saved ? <Alert severity="success" onClose={() => setSaved(false)}>{t('mfg.settings.saved')}</Alert> : null}

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={2}>
          <Typography variant="subtitle1">{t('mfg.settings.flow')}</Typography>
          <SelectField
            label={t('mfg.settings.issueMode')}
            size="medium"
            value={s.defaultIssueMode}
            disabled={!canPlan}
            onChange={(v) => set({ defaultIssueMode: v })}
            options={[
              { value: 'AUTO_AT_RELEASE', label: t('mfg.settings.modeAuto') },
              { value: 'SEPARATE', label: t('mfg.settings.modeSeparate') },
            ]}
          />
          <Typography variant="caption" color="text.secondary">{t('mfg.settings.issueModeHelp')}</Typography>
          <FormControlLabel control={<Switch checked={s.backflushDefault} disabled={!canPlan} onChange={(e) => set({ backflushDefault: e.target.checked })} />} label={t('mfg.settings.backflush')} />
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
            <WarehousePick label={t('mfg.settings.rmWarehouse')} value={s.rmWarehouse} disabled={!canPlan} onChange={(v) => set({ rmWarehouse: v === '' ? null : v })} />
            <WarehousePick label={t('mfg.settings.fgWarehouse')} value={s.fgWarehouse} disabled={!canPlan} onChange={(v) => set({ fgWarehouse: v === '' ? null : v })} />
            <WarehousePick label={t('mfg.settings.scrapWarehouse')} value={s.scrapWarehouse} disabled={!canPlan} onChange={(v) => set({ scrapWarehouse: v === '' ? null : v })} />
            <WarehousePick label={t('mfg.settings.quarantineWarehouse')} value={s.quarantineWarehouse} disabled={!canPlan} onChange={(v) => set({ quarantineWarehouse: v === '' ? null : v })} />
          </Stack>
          <Typography variant="subtitle1">{t('mfg.settings.limits')}</Typography>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
            <NumField label={t('mfg.settings.backdateDays')} value={String(s.backdateDays)} disabled={!canPlan} onChange={(v) => set({ backdateDays: Math.trunc(Number(v) || 0) })} width={170} />
            <NumField label={t('mfg.settings.extraIssuePct')} value={s.extraIssueApprovalPct} disabled={!canPlan} onChange={(v) => set({ extraIssueApprovalPct: v })} width={190} />
            <NumField label={t('mfg.settings.overReceiptPct')} value={s.overReceiptPct} disabled={!canPlan} onChange={(v) => set({ overReceiptPct: v })} width={170} />
            <NumField label={t('mfg.settings.finalTolerance')} value={s.finalReceiptTolerancePct ?? ''} disabled={!canPlan} onChange={(v) => set({ finalReceiptTolerancePct: v || null })} width={190} />
          </Stack>
          <Typography variant="subtitle1">{t('mfg.settings.jobWorkRules')}</Typography>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
            <SelectField label={t('mfg.settings.itc04')} size="medium" value={s.itc04Frequency} disabled={!canPlan} onChange={(v) => set({ itc04Frequency: v })} options={[{ value: 'HALF_YEARLY', label: t('mfg.settings.halfYearly') }, { value: 'ANNUAL', label: t('mfg.settings.annual') }]} />
            <NumField label={t('mfg.settings.inputLimit')} value={String(s.jwInputLimitDays)} disabled={!canPlan} onChange={(v) => set({ jwInputLimitDays: Math.trunc(Number(v) || 0) })} width={190} />
            <NumField label={t('mfg.settings.capitalLimit')} value={String(s.jwCapitalLimitDays)} disabled={!canPlan} onChange={(v) => set({ jwCapitalLimitDays: Math.trunc(Number(v) || 0) })} width={190} />
          </Stack>
          <Button variant="contained" sx={{ alignSelf: 'flex-start' }} disabled={!canPlan || busy} onClick={save}>{t('common.save')}</Button>
        </Stack>
      </Paper>

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={1}>
          <Typography variant="subtitle1">{t('mfg.settings.modules')}</Typography>
          <Typography variant="body2" color="text.secondary">{t('mfg.settings.modulesHelp')}</Typography>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            {FLAGS.map(([key, label]) => (
              <Chip key={key} label={t(label)} color={isRuntimeFlagEnabled(key) ? 'success' : 'default'} variant={isRuntimeFlagEnabled(key) ? 'filled' : 'outlined'} />
            ))}
          </Stack>
          {isRuntimeFlagEnabled('MFG_SHOP_FLOOR') ? (
            <Stack spacing={0.5} sx={{ pt: 1 }}>
              <TextField size="small" label={t('mfg.settings.tabletLink')} value={tabletUrl} InputProps={{ readOnly: true }} />
              <Typography variant="caption" color="text.secondary">{t('mfg.settings.tabletHelp')}</Typography>
            </Stack>
          ) : null}
        </Stack>
      </Paper>

      <RecipeData canPlan={canPlan} />
    </MfgPage>
  );
}

function RecipeData({ canPlan }: { canPlan: boolean }) {
  const { run, busy, error, clear } = useRun();
  const file = useRef<HTMLInputElement>(null);
  const [picked, setPicked] = useState<File | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const check = async (commit: boolean) => {
    if (!picked) return;
    const out = await run(() => importRecipes(picked, commit));
    if (out) setResult(out);
  };
  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Stack spacing={2}>
        <Typography variant="subtitle1">{t('mfg.settings.recipeData')}</Typography>
        <Typography variant="body2" color="text.secondary">{t('mfg.settings.recipeDataHelp')}</Typography>
        <ErrorLine error={error} onClose={clear} />
        <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
          <Button onClick={async () => { const b = await run(downloadRecipeTemplate); if (b) saveBlob(b, 'recipe-template.csv'); }}>{t('mfg.settings.template')}</Button>
          <Button onClick={async () => { const b = await run(downloadRecipeExport); if (b) saveBlob(b, 'recipes.csv'); }}>{t('mfg.settings.exportAll')}</Button>
          <Button onClick={() => file.current?.click()} disabled={!canPlan}>{t('mfg.settings.chooseFile')}</Button>
          <input ref={file} type="file" accept=".csv,.xlsx" hidden onChange={(e) => { setPicked(e.target.files?.[0] ?? null); setResult(null); }} />
          {picked ? <Typography sx={{ alignSelf: 'center' }}>{picked.name}</Typography> : null}
        </Stack>
        {picked ? (
          <Stack direction="row" spacing={2}>
            <Button disabled={busy} onClick={() => void check(false)}>{t('mfg.settings.check')}</Button>
            <Button variant="contained" disabled={busy || !canPlan || !result || result.errors.length > 0} onClick={() => void check(true)}>{t('mfg.settings.importNow')}</Button>
          </Stack>
        ) : null}
        {result ? (
          <Stack spacing={1}>
            <Alert severity={result.errors.length ? 'warning' : 'success'}>
              {result.committed ? t('mfg.settings.imported', { n: result.created }) : t('mfg.settings.checked', { n: result.recipes.length, e: result.errors.length })}
            </Alert>
            <Grid rows={result.errors} rowKey={(e) => `${e.row}-${e.message}`} cols={[{ key: 'r', label: t('mfg.settings.row'), render: (e) => e.row }, { key: 'm', label: t('mfg.settings.problem'), render: (e) => e.message }]} />
            <Grid rows={result.recipes} rowKey={(r) => `${r.product}-${r.firstRow}`} cols={[{ key: 'p', label: t('mfg.common.item'), render: (r) => r.product }, { key: 'n', label: t('mfg.common.name'), render: (r) => r.name }, { key: 'm', label: t('mfg.recipe.tabMaterials'), align: 'right', render: (r) => r.materials }, { key: 'o', label: t('mfg.recipe.tabOutputs'), align: 'right', render: (r) => r.outputs }]} />
          </Stack>
        ) : null}
      </Stack>
    </Paper>
  );
}
