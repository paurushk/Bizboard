import { useState } from 'react';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import IconButton from '@mui/material/IconButton';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import DeleteIcon from '@mui/icons-material/Delete';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  advanceNcr,
  cancelInspection,
  completeInspection,
  createInspection,
  fetchCertificate,
  getInspection,
  getScorecard,
  listDefectCodes,
  listInspections,
  listNcrs,
  listTemplates,
  recordResults,
  saveDefectCode,
  saveNcr,
  saveTemplate,
  type BatchHit,
  type Inspection,
  type InspectionTemplate,
  type Ncr,
} from '@/api/mfg';
import { t } from '@/i18n';
import { BatchPick, ErrorLine, Grid, MfgPage, NumField, Pill, ProductPick, SelectField, SupplierPick, TabPanels, day, qty, useMfgRights, useRun } from './mfgShared';

export function QualityPage() {
  return (
    <MfgPage title={t('mfg.quality.title')} subtitle={t('mfg.quality.subtitle')} flag="MFG_QUALITY">
      <TabPanels
        tabs={[
          { key: 'insp', label: t('mfg.quality.tabInspections'), node: () => <Inspections /> },
          { key: 'ncr', label: t('mfg.quality.tabNcr'), node: () => <Ncrs /> },
          { key: 'tpl', label: t('mfg.quality.tabTemplates'), node: () => <Templates /> },
          { key: 'def', label: t('mfg.quality.tabDefects'), node: () => <Defects /> },
          { key: 'sc', label: t('mfg.quality.tabScorecard'), node: () => <Scorecard /> },
        ]}
      />
    </MfgPage>
  );
}

function Inspections() {
  const qc = useQueryClient();
  const { canWork } = useMfgRights();
  const [status, setStatus] = useState('');
  const [openId, setOpenId] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);
  const q = useQuery({ queryKey: ['mfg-inspections', status], queryFn: () => listInspections(status ? { status } : undefined) });
  const reload = () => void qc.invalidateQueries({ queryKey: ['mfg-inspections'] });
  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={2}>
        <SelectField
          label={t('mfg.common.status')}
          value={status}
          onChange={setStatus}
          options={[
            { value: '', label: t('mfg.common.all') },
            { value: 'DRAFT', label: t('mfg.status.DRAFT') },
            { value: 'COMPLETED', label: t('mfg.status.COMPLETED') },
          ]}
        />
        <Button variant="contained" disabled={!canWork} onClick={() => setCreating(true)}>{t('mfg.quality.newInspection')}</Button>
      </Stack>
      <Grid
        query={q}
        rows={q.data ?? []}
        rowKey={(r) => r.id}
        onRow={(r) => setOpenId(r.id)}
        cols={[
          { key: 'n', label: t('mfg.common.number'), render: (r) => r.number },
          { key: 'p', label: t('mfg.common.item'), render: (r) => r.productName },
          { key: 'b', label: t('mfg.common.batchNo'), render: (r) => r.batchNo || '—' },
          { key: 'st', label: t('mfg.quality.stage'), render: (r) => t(`mfg.quality.stage_${r.stage}`) },
          { key: 'q', label: t('mfg.common.quantity'), align: 'right', render: (r) => qty(r.qtyInspected) },
          { key: 's', label: t('mfg.common.status'), render: (r) => <Pill value={r.status} /> },
          { key: 'd', label: t('mfg.quality.decision'), render: (r) => <Pill value={r.decision} /> },
        ]}
      />
      {openId ? <InspectionDialog id={openId} onClose={() => { setOpenId(null); reload(); }} /> : null}
      {creating ? <NewInspection onClose={(id) => { setCreating(false); reload(); if (id) setOpenId(id); }} /> : null}
    </Stack>
  );
}

function NewInspection({ onClose }: { onClose: (id?: number) => void }) {
  const { run, busy, error, clear } = useRun();
  const [product, setProduct] = useState<number | ''>('');
  const [quantity, setQuantity] = useState('');
  const [stage, setStage] = useState('FINAL');
  const [tpl, setTpl] = useState<number | ''>('');
  const [batch, setBatch] = useState<BatchHit | null>(null);
  const templates = useQuery({ queryKey: ['mfg-templates'], queryFn: () => listTemplates() });
  return (
    <Dialog open onClose={() => onClose()} fullWidth maxWidth="sm">
      <DialogTitle>{t('mfg.quality.newInspection')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <ErrorLine error={error} onClose={clear} />
          <ProductPick value={product} onChange={setProduct} />
          <BatchPick label={t('mfg.quality.ofBatch')} value={batch} product={product === '' ? null : product} onChange={(b) => { setBatch(b); if (b) setProduct(b.product); }} />
          <NumField label={t('mfg.common.quantity')} value={quantity} onChange={setQuantity} />
          <SelectField
            label={t('mfg.quality.stage')}
            value={stage}
            onChange={setStage}
            size="medium"
            options={['INCOMING', 'IN_PROCESS', 'FINAL'].map((s) => ({ value: s, label: t(`mfg.quality.stage_${s}`) }))}
          />
          <TextField select size="small" label={t('mfg.quality.template')} value={tpl} onChange={(e) => setTpl(e.target.value === '' ? '' : Number(e.target.value))}>
            <MenuItem value="">{t('mfg.quality.noTemplate')}</MenuItem>
            {(templates.data ?? []).filter((x) => x.stage === stage).map((x) => (
              <MenuItem key={x.id} value={x.id}>{x.name}</MenuItem>
            ))}
          </TextField>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={() => onClose()}>{t('common.cancel')}</Button>
        <Button
          variant="contained"
          disabled={busy || product === '' || !quantity}
          onClick={async () => {
            const r = await run(() => createInspection({ product: product as number, qty: quantity, stage, sourceType: 'BATCH', batch: batch?.id, template: tpl === '' ? undefined : tpl }));
            if (r) onClose(r.id);
          }}
        >
          {t('common.create')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function InspectionDialog({ id, onClose }: { id: number; onClose: () => void }) {
  const { canWork } = useMfgRights();
  const qc = useQueryClient();
  const { run, busy, error, clear } = useRun();
  const q = useQuery({ queryKey: ['mfg-inspection', id], queryFn: () => getInspection(id) });
  const [values, setValues] = useState<Record<string, string>>({});
  const [accepted, setAccepted] = useState('');
  const [decision, setDecision] = useState('');
  const insp = q.data;
  const reload = () => void qc.invalidateQueries({ queryKey: ['mfg-inspection', id] });
  const cert = async () => {
    const html = await run(() => fetchCertificate(id));
    if (html) {
      const w = window.open('', '_blank');
      if (w) {
        w.document.write(html);
        w.document.close();
      }
    }
  };
  const draft = insp?.status === 'DRAFT';
  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>{insp ? `${insp.number} · ${insp.productName}` : t('common.loading')}</DialogTitle>
      <DialogContent>
        {insp ? (
          <Stack spacing={2} sx={{ pt: 1 }}>
            <ErrorLine error={error} onClose={clear} />
            <Stack direction="row" spacing={1}>
              <Pill value={insp.status} />
              <Pill value={insp.decision} />
            </Stack>
            <Grid<Inspection['results'][number]>
              rows={insp.results}
              rowKey={(r) => r.id}
              empty={t('mfg.quality.noParams')}
              cols={[
                { key: 'n', label: t('mfg.common.name'), render: (r) => r.name + (r.mandatory ? ' *' : '') },
                { key: 'r', label: t('mfg.quality.range'), render: (r) => (r.kind === 'NUMERIC' ? `${r.minValue ?? '—'} – ${r.maxValue ?? '—'} ${r.unit}` : r.kind === 'PASS_FAIL' ? t('mfg.quality.passFail') : '') },
                {
                  key: 'v',
                  label: t('mfg.quality.result'),
                  render: (r) =>
                    draft ? (
                      <TextField
                        size="small"
                        value={values[String(r.id)] ?? r.valueText ?? r.valueNumeric ?? ''}
                        placeholder={r.kind === 'PASS_FAIL' ? 'pass / fail' : ''}
                        onChange={(e) => setValues({ ...values, [String(r.id)]: e.target.value })}
                      />
                    ) : (
                      r.valueNumeric ?? r.valueText ?? ''
                    ),
                },
                { key: 'p', label: '', render: (r) => (r.passed === null ? '' : r.passed ? <Pill value="PASS" /> : <Pill value="FAIL" />) },
              ]}
            />
            {draft ? (
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                <Button disabled={!canWork || busy || Object.keys(values).length === 0} onClick={async () => { if (await run(() => recordResults(id, values))) { setValues({}); reload(); } }}>
                  {t('mfg.quality.saveResults')}
                </Button>
                <NumField label={t('mfg.quality.qtyAccepted')} value={accepted} onChange={setAccepted} width={150} helperText={t('mfg.quality.acceptedHelp')} />
                <SelectField
                  label={t('mfg.quality.decision')}
                  value={decision}
                  onChange={setDecision}
                  options={[
                    { value: '', label: t('mfg.quality.decideFromResults') },
                    { value: 'PASS', label: t('mfg.status.PASS') },
                    { value: 'FAIL', label: t('mfg.status.FAIL') },
                    { value: 'HOLD', label: t('mfg.status.HOLD') },
                    { value: 'REWORK', label: t('mfg.status.REWORK') },
                  ]}
                />
              </Stack>
            ) : null}
          </Stack>
        ) : null}
      </DialogContent>
      <DialogActions>
        {insp && insp.status === 'COMPLETED' ? <Button onClick={cert}>{t('mfg.quality.certificate')}</Button> : null}
        {draft ? <Button color="warning" disabled={!canWork || busy} onClick={async () => { if (await run(() => cancelInspection(id))) onClose(); }}>{t('common.cancel')}</Button> : null}
        {draft ? (
          <Button
            variant="contained"
            disabled={!canWork || busy}
            onClick={async () => {
              if (Object.keys(values).length) await run(() => recordResults(id, values));
              const r = await run(() => completeInspection(id, { decision: decision || undefined, qtyAccepted: accepted || undefined }));
              if (r) onClose();
            }}
          >
            {t('mfg.quality.complete')}
          </Button>
        ) : null}
        <Button onClick={onClose}>{t('common.close')}</Button>
      </DialogActions>
    </Dialog>
  );
}

function Ncrs() {
  const qc = useQueryClient();
  const { canWork } = useMfgRights();
  const { run, error, clear } = useRun();
  const q = useQuery({ queryKey: ['mfg-ncrs'], queryFn: () => listNcrs() });
  const [edit, setEdit] = useState<Partial<Ncr> | null>(null);
  const reload = () => void qc.invalidateQueries({ queryKey: ['mfg-ncrs'] });
  const next: Record<Ncr['status'], Ncr['status'] | null> = { OPEN: 'ACTION', ACTION: 'VERIFIED', VERIFIED: 'CLOSED', CLOSED: null };
  return (
    <Stack spacing={2}>
      <ErrorLine error={error} onClose={clear} />
      <Button variant="contained" sx={{ alignSelf: 'flex-start' }} disabled={!canWork} onClick={() => setEdit({ sourceType: 'INTERNAL', description: '', qty: '0' })}>
        {t('mfg.quality.newNcr')}
      </Button>
      <Grid
        query={q}
        rows={q.data ?? []}
        rowKey={(r) => r.id}
        cols={[
          { key: 'n', label: t('mfg.common.number'), render: (r) => r.number },
          { key: 'p', label: t('mfg.common.item'), render: (r) => r.productName || '—' },
          { key: 'd', label: t('mfg.common.description'), render: (r) => r.description },
          { key: 'due', label: t('mfg.wo.due'), render: (r) => day(r.dueDate) },
          { key: 's', label: t('mfg.common.status'), render: (r) => <Pill value={r.status} /> },
          {
            key: 'a',
            label: '',
            render: (r) => (
              <Stack direction="row" spacing={1}>
                <Button size="small" disabled={!canWork} onClick={() => setEdit(r)}>{t('common.edit')}</Button>
                {next[r.status] ? (
                  <Button size="small" disabled={!canWork} onClick={async () => { if (await run(() => advanceNcr(r.id, { status: next[r.status]! }))) reload(); }}>
                    {t(`mfg.quality.ncr_${next[r.status]}`)}
                  </Button>
                ) : null}
              </Stack>
            ),
          },
        ]}
      />
      {edit ? (
        <Dialog open onClose={() => setEdit(null)} fullWidth maxWidth="sm">
          <DialogTitle>{edit.id ? edit.number : t('mfg.quality.newNcr')}</DialogTitle>
          <DialogContent>
            <Stack spacing={2} sx={{ pt: 1 }}>
              <TextField size="small" multiline minRows={2} label={t('mfg.common.description')} value={edit.description ?? ''} onChange={(e) => setEdit({ ...edit, description: e.target.value })} />
              <TextField size="small" label={t('mfg.quality.rootCause')} value={edit.rootCause ?? ''} onChange={(e) => setEdit({ ...edit, rootCause: e.target.value })} />
              <TextField size="small" label={t('mfg.quality.actionTaken')} value={edit.actionTaken ?? ''} onChange={(e) => setEdit({ ...edit, actionTaken: e.target.value })} />
              <TextField size="small" label={t('mfg.quality.preventive')} value={edit.preventiveAction ?? ''} onChange={(e) => setEdit({ ...edit, preventiveAction: e.target.value })} />
              <TextField size="small" type="date" label={t('mfg.wo.due')} value={edit.dueDate ?? ''} onChange={(e) => setEdit({ ...edit, dueDate: e.target.value || null })} InputLabelProps={{ shrink: true }} />
              <SupplierPick value={edit.supplier ?? ''} onChange={(v) => setEdit({ ...edit, supplier: v === '' ? null : v })} />
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setEdit(null)}>{t('common.cancel')}</Button>
            <Button variant="contained" onClick={async () => { if (await run(() => saveNcr(edit.id ?? null, edit))) { setEdit(null); reload(); } }}>{t('common.save')}</Button>
          </DialogActions>
        </Dialog>
      ) : null}
    </Stack>
  );
}

function Templates() {
  const qc = useQueryClient();
  const { canPlan } = useMfgRights();
  const { run, error, clear } = useRun();
  const q = useQuery({ queryKey: ['mfg-templates'], queryFn: () => listTemplates() });
  const [edit, setEdit] = useState<Partial<InspectionTemplate> | null>(null);
  const reload = () => void qc.invalidateQueries({ queryKey: ['mfg-templates'] });
  return (
    <Stack spacing={2}>
      <ErrorLine error={error} onClose={clear} />
      <Button variant="contained" sx={{ alignSelf: 'flex-start' }} disabled={!canPlan} onClick={() => setEdit({ name: '', stage: 'FINAL', sampleSize: 1, parameters: [], isActive: true })}>
        {t('mfg.quality.newTemplate')}
      </Button>
      <Grid
        query={q}
        rows={q.data ?? []}
        rowKey={(r) => r.id}
        onRow={(r) => setEdit(r)}
        cols={[
          { key: 'n', label: t('mfg.common.name'), render: (r) => r.name },
          { key: 'st', label: t('mfg.quality.stage'), render: (r) => t(`mfg.quality.stage_${r.stage}`) },
          { key: 'pa', label: t('mfg.quality.params'), align: 'right', render: (r) => r.parameters.length },
        ]}
      />
      {edit ? (
        <Dialog open onClose={() => setEdit(null)} fullWidth maxWidth="md">
          <DialogTitle>{edit.id ? edit.name : t('mfg.quality.newTemplate')}</DialogTitle>
          <DialogContent>
            <Stack spacing={2} sx={{ pt: 1 }}>
              <Stack direction="row" spacing={2}>
                <TextField size="small" label={t('mfg.common.name')} value={edit.name ?? ''} onChange={(e) => setEdit({ ...edit, name: e.target.value })} />
                <SelectField label={t('mfg.quality.stage')} value={edit.stage ?? 'FINAL'} onChange={(v) => setEdit({ ...edit, stage: v as InspectionTemplate['stage'] })} options={['INCOMING', 'IN_PROCESS', 'FINAL'].map((s) => ({ value: s, label: t(`mfg.quality.stage_${s}`) }))} />
                <ProductPick label={t('mfg.quality.onlyFor')} value={edit.product ?? ''} onChange={(v) => setEdit({ ...edit, product: v === '' ? null : v })} />
              </Stack>
              {(edit.parameters ?? []).map((p, i) => (
                <Stack key={i} direction="row" spacing={1} alignItems="center">
                  <TextField size="small" label={t('mfg.common.name')} value={p.name} onChange={(e) => setEdit({ ...edit, parameters: edit.parameters!.map((x, k) => (k === i ? { ...x, name: e.target.value } : x)) })} />
                  <SelectField label={t('mfg.quality.kind')} value={p.kind} onChange={(v) => setEdit({ ...edit, parameters: edit.parameters!.map((x, k) => (k === i ? { ...x, kind: v as typeof p.kind } : x)) })} options={[{ value: 'NUMERIC', label: t('mfg.quality.numeric') }, { value: 'PASS_FAIL', label: t('mfg.quality.passFail') }, { value: 'TEXT', label: t('mfg.quality.text') }]} />
                  {p.kind === 'NUMERIC' ? (
                    <>
                      <NumField label={t('mfg.quality.min')} value={p.minValue ?? ''} onChange={(v) => setEdit({ ...edit, parameters: edit.parameters!.map((x, k) => (k === i ? { ...x, minValue: v || null } : x)) })} width={90} />
                      <NumField label={t('mfg.quality.max')} value={p.maxValue ?? ''} onChange={(v) => setEdit({ ...edit, parameters: edit.parameters!.map((x, k) => (k === i ? { ...x, maxValue: v || null } : x)) })} width={90} />
                      <TextField size="small" label={t('mfg.recipe.unit')} value={p.unit} onChange={(e) => setEdit({ ...edit, parameters: edit.parameters!.map((x, k) => (k === i ? { ...x, unit: e.target.value } : x)) })} sx={{ width: 90 }} />
                    </>
                  ) : null}
                  <IconButton aria-label={t('common.delete')} onClick={() => setEdit({ ...edit, parameters: edit.parameters!.filter((_, k) => k !== i) })}>
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </Stack>
              ))}
              <Button onClick={() => setEdit({ ...edit, parameters: [...(edit.parameters ?? []), { name: '', kind: 'NUMERIC', minValue: null, maxValue: null, unit: '', mandatory: true }] })}>
                {t('mfg.quality.addParam')}
              </Button>
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setEdit(null)}>{t('common.cancel')}</Button>
            <Button variant="contained" disabled={!canPlan} onClick={async () => { if (await run(() => saveTemplate(edit.id ?? null, edit))) { setEdit(null); reload(); } }}>{t('common.save')}</Button>
          </DialogActions>
        </Dialog>
      ) : null}
    </Stack>
  );
}

function Defects() {
  const qc = useQueryClient();
  const { canPlan } = useMfgRights();
  const { run, error, clear } = useRun();
  const q = useQuery({ queryKey: ['mfg-defects'], queryFn: listDefectCodes });
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [severity, setSeverity] = useState('MINOR');
  return (
    <Stack spacing={2}>
      <ErrorLine error={error} onClose={clear} />
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
        <TextField size="small" label={t('mfg.common.code')} value={code} onChange={(e) => setCode(e.target.value)} />
        <TextField size="small" label={t('mfg.common.name')} value={name} onChange={(e) => setName(e.target.value)} />
        <SelectField label={t('mfg.quality.severity')} value={severity} onChange={setSeverity} options={['MINOR', 'MAJOR', 'CRITICAL'].map((s) => ({ value: s, label: t(`mfg.quality.sev_${s}`) }))} />
        <Button
          variant="contained"
          disabled={!canPlan || !code || !name}
          onClick={async () => {
            if (await run(() => saveDefectCode(null, { code, name, severity: severity as 'MINOR' | 'MAJOR' | 'CRITICAL' }))) {
              setCode('');
              setName('');
              void qc.invalidateQueries({ queryKey: ['mfg-defects'] });
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
          { key: 'c', label: t('mfg.common.code'), render: (r) => r.code },
          { key: 'n', label: t('mfg.common.name'), render: (r) => r.name },
          { key: 's', label: t('mfg.quality.severity'), render: (r) => t(`mfg.quality.sev_${r.severity}`) },
        ]}
      />
    </Stack>
  );
}

function Scorecard() {
  const q = useQuery({ queryKey: ['mfg-scorecard'], queryFn: () => getScorecard() });
  return (
    <Stack spacing={2}>
      <Typography variant="body2" color="text.secondary">{t('mfg.quality.scorecardHelp')}</Typography>
      <Grid
        query={q}
        rows={q.data?.suppliers ?? []}
        rowKey={(r) => r.supplier}
        cols={[
          { key: 'n', label: t('mfg.common.supplier'), render: (r) => r.name },
          { key: 'r', label: t('mfg.quality.receipts'), align: 'right', render: (r) => r.receipts },
          { key: 'q', label: t('mfg.quality.received'), align: 'right', render: (r) => qty(r.receivedQty) },
          { key: 'j', label: t('mfg.wo.rejected'), align: 'right', render: (r) => qty(r.rejectedQty) },
          { key: 'p', label: t('mfg.quality.rejectionPct'), align: 'right', render: (r) => `${r.rejectionPct}%` },
          { key: 'o', label: t('mfg.quality.onTime'), align: 'right', render: (r) => (r.onTimePct == null ? '—' : `${r.onTimePct}%`) },
          { key: 'l', label: t('mfg.quality.leadDays'), align: 'right', render: (r) => r.avgLeadDays ?? '—' },
          { key: 'nc', label: t('mfg.quality.openNcrs'), align: 'right', render: (r) => r.openNcrs },
        ]}
      />
    </Stack>
  );
}
