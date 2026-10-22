import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import FormControlLabel from '@mui/material/FormControlLabel';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  completeMaintenance,
  createOperator,
  endDowntime,
  getMaintenanceDue,
  getUtilisation,
  listDowntime,
  listDowntimeReasons,
  listJobCards,
  listMachines,
  listMaintenanceLog,
  listMaintenancePlans,
  listOperators,
  listWorkCentres,
  reportBreakdown,
  resolveBreakdown,
  saveDowntimeReason,
  saveMachine,
  saveMaintenancePlan,
  saveWorkCentre,
  setOperatorActive,
  setOperatorPin,
  startDowntime,
  jobCardAction,
  type JobCard,
} from '@/api/mfg';
import { isRuntimeFlagEnabled } from '@/config/featureFlags';
import { t } from '@/i18n';
import { ErrorLine, Grid, MfgPage, NumField, Pill, TabPanels, day, qty, stamp, todayIso, useMfgRights, useRun } from './mfgShared';
import { SubcontractDialog } from './SubcontractDialog';

export function ShopFloorPage() {
  return (
    <MfgPage title={t('mfg.floor.title')} subtitle={t('mfg.floor.subtitle')} flag="MFG_SHOP_FLOOR">
      <TabPanels
        tabs={[
          { key: 'cards', label: t('mfg.floor.tabCards'), node: () => <Cards /> },
          { key: 'down', label: t('mfg.floor.tabDowntime'), node: () => <Downtime /> },
          { key: 'mach', label: t('mfg.floor.tabMachines'), node: () => <Machines /> },
          { key: 'wc', label: t('mfg.floor.tabCentres'), node: () => <Centres /> },
          { key: 'ops', label: t('mfg.floor.tabOperators'), node: () => <Operators /> },
          { key: 'util', label: t('mfg.floor.tabUtilisation'), node: () => <Utilisation /> },
        ]}
      />
    </MfgPage>
  );
}

function Cards() {
  const qc = useQueryClient();
  const { canWork } = useMfgRights();
  const { run, error, clear } = useRun();
  const [status, setStatus] = useState('IN_PROGRESS');
  const [sendCard, setSendCard] = useState<JobCard | null>(null);
  const q = useQuery({ queryKey: ['mfg-cards-all', status], queryFn: () => listJobCards(status ? { status } : undefined), refetchInterval: 30_000 });
  const reload = () => void qc.invalidateQueries({ queryKey: ['mfg-cards-all'] });
  return (
    <Stack spacing={2}>
      <ErrorLine error={error} onClose={clear} />
      <TextField select size="small" label={t('mfg.common.status')} value={status} onChange={(e) => setStatus(e.target.value)} sx={{ width: 220 }}>
        <MenuItem value="">{t('mfg.common.all')}</MenuItem>
        {['PLANNED', 'IN_PROGRESS', 'PAUSED', 'DONE'].map((s) => <MenuItem key={s} value={s}>{t(`mfg.status.${s}`)}</MenuItem>)}
      </TextField>
      <Grid
        query={q}
        rows={q.data ?? []}
        rowKey={(c) => c.id}
        cols={[
          { key: 'w', label: t('mfg.wo.title'), render: (c) => c.workOrderNumber },
          { key: 's', label: t('mfg.recipe.step'), render: (c) => `${c.sequence} · ${c.name}` },
          { key: 'wc', label: t('mfg.recipe.workCentre'), render: (c) => c.workCentreCode },
          { key: 'st', label: t('mfg.common.status'), render: (c) => <Pill value={c.status} /> },
          { key: 'g', label: t('mfg.wo.good'), align: 'right', render: (c) => `${qty(c.qtyGood)} / ${qty(c.qtyPlanned)}` },
          { key: 'r', label: t('mfg.wo.rejected'), align: 'right', render: (c) => qty(c.qtyRejected) },
          { key: 'm', label: t('mfg.floor.minutes'), align: 'right', render: (c) => `${qty(c.minutesWorked)} / ${qty(c.plannedMinutes)}` },
          {
            key: 'a',
            label: '',
            render: (c) => {
              if (c.isSubcontract && c.jobworkOrderId) return <Typography variant="body2" color="text.secondary">{t('mfg.sub.atJobWorker')}</Typography>;
              if (c.isSubcontract && c.status === 'PLANNED' && isRuntimeFlagEnabled('MFG_JOB_WORK')) {
                return <Button size="small" variant="contained" disabled={!canWork} onClick={() => setSendCard(c)}>{t('mfg.sub.sendButton')}</Button>;
              }
              return c.status === 'DONE' ? <Button size="small" disabled={!canWork} onClick={async () => { if (await run(() => jobCardAction(c.id, 'reopen'))) reload(); }}>{t('mfg.wo.reopen')}</Button> : null;
            },
          },
        ]}
      />
      <SubcontractDialog card={sendCard} onClose={() => setSendCard(null)} onDone={reload} />
    </Stack>
  );
}

function Downtime() {
  const qc = useQueryClient();
  const { canWork, canPlan } = useMfgRights();
  const { run, error, clear } = useRun();
  const centres = useQuery({ queryKey: ['mfg-work-centres'], queryFn: listWorkCentres });
  const reasons = useQuery({ queryKey: ['mfg-down-reasons'], queryFn: listDowntimeReasons });
  const events = useQuery({ queryKey: ['mfg-downtime'], queryFn: () => listDowntime() });
  const [wc, setWc] = useState<number | ''>('');
  const [reason, setReason] = useState<number | ''>('');
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const reload = () => {
    void qc.invalidateQueries({ queryKey: ['mfg-downtime'] });
    void qc.invalidateQueries({ queryKey: ['mfg-down-reasons'] });
  };
  return (
    <Stack spacing={2}>
      <ErrorLine error={error} onClose={clear} />
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
        <TextField select size="small" label={t('mfg.recipe.workCentre')} value={wc} onChange={(e) => setWc(Number(e.target.value))} sx={{ minWidth: 200 }}>
          {(centres.data ?? []).map((c) => <MenuItem key={c.id} value={c.id}>{c.code} · {c.name}</MenuItem>)}
        </TextField>
        <TextField select size="small" label={t('mfg.floor.reason')} value={reason} onChange={(e) => setReason(Number(e.target.value))} sx={{ minWidth: 200 }}>
          {(reasons.data ?? []).map((r) => <MenuItem key={r.id} value={r.id}>{r.name}</MenuItem>)}
        </TextField>
        <Button variant="contained" disabled={!canWork || wc === '' || reason === ''} onClick={async () => { if (await run(() => startDowntime({ workCentre: wc as number, reason: reason as number }))) reload(); }}>
          {t('mfg.floor.startDowntime')}
        </Button>
      </Stack>
      <Grid
        query={events}
        rows={events.data ?? []}
        rowKey={(e) => e.id}
        cols={[
          { key: 'w', label: t('mfg.recipe.workCentre'), render: (e) => e.workCentreCode },
          { key: 'r', label: t('mfg.floor.reason'), render: (e) => e.reasonName },
          { key: 's', label: t('mfg.floor.started'), render: (e) => stamp(e.startedAt) },
          { key: 'e', label: t('mfg.floor.ended'), render: (e) => (e.endedAt ? stamp(e.endedAt) : <Pill value="OPEN" />) },
          { key: 'm', label: t('mfg.floor.minutes'), align: 'right', render: (e) => qty(e.minutes) },
          { key: 'a', label: '', render: (e) => (!e.endedAt ? <Button size="small" disabled={!canWork} onClick={async () => { if (await run(() => endDowntime(e.id))) reload(); }}>{t('mfg.floor.endDowntime')}</Button> : null) },
        ]}
      />
      <Typography variant="subtitle2">{t('mfg.floor.reasons')}</Typography>
      <Stack direction="row" spacing={2}>
        <TextField size="small" label={t('mfg.common.code')} value={code} onChange={(e) => setCode(e.target.value)} />
        <TextField size="small" label={t('mfg.common.name')} value={name} onChange={(e) => setName(e.target.value)} />
        <Button disabled={!canPlan || !code || !name} onClick={async () => { if (await run(() => saveDowntimeReason(null, { code, name }))) { setCode(''); setName(''); reload(); } }}>{t('common.add')}</Button>
      </Stack>
    </Stack>
  );
}

function Machines() {
  const qc = useQueryClient();
  const { canWork, canPlan } = useMfgRights();
  const { run, error, clear } = useRun();
  const machines = useQuery({ queryKey: ['mfg-machines'], queryFn: listMachines });
  const plans = useQuery({ queryKey: ['mfg-mplans'], queryFn: listMaintenancePlans });
  const due = useQuery({ queryKey: ['mfg-mdue'], queryFn: getMaintenanceDue });
  const log = useQuery({ queryKey: ['mfg-mlog'], queryFn: () => listMaintenanceLog() });
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [planFor, setPlanFor] = useState<number | ''>('');
  const [planName, setPlanName] = useState('');
  const [days, setDays] = useState('');
  const reload = () => ['mfg-machines', 'mfg-mplans', 'mfg-mdue', 'mfg-mlog'].forEach((k) => void qc.invalidateQueries({ queryKey: [k] }));
  return (
    <Stack spacing={2}>
      <ErrorLine error={error} onClose={clear} />
      {(due.data?.plans ?? []).some((p) => p.overdue) ? <Alert severity="warning">{t('mfg.floor.maintenanceOverdue')}</Alert> : null}
      <Stack direction="row" spacing={2}>
        <TextField size="small" label={t('mfg.common.code')} value={code} onChange={(e) => setCode(e.target.value)} />
        <TextField size="small" label={t('mfg.common.name')} value={name} onChange={(e) => setName(e.target.value)} />
        <Button variant="contained" disabled={!canPlan || !code || !name} onClick={async () => { if (await run(() => saveMachine(null, { code, name }))) { setCode(''); setName(''); reload(); } }}>{t('mfg.floor.addMachine')}</Button>
      </Stack>
      <Grid
        query={machines}
        rows={machines.data ?? []}
        rowKey={(m) => m.id}
        cols={[
          { key: 'c', label: t('mfg.common.code'), render: (m) => m.code },
          { key: 'n', label: t('mfg.common.name'), render: (m) => m.name },
          { key: 'h', label: t('mfg.floor.runHours'), align: 'right', render: (m) => qty(m.runHours) },
          { key: 'b', label: '', render: (m) => <Button size="small" color="warning" disabled={!canWork} onClick={async () => { if (await run(() => reportBreakdown(m.id, t('mfg.floor.breakdownDefault')))) reload(); }}>{t('mfg.floor.reportBreakdown')}</Button> },
        ]}
      />
      <Typography variant="subtitle2">{t('mfg.floor.plans')}</Typography>
      <Stack direction="row" spacing={2}>
        <TextField select size="small" label={t('mfg.floor.machine')} value={planFor} onChange={(e) => setPlanFor(Number(e.target.value))} sx={{ minWidth: 180 }}>
          {(machines.data ?? []).map((m) => <MenuItem key={m.id} value={m.id}>{m.name}</MenuItem>)}
        </TextField>
        <TextField size="small" label={t('mfg.common.name')} value={planName} onChange={(e) => setPlanName(e.target.value)} />
        <NumField label={t('mfg.floor.everyDays')} value={days} onChange={setDays} />
        <Button disabled={!canPlan || planFor === '' || !planName || !days} onClick={async () => { if (await run(() => saveMaintenancePlan(null, { machine: planFor as number, name: planName, intervalDays: Math.trunc(Number(days)) }))) { setPlanName(''); setDays(''); reload(); } }}>{t('common.add')}</Button>
      </Stack>
      <Grid
        query={due}
        rows={due.data?.plans ?? []}
        rowKey={(p) => p.plan}
        cols={[
          { key: 'm', label: t('mfg.floor.machine'), render: (p) => p.machine },
          { key: 'n', label: t('mfg.common.name'), render: (p) => p.name },
          { key: 'd', label: t('mfg.floor.dueOn'), render: (p) => day(p.dueOn) },
          { key: 's', label: t('mfg.common.status'), render: (p) => (p.overdue ? <Pill value="OVERDUE" /> : <Pill value="OK" />) },
          { key: 'a', label: '', render: (p) => <Button size="small" disabled={!canWork} onClick={async () => { if (await run(() => completeMaintenance(p.plan, { doneOn: todayIso() }))) reload(); }}>{t('mfg.floor.markDone')}</Button> },
        ]}
      />
      <Typography variant="caption" color="text.secondary">{(plans.data ?? []).length} {t('mfg.floor.plans')}</Typography>
      <Typography variant="subtitle2">{t('mfg.floor.log')}</Typography>
      <Grid
        query={log}
        rows={log.data ?? []}
        rowKey={(l) => l.id}
        cols={[
          { key: 'm', label: t('mfg.floor.machine'), render: (l) => l.machineName },
          { key: 'k', label: t('mfg.floor.kind'), render: (l) => (l.kind === 'BREAKDOWN' ? t('mfg.floor.breakdown') : t('mfg.floor.preventive')) },
          { key: 'r', label: t('mfg.floor.started'), render: (l) => stamp(l.reportedAt) },
          { key: 'e', label: t('mfg.floor.ended'), render: (l) => (l.resolvedAt ? stamp(l.resolvedAt) : <Pill value="OPEN" />) },
          { key: 'a', label: '', render: (l) => (l.kind === 'BREAKDOWN' && !l.resolvedAt ? <Button size="small" disabled={!canWork} onClick={async () => { if (await run(() => resolveBreakdown(l.id, {}))) reload(); }}>{t('mfg.floor.resolve')}</Button> : null) },
        ]}
      />
    </Stack>
  );
}

function Centres() {
  const qc = useQueryClient();
  const { canPlan } = useMfgRights();
  const { run, error, clear } = useRun();
  const q = useQuery({ queryKey: ['mfg-work-centres'], queryFn: listWorkCentres });
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [hours, setHours] = useState('8');
  const [labour, setLabour] = useState('');
  const [machine, setMachine] = useState('');
  const [overhead, setOverhead] = useState('');
  return (
    <Stack spacing={2}>
      <ErrorLine error={error} onClose={clear} />
      <Typography variant="body2" color="text.secondary">{t('mfg.floor.centresHelp')}</Typography>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} alignItems={{ md: 'center' }}>
        <TextField size="small" label={t('mfg.common.code')} value={code} onChange={(e) => setCode(e.target.value)} />
        <TextField size="small" label={t('mfg.common.name')} value={name} onChange={(e) => setName(e.target.value)} />
        <NumField label={t('mfg.floor.hoursPerDay')} value={hours} onChange={setHours} />
        <NumField label={t('mfg.floor.labourRate')} value={labour} onChange={setLabour} />
        <NumField label={t('mfg.floor.machineRate')} value={machine} onChange={setMachine} />
        <NumField label={t('mfg.floor.overheadRate')} value={overhead} onChange={setOverhead} />
        <Button
          variant="contained"
          disabled={!canPlan || !code || !name}
          onClick={async () => {
            if (await run(() => saveWorkCentre(null, { code, name, hoursPerDay: hours || '8', labourRate: labour || '0', machineRate: machine || '0', overheadRate: overhead || '0' }))) {
              setCode('');
              setName('');
              void qc.invalidateQueries({ queryKey: ['mfg-work-centres'] });
            }
          }}
        >
          {t('common.add')}
        </Button>
      </Stack>
      <Grid
        query={q}
        rows={q.data ?? []}
        rowKey={(c) => c.id}
        cols={[
          { key: 'c', label: t('mfg.common.code'), render: (c) => c.code },
          { key: 'n', label: t('mfg.common.name'), render: (c) => c.name },
          { key: 'h', label: t('mfg.floor.hoursPerDay'), align: 'right', render: (c) => qty(c.hoursPerDay) },
          { key: 'l', label: t('mfg.floor.labourRate'), align: 'right', render: (c) => qty(c.labourRate) },
          { key: 'm', label: t('mfg.floor.machineRate'), align: 'right', render: (c) => qty(c.machineRate) },
          { key: 'o', label: t('mfg.floor.overheadRate'), align: 'right', render: (c) => qty(c.overheadRate) },
        ]}
      />
    </Stack>
  );
}

function Operators() {
  const qc = useQueryClient();
  const { canPlan } = useMfgRights();
  const { run, error, clear } = useRun();
  const q = useQuery({ queryKey: ['mfg-operators'], queryFn: listOperators });
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [pin, setPin] = useState('');
  const [newPin, setNewPin] = useState<Record<number, string>>({});
  const reload = () => void qc.invalidateQueries({ queryKey: ['mfg-operators'] });
  return (
    <Stack spacing={2}>
      <ErrorLine error={error} onClose={clear} />
      <Alert severity="info">{t('mfg.floor.operatorsHelp')}</Alert>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
        <TextField size="small" label={t('mfg.common.code')} value={code} onChange={(e) => setCode(e.target.value)} />
        <TextField size="small" label={t('mfg.common.name')} value={name} onChange={(e) => setName(e.target.value)} />
        <TextField size="small" type="password" label={t('mfg.floor.pin')} value={pin} inputProps={{ inputMode: 'numeric', maxLength: 8, autoComplete: 'new-password' }} onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))} />
        <Button variant="contained" disabled={!canPlan || !code || !name || pin.length < 4} onClick={async () => { if (await run(() => createOperator({ code, name, pin }))) { setCode(''); setName(''); setPin(''); reload(); } }}>{t('common.add')}</Button>
      </Stack>
      <Grid
        query={q}
        rows={q.data ?? []}
        rowKey={(o) => o.id}
        cols={[
          { key: 'c', label: t('mfg.common.code'), render: (o) => o.code },
          { key: 'n', label: t('mfg.common.name'), render: (o) => o.name },
          { key: 'a', label: t('mfg.common.status'), render: (o) => <FormControlLabel control={<Switch size="small" checked={o.isActive} disabled={!canPlan} onChange={async (e) => { if (await run(() => setOperatorActive(o.id, e.target.checked))) reload(); }} />} label={o.isActive ? t('mfg.floor.active') : t('mfg.floor.inactive')} /> },
          { key: 'l', label: t('mfg.floor.locked'), render: (o) => (o.lockedUntil ? stamp(o.lockedUntil) : '') },
          {
            key: 'p',
            label: t('mfg.floor.pin'),
            render: (o) => (
              <Stack direction="row" spacing={1}>
                <TextField size="small" type="password" value={newPin[o.id] ?? ''} inputProps={{ inputMode: 'numeric', maxLength: 8, autoComplete: 'new-password' }} onChange={(e) => setNewPin({ ...newPin, [o.id]: e.target.value.replace(/\D/g, '') })} sx={{ width: 110 }} />
                <Button size="small" disabled={!canPlan || (newPin[o.id] ?? '').length < 4} onClick={async () => { if (await run(() => setOperatorPin(o.id, newPin[o.id]))) { setNewPin({ ...newPin, [o.id]: '' }); reload(); } }}>{t('mfg.floor.changePin')}</Button>
              </Stack>
            ),
          },
        ]}
      />
    </Stack>
  );
}

function Utilisation() {
  const [from, setFrom] = useState(todayIso().slice(0, 8) + '01');
  const [to, setTo] = useState(todayIso());
  const q = useQuery({ queryKey: ['mfg-util', from, to], queryFn: () => getUtilisation(from, to) });
  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={2}>
        <TextField size="small" type="date" label={t('mfg.common.from')} value={from} onChange={(e) => setFrom(e.target.value)} InputLabelProps={{ shrink: true }} />
        <TextField size="small" type="date" label={t('mfg.common.to')} value={to} onChange={(e) => setTo(e.target.value)} InputLabelProps={{ shrink: true }} />
      </Stack>
      <Grid
        query={q}
        rows={q.data?.workCentres ?? []}
        rowKey={(w) => w.code}
        cols={[
          { key: 'c', label: t('mfg.recipe.workCentre'), render: (w) => `${w.code} · ${w.name}` },
          { key: 'w', label: t('mfg.floor.worked'), align: 'right', render: (w) => qty(w.workedMinutes) },
          { key: 'a', label: t('mfg.floor.available'), align: 'right', render: (w) => qty(w.availableMinutes) },
          { key: 'u', label: t('mfg.floor.utilisation'), align: 'right', render: (w) => (w.utilisationPct == null ? '—' : `${w.utilisationPct}%`) },
          { key: 'd', label: t('mfg.floor.downtimeMin'), align: 'right', render: (w) => qty(w.downtimeMinutes) },
          { key: 'g', label: t('mfg.wo.good'), align: 'right', render: (w) => qty(w.good) },
          { key: 'ph', label: t('mfg.floor.perHour'), align: 'right', render: (w) => (w.goodPerHour == null ? '—' : qty(w.goodPerHour)) },
        ]}
      />
      <Typography variant="subtitle2">{t('mfg.floor.people')}</Typography>
      <Grid
        query={q}
        rows={q.data?.people ?? []}
        rowKey={(p) => p.who}
        cols={[
          { key: 'w', label: t('mfg.common.name'), render: (p) => p.who },
          { key: 'h', label: t('mfg.floor.hours'), align: 'right', render: (p) => qty(p.hours) },
          { key: 'c', label: t('mfg.floor.cards'), align: 'right', render: (p) => p.cards },
        ]}
      />
    </Stack>
  );
}
