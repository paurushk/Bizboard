import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import FormControlLabel from '@mui/material/FormControlLabel';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink, useParams } from 'react-router-dom';
import {
  approveIssue,
  createIssue,
  createJobCards,
  createReceipt,
  createReturn,
  discardIssue,
  discardReceipt,
  discardReturn,
  getAvailability,
  getWorkOrder,
  jobCardAction,
  listIssues,
  listJobCards,
  listReceipts,
  listReturns,
  postIssue,
  postReceipt,
  postReturn,
  printBatchLabels,
  printIssueSlip,
  printWorkOrder,
  rejectIssue,
  requestIssueApproval,
  reverseIssue,
  reverseReceipt,
  reverseReturn,
  setPriority,
  workOrderAction,
  type JobCard,
  type ReceiptDoc,
  type WorkOrderRow,
} from '@/api/mfg';
import { errorCode } from '@/api/mfg';
import { getErrorMessage } from '@/api/client';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { ErrorState, LoadingState } from '@/components/PageState';
import { isRuntimeFlagEnabled } from '@/config/featureFlags';
import { t } from '@/i18n';
import {
  ErrorLine,
  Grid,
  MfgPage,
  NumField,
  Pill,
  SelectField,
  Stat,
  TabPanels,
  day,
  money,
  qty,
  todayIso,
  useMasters,
  useMfgRights,
  useRun,
} from './mfgShared';
import { SubcontractDialog } from './SubcontractDialog';

type Doc = { id: number; number: string; status: 'DRAFT' | 'POSTED' | 'REVERSED'; docDate: string | null };

export function WorkOrderDetailPage() {
  const { id } = useParams();
  const woId = Number(id);
  const qc = useQueryClient();
  const { canWork, canPlan, canCosts } = useMfgRights();
  const { run, busy, error, clear } = useRun();
  const [confirm, setConfirm] = useState<'release' | 'complete' | 'cancel' | 'close' | 'reopen' | null>(null);
  const q = useQuery({ queryKey: ['mfg-wo', woId], queryFn: () => getWorkOrder(woId) });
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['mfg-wo', woId] });
    void qc.invalidateQueries({ queryKey: ['mfg-docs', woId] });
    void qc.invalidateQueries({ queryKey: ['mfg-avail', woId] });
    void qc.invalidateQueries({ queryKey: ['work-orders'] });
  };
  if (q.isLoading) return <MfgPage title={t('mfg.wo.title')}><LoadingState /></MfgPage>;
  if (q.isError || !q.data) {
    return <MfgPage title={t('mfg.wo.title')}><ErrorState message={getErrorMessage(q.error)} error={q.error} onRetry={() => void q.refetch()} /></MfgPage>;
  }
  const wo = q.data;
  const separate = wo.issueMode === 'SEPARATE';
  const open = ['RELEASED', 'IN_PROGRESS'].includes(wo.status);
  const act = async (a: 'release' | 'complete' | 'cancel' | 'close' | 'reopen', reason?: string) => {
    const out = await run(() => workOrderAction(wo.id, a, reason ? { reason } : undefined));
    if (out) refresh();
  };

  return (
    <MfgPage
      title={`${wo.number} · ${wo.productName}`}
      subtitle={t('mfg.wo.subtitle', { qty: qty(wo.qty), due: day(wo.dueDate) })}
      actions={
        <Stack direction="row" spacing={1} flexWrap="wrap">
          <Button component={RouterLink} to="/manufacturing/work-orders">{t('mfg.common.back')}</Button>
          <Button onClick={() => void printWorkOrder(wo.id)}>{t('mfg.common.print')}</Button>
          {wo.status === 'DRAFT' ? <Button variant="contained" disabled={!canWork || busy} onClick={() => setConfirm('release')}>{t('erp.release')}</Button> : null}
          {open && !separate ? <Button variant="contained" disabled={!canWork || busy} onClick={() => setConfirm('complete')}>{t('common.complete')}</Button> : null}
          {open && separate ? <Button variant="outlined" disabled={!canWork || busy} onClick={() => setConfirm('complete')}>{t('mfg.wo.markDone')}</Button> : null}
          {wo.status === 'COMPLETED' && separate ? <Button variant="contained" disabled={!canWork || busy} onClick={() => setConfirm('close')}>{t('mfg.wo.close')}</Button> : null}
          {['COMPLETED', 'CLOSED'].includes(wo.status) && separate ? <Button disabled={!canPlan || busy} onClick={() => setConfirm('reopen')}>{t('mfg.wo.reopen')}</Button> : null}
          {['DRAFT', 'RELEASED', 'IN_PROGRESS'].includes(wo.status) ? <Button color="warning" disabled={!canPlan || busy} onClick={() => setConfirm('cancel')}>{t('common.cancel')}</Button> : null}
        </Stack>
      }
    >
      <ErrorLine error={error} onClose={clear} />
      <Stack direction="row" spacing={1} alignItems="center">
        <Pill value={wo.status} />
        <Typography variant="body2" color="text.secondary">
          {separate ? t('mfg.wo.modeSeparate') : t('mfg.wo.modeAuto')}
        </Typography>
      </Stack>

      <TabPanels
        tabs={[
          { key: 'ov', label: t('mfg.wo.tabOverview'), node: () => <Overview wo={wo} canCosts={canCosts} canPlan={canPlan} onChanged={refresh} /> },
          { key: 'mat', label: t('mfg.wo.tabMaterials'), node: () => <Materials wo={wo} canWork={canWork} canPlan={canPlan} onChanged={refresh} /> },
          { key: 'ret', label: t('mfg.wo.tabReturns'), hide: !separate, node: () => <Returns wo={wo} canWork={canWork} canPlan={canPlan} onChanged={refresh} /> },
          { key: 'out', label: t('mfg.wo.tabOutput'), hide: !separate, node: () => <Output wo={wo} canWork={canWork} canPlan={canPlan} onChanged={refresh} /> },
          { key: 'floor', label: t('mfg.wo.tabFloor'), hide: !isRuntimeFlagEnabled('MFG_SHOP_FLOOR'), node: () => <Floor wo={wo} canWork={canWork} /> },
        ]}
      />

      <ConfirmDialog
        open={confirm === 'release'}
        title={t('mfg.wo.releaseTitle')}
        body={separate ? t('mfg.wo.releaseBodySeparate') : t('mfg.wo.releaseBodyAuto')}
        onClose={() => setConfirm(null)}
        onConfirm={() => { setConfirm(null); void act('release'); }}
      />
      <ConfirmDialog
        open={confirm === 'complete'}
        title={separate ? t('mfg.wo.markDone') : t('mfg.wo.completeTitle')}
        body={separate ? t('mfg.wo.markDoneBody') : t('mfg.wo.completeBody')}
        onClose={() => setConfirm(null)}
        onConfirm={() => { setConfirm(null); void act('complete'); }}
      />
      <ConfirmDialog
        open={confirm === 'close'}
        title={t('mfg.wo.close')}
        body={t('mfg.wo.closeBody')}
        onClose={() => setConfirm(null)}
        onConfirm={() => { setConfirm(null); void act('close'); }}
      />
      <ConfirmDialog
        open={confirm === 'reopen'}
        title={t('mfg.wo.reopen')}
        body={t('mfg.wo.reopenBody')}
        requireReason={{ label: t('mfg.common.reason') }}
        onClose={() => setConfirm(null)}
        onConfirm={(r) => { setConfirm(null); void act('reopen', r); }}
      />
      <ConfirmDialog
        open={confirm === 'cancel'}
        title={t('mfg.wo.cancelTitle')}
        body={t('mfg.wo.cancelBody')}
        confirmColor="warning"
        onClose={() => setConfirm(null)}
        onConfirm={() => { setConfirm(null); void act('cancel'); }}
      />
    </MfgPage>
  );
}

function Overview({ wo, canCosts, canPlan, onChanged }: { wo: WorkOrderRow; canCosts: boolean; canPlan: boolean; onChanged: () => void }) {
  const { productName } = useMasters();
  const avail = useQuery({ queryKey: ['mfg-avail', wo.id], queryFn: () => getAvailability(wo.id), enabled: ['DRAFT', 'RELEASED', 'IN_PROGRESS'].includes(wo.status) });
  const { run, error, clear } = useRun();
  const [prio, setPrio] = useState(String(wo.priority));
  const [why, setWhy] = useState(wo.delayReason ?? '');
  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
        <Stat label={t('mfg.wo.planned')} value={qty(wo.qty)} />
        <Stat label={t('mfg.wo.made')} value={qty(wo.qtyCompleted)} tone="good" />
        <Stat label={t('mfg.wo.rejected')} value={qty(wo.qtyRejected)} tone={Number(wo.qtyRejected) > 0 ? 'bad' : undefined} />
        <Stat label={t('mfg.wo.rework')} value={qty(wo.qtyRework)} tone={Number(wo.qtyRework) > 0 ? 'warn' : undefined} />
      </Stack>
      {canCosts && wo.issueMode === 'SEPARATE' ? (
        <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
          <Stat label={t('mfg.wo.costIssued')} value={money(wo.costIssued)} />
          <Stat label={t('mfg.wo.costReturned')} value={money(wo.costReturned)} />
          <Stat label={t('mfg.wo.costAbsorbed')} value={money(wo.costAbsorbed)} />
          <Stat label={t('mfg.wo.costReceived')} value={money(wo.costReceived)} />
          <Stat label={t('mfg.wo.wip')} value={money(wo.wipValue)} tone="warn" />
          <Stat label={t('mfg.wo.variance')} value={money(wo.costVariance)} />
        </Stack>
      ) : null}
      <ErrorLine error={error} onClose={clear} />
      {['DRAFT', 'RELEASED', 'IN_PROGRESS'].includes(wo.status) ? (
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems={{ sm: 'center' }}>
          <SelectField
            label={t('mfg.wo.priority')}
            value={prio}
            disabled={!canPlan}
            onChange={setPrio}
            options={[1, 2, 3, 4, 5].map((n) => ({ value: String(n), label: `${n}${n === 1 ? ` · ${t('mfg.wo.mostUrgent')}` : ''}` }))}
          />
          <TextField size="small" label={t('mfg.wo.delayReason')} value={why} disabled={!canPlan} onChange={(e) => setWhy(e.target.value)} sx={{ minWidth: 260 }} />
          <Button
            disabled={!canPlan}
            onClick={async () => {
              const r = await run(() => setPriority(wo.id, { priority: Number(prio), delayReason: why }));
              if (r) onChanged();
            }}
          >
            {t('common.save')}
          </Button>
        </Stack>
      ) : null}
      {avail.data ? (
        <>
          <Typography variant="subtitle2">{t('mfg.wo.availability')}</Typography>
          <Grid
            query={avail}
            rows={avail.data.lines}
            rowKey={(l) => l.lineId}
            cols={[
              { key: 'p', label: t('mfg.recipe.material'), render: (l) => l.product.name },
              { key: 'n', label: t('mfg.wo.need'), align: 'right', render: (l) => qty(l.need) },
              { key: 'h', label: t('mfg.wo.held'), align: 'right', render: (l) => qty(l.held) },
              { key: 'f', label: t('mfg.wo.free'), align: 'right', render: (l) => qty(l.free) },
              { key: 's', label: t('mfg.wo.short'), align: 'right', render: (l) => (Number(l.short) > 0 ? <b style={{ color: 'crimson' }}>{qty(l.short)}</b> : '—') },
              { key: 'a', label: t('mfg.wo.alternates'), render: (l) => l.alternates.map((a) => `${a.product.name} (${qty(a.free)})`).join(', ') || '' },
            ]}
          />
        </>
      ) : null}
      <Typography variant="body2" color="text.secondary">
        {wo.salesOrder ? t('mfg.wo.forOrder', { id: wo.salesOrder }) : ''} {wo.principal ? t('mfg.wo.principalWork') : ''} {productName(wo.product)}
      </Typography>
    </Stack>
  );
}

function useDocs<T extends Doc>(wo: WorkOrderRow, kind: 'issues' | 'returns' | 'receipts', fn: (id: number) => Promise<T[]>) {
  return useQuery({ queryKey: ['mfg-docs', wo.id, kind], queryFn: () => fn(wo.id), enabled: wo.issueMode === 'SEPARATE' });
}

function DocActions({ doc, canWork, canPlan, onPost, onReverse, onDiscard, onPrint }: { doc: Doc; canWork: boolean; canPlan: boolean; onPost: () => void; onReverse: () => void; onDiscard: () => void; onPrint?: () => void }) {
  return (
    <Stack direction="row" spacing={1}>
      {onPrint ? <Button size="small" onClick={onPrint}>{t('mfg.common.print')}</Button> : null}
      {doc.status === 'DRAFT' ? <Button size="small" disabled={!canWork} onClick={onPost}>{t('mfg.common.post')}</Button> : null}
      {doc.status === 'DRAFT' ? <Button size="small" color="warning" disabled={!canWork} onClick={onDiscard}>{t('mfg.common.discard')}</Button> : null}
      {doc.status === 'POSTED' ? <Button size="small" color="warning" disabled={!canPlan} onClick={onReverse}>{t('mfg.common.reverse')}</Button> : null}
    </Stack>
  );
}

function Materials({ wo, canWork, canPlan, onChanged }: { wo: WorkOrderRow; canWork: boolean; canPlan: boolean; onChanged: () => void }) {
  const { productName } = useMasters();
  const { run, busy, error, code, clear } = useRun();
  const docs = useDocs(wo, 'issues', listIssues);
  const [amounts, setAmounts] = useState<Record<number, string>>({});
  const [extra, setExtra] = useState<Record<number, string>>({});
  const [reverseId, setReverseId] = useState<number | null>(null);
  // A draft that goes further over the plan than this user may post: the id to ask a manager about, and the note.
  const [askId, setAskId] = useState<number | null>(null);
  const [askNote, setAskNote] = useState('');
  const [rejectId, setRejectId] = useState<number | null>(null);
  const live = ['RELEASED', 'IN_PROGRESS'].includes(wo.status);
  const separate = wo.issueMode === 'SEPARATE';

  const issueNow = async () => {
    const lines = wo.componentLines
      .map((l) => ({ woLine: l.id, qty: amounts[l.id] || '', extraReason: extra[l.id] }))
      .filter((l) => Number(l.qty) > 0);
    if (!lines.length) return;
    const result = await run(async () => {
      const d = await createIssue({ workOrder: wo.id, docDate: todayIso(), lines });
      try {
        return await postIssue(d.id);
      } catch (err) {
        // Not an error for the person: the draft is kept and a manager can be asked.
        if (errorCode(err) === 'MFG_EXTRA_NEEDS_MANAGER') return { askFor: d.id };
        throw err;
      }
    });
    if (result && 'askFor' in result) {
      setAskId(result.askFor);
      onChanged();
    } else if (result) {
      setAmounts({});
      onChanged();
    }
  };

  return (
    <Stack spacing={2}>
      <ErrorLine error={error ? `${error}${code ? ` (${code})` : ''}` : null} onClose={clear} />
      <Grid
        rows={wo.componentLines}
        rowKey={(l) => l.id}
        cols={[
          { key: 'p', label: t('mfg.recipe.material'), render: (l) => productName(l.component) },
          { key: 'n', label: t('mfg.wo.need'), align: 'right', render: (l) => qty(l.qty) },
          { key: 'i', label: t('mfg.wo.issued'), align: 'right', render: (l) => qty(l.qtyIssued) },
          { key: 'r', label: t('mfg.wo.returned'), align: 'right', render: (l) => qty(l.qtyReturned) },
          {
            key: 'rem',
            label: t('mfg.wo.remaining'),
            align: 'right',
            render: (l) => qty(Math.max(Number(l.qty) - (Number(l.qtyIssued) - Number(l.qtyReturned)), 0)),
          },
          {
            key: 'now',
            label: t('mfg.wo.issueNow'),
            hide: !(separate && live),
            render: (l) => (
              <Stack direction="row" spacing={1}>
                <NumField label={t('mfg.common.quantity')} value={amounts[l.id] ?? ''} disabled={!canWork || l.issueMethod === 'BACKFLUSH'} onChange={(v) => setAmounts({ ...amounts, [l.id]: v })} width={100} />
                {Number(amounts[l.id] || 0) > Math.max(Number(l.qty) - (Number(l.qtyIssued) - Number(l.qtyReturned)), 0) ? (
                  <TextField size="small" label={t('mfg.wo.extraReason')} value={extra[l.id] ?? ''} onChange={(e) => setExtra({ ...extra, [l.id]: e.target.value })} />
                ) : null}
              </Stack>
            ),
          },
        ]}
      />
      {separate && live ? (
        <Stack direction="row" spacing={2}>
          <Button variant="contained" disabled={!canWork || busy} onClick={issueNow}>{t('mfg.wo.issueButton')}</Button>
          <Button disabled={!canWork || busy} onClick={() => setAmounts(Object.fromEntries(wo.componentLines.filter((l) => l.issueMethod !== 'BACKFLUSH').map((l) => [l.id, String(Math.max(Number(l.qty) - (Number(l.qtyIssued) - Number(l.qtyReturned)), 0))])))}>{t('mfg.wo.fillRemaining')}</Button>
        </Stack>
      ) : null}
      {askId !== null ? (
        <Alert severity="warning" action={<Button color="inherit" size="small" onClick={() => setAskId(null)}>{t('common.cancel')}</Button>}>
          <Stack spacing={1}>
            <span>{t('mfg.wo.needsManager')}</span>
            <Stack direction="row" spacing={1} alignItems="center">
              <TextField size="small" label={t('mfg.wo.askNote')} value={askNote} onChange={(e) => setAskNote(e.target.value)} sx={{ minWidth: 280 }} />
              <Button
                size="small"
                variant="contained"
                disabled={busy}
                onClick={async () => {
                  if (await run(() => requestIssueApproval(askId, askNote))) {
                    setAskId(null);
                    setAskNote('');
                    setAmounts({});
                    onChanged();
                  }
                }}
              >
                {t('mfg.wo.askManager')}
              </Button>
            </Stack>
          </Stack>
        </Alert>
      ) : null}
      {!separate ? <Alert severity="info">{t('mfg.wo.autoNoDocs')}</Alert> : null}
      {separate ? (
        <>
          <Typography variant="subtitle2">{t('mfg.wo.issueDocs')}</Typography>
          <Grid
            query={docs}
            rows={docs.data ?? []}
            rowKey={(d) => d.id}
            cols={[
              { key: 'n', label: t('mfg.common.number'), render: (d) => d.number },
              { key: 'd', label: t('mfg.common.date'), render: (d) => day(d.docDate) },
              {
                key: 's',
                label: t('mfg.common.status'),
                render: (d) => (
                  <Stack direction="row" spacing={0.5} alignItems="center">
                    <Pill value={d.status} />
                    {d.status === 'DRAFT' && d.approval === 'REQUESTED' ? <Pill value="APPROVAL_REQUESTED" tone="warning" /> : null}
                    {d.status === 'DRAFT' && d.approval === 'REJECTED' ? <Pill value="APPROVAL_REJECTED" tone="error" /> : null}
                  </Stack>
                ),
              },
              { key: 'l', label: t('mfg.wo.lines'), render: (d) => d.lines.map((l) => `${l.componentName} ${qty(l.qty)}`).join(', ') },
              {
                key: 'a',
                label: '',
                render: (d) => (
                  <Stack direction="row" spacing={1} alignItems="center">
                    {d.status === 'DRAFT' && d.approval === 'REQUESTED' && canPlan ? (
                      <>
                        <Button size="small" variant="contained" disabled={busy} onClick={() => void run(() => approveIssue(d.id)).then(onChanged)}>{t('mfg.wo.approve')}</Button>
                        <Button size="small" color="warning" disabled={busy} onClick={() => setRejectId(d.id)}>{t('mfg.wo.reject')}</Button>
                      </>
                    ) : null}
                    {d.status === 'DRAFT' && d.approval !== 'REQUESTED' && !canPlan && canWork ? (
                      <Button size="small" onClick={() => setAskId(d.id)}>{t('mfg.wo.askManager')}</Button>
                    ) : null}
                    <DocActions doc={d} canWork={canWork} canPlan={canPlan} onPost={() => void run(() => postIssue(d.id)).then(onChanged)} onDiscard={() => void run(() => discardIssue(d.id)).then(onChanged)} onReverse={() => setReverseId(d.id)} onPrint={() => void printIssueSlip(d.id)} />
                  </Stack>
                ),
              },
            ]}
          />
        </>
      ) : null}
      <ConfirmDialog
        open={rejectId !== null}
        title={t('mfg.wo.rejectTitle')}
        body={t('mfg.wo.rejectBody')}
        requireReason={{ label: t('mfg.common.reason') }}
        confirmColor="warning"
        onClose={() => setRejectId(null)}
        onConfirm={(r) => { const i = rejectId!; setRejectId(null); void run(() => rejectIssue(i, r)).then(onChanged); }}
      />
      <ConfirmDialog
        open={reverseId !== null}
        title={t('mfg.common.reverseTitle')}
        body={t('mfg.wo.reverseIssueBody')}
        requireReason={{ label: t('mfg.common.reason') }}
        confirmColor="warning"
        onClose={() => setReverseId(null)}
        onConfirm={(r) => { const i = reverseId!; setReverseId(null); void run(() => reverseIssue(i, r)).then(onChanged); }}
      />
    </Stack>
  );
}

function Returns({ wo, canWork, canPlan, onChanged }: { wo: WorkOrderRow; canWork: boolean; canPlan: boolean; onChanged: () => void }) {
  const { productName } = useMasters();
  const { run, busy, error, code, clear } = useRun();
  const docs = useDocs(wo, 'returns', listReturns);
  const [amounts, setAmounts] = useState<Record<number, string>>({});
  const [reverseId, setReverseId] = useState<number | null>(null);
  const live = ['RELEASED', 'IN_PROGRESS'].includes(wo.status);
  const out = (l: WorkOrderRow['componentLines'][number]) => Math.max(Number(l.qtyIssued) - Number(l.qtyReturned), 0);
  return (
    <Stack spacing={2}>
      <ErrorLine error={error ? `${error}${code ? ` (${code})` : ''}` : null} onClose={clear} />
      <Typography variant="body2" color="text.secondary">{t('mfg.wo.returnHelp')}</Typography>
      <Grid
        rows={wo.componentLines.filter((l) => out(l) > 0)}
        rowKey={(l) => l.id}
        empty={t('mfg.wo.nothingOut')}
        cols={[
          { key: 'p', label: t('mfg.recipe.material'), render: (l) => productName(l.component) },
          { key: 'o', label: t('mfg.wo.outOnOrder'), align: 'right', render: (l) => qty(out(l)) },
          { key: 'r', label: t('mfg.wo.returnQty'), hide: !live, render: (l) => <NumField label={t('mfg.common.quantity')} value={amounts[l.id] ?? ''} disabled={!canWork} onChange={(v) => setAmounts({ ...amounts, [l.id]: v })} width={100} /> },
        ]}
      />
      {live ? (
        <Button
          variant="contained"
          sx={{ alignSelf: 'flex-start' }}
          disabled={!canWork || busy || !Object.values(amounts).some((v) => Number(v) > 0)}
          onClick={async () => {
            const lines = Object.entries(amounts).filter(([, v]) => Number(v) > 0).map(([k, v]) => ({ woLine: Number(k), qty: v }));
            const r = await run(async () => postReturn((await createReturn({ workOrder: wo.id, docDate: todayIso(), lines })).id));
            if (r) {
              setAmounts({});
              onChanged();
            }
          }}
        >
          {t('mfg.wo.returnButton')}
        </Button>
      ) : null}
      <Grid
        query={docs}
        rows={docs.data ?? []}
        rowKey={(d) => d.id}
        cols={[
          { key: 'n', label: t('mfg.common.number'), render: (d) => d.number },
          { key: 'd', label: t('mfg.common.date'), render: (d) => day(d.docDate) },
          { key: 's', label: t('mfg.common.status'), render: (d) => <Pill value={d.status} /> },
          { key: 'l', label: t('mfg.wo.lines'), render: (d) => d.lines.map((l) => `${l.componentName} ${qty(l.qty)}`).join(', ') },
          { key: 'a', label: '', render: (d) => <DocActions doc={d} canWork={canWork} canPlan={canPlan} onPost={() => void run(() => postReturn(d.id)).then(onChanged)} onDiscard={() => void run(() => discardReturn(d.id)).then(onChanged)} onReverse={() => setReverseId(d.id)} /> },
        ]}
      />
      <ConfirmDialog
        open={reverseId !== null}
        title={t('mfg.common.reverseTitle')}
        body={t('mfg.wo.reverseReturnBody')}
        requireReason={{ label: t('mfg.common.reason') }}
        confirmColor="warning"
        onClose={() => setReverseId(null)}
        onConfirm={(r) => { const i = reverseId!; setReverseId(null); void run(() => reverseReturn(i, r)).then(onChanged); }}
      />
    </Stack>
  );
}

function Output({ wo, canWork, canPlan, onChanged }: { wo: WorkOrderRow; canWork: boolean; canPlan: boolean; onChanged: () => void }) {
  const { run, busy, error, code, clear } = useRun();
  const docs = useDocs<ReceiptDoc>(wo, 'receipts', listReceipts);
  const [good, setGood] = useState('');
  const [rejected, setRejected] = useState('');
  const [rework, setRework] = useState('');
  const [batchNo, setBatchNo] = useState('');
  const [expDate, setExpDate] = useState('');
  const [isFinal, setIsFinal] = useState(false);
  const [reverseId, setReverseId] = useState<number | null>(null);
  const [overrideWip, setOverrideWip] = useState(false);
  const live = ['RELEASED', 'IN_PROGRESS'].includes(wo.status);
  const left = Math.max(Number(wo.qty) - Number(wo.qtyCompleted), 0);
  const record = async () => {
    const r = await run(async () => {
      const doc = await createReceipt({
        workOrder: wo.id,
        docDate: todayIso(),
        isFinal,
        batchNo: batchNo || undefined,
        expDate: expDate || undefined,
        lines: [{ kind: 'MAIN', qtyGood: good || '0', qtyRejected: rejected || '0', qtyRework: rework || '0' }],
      });
      return postReceipt(doc.id, overrideWip);
    });
    if (r) {
      setGood('');
      setRejected('');
      setRework('');
      setBatchNo('');
      setIsFinal(false);
      onChanged();
    }
  };
  return (
    <Stack spacing={2}>
      <ErrorLine error={error ? `${error}${code ? ` (${code})` : ''}` : null} onClose={clear} />
      {code === 'MFG_RECEIPT_EXCEEDS_WIP' ? (
        <FormControlLabel control={<Switch checked={overrideWip} onChange={(e) => setOverrideWip(e.target.checked)} />} label={t('mfg.wo.overrideWip')} />
      ) : null}
      {live ? (
        <Stack spacing={1.5}>
          <Typography variant="subtitle2">{t('mfg.wo.recordOutput', { left: qty(left) })}</Typography>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} alignItems={{ md: 'center' }}>
            <NumField label={t('mfg.wo.good')} value={good} onChange={setGood} />
            <NumField label={t('mfg.wo.rejected')} value={rejected} onChange={setRejected} />
            <NumField label={t('mfg.wo.rework')} value={rework} onChange={setRework} />
            <TextField size="small" label={t('mfg.common.batchNo')} value={batchNo} onChange={(e) => setBatchNo(e.target.value)} />
            <TextField size="small" type="date" label={t('mfg.common.expiry')} value={expDate} onChange={(e) => setExpDate(e.target.value)} InputLabelProps={{ shrink: true }} />
            <FormControlLabel control={<Switch checked={isFinal} onChange={(e) => setIsFinal(e.target.checked)} />} label={t('mfg.wo.finalReceipt')} />
          </Stack>
          <Typography variant="caption" color="text.secondary">{t('mfg.wo.finalHelp')}</Typography>
          <Button variant="contained" sx={{ alignSelf: 'flex-start' }} disabled={!canWork || busy || !(Number(good) > 0 || Number(rejected) > 0 || Number(rework) > 0)} onClick={record}>
            {t('mfg.wo.recordButton')}
          </Button>
        </Stack>
      ) : null}
      <Grid
        query={docs}
        rows={docs.data ?? []}
        rowKey={(d) => d.id}
        cols={[
          { key: 'n', label: t('mfg.common.number'), render: (d) => d.number },
          { key: 'd', label: t('mfg.common.date'), render: (d) => day(d.docDate) },
          { key: 's', label: t('mfg.common.status'), render: (d) => <Pill value={d.status} /> },
          { key: 'f', label: t('mfg.wo.finalReceipt'), render: (d) => (d.isFinal ? t('common.yes') : '') },
          { key: 'l', label: t('mfg.wo.lines'), render: (d) => d.lines.map((l) => `${l.productName} ${qty(l.qtyGood)}${Number(l.qtyRejected) ? ` / ${t('mfg.wo.rejected')} ${qty(l.qtyRejected)}` : ''}`).join(', ') },
          {
            key: 'a',
            label: '',
            render: (d) => (
              <Stack direction="row" spacing={1} alignItems="center">
                {d.status === 'POSTED' ? <Button size="small" onClick={() => void printBatchLabels(d.id)}>{t('mfg.wo.printLabel')}</Button> : null}
                <DocActions doc={d} canWork={canWork} canPlan={canPlan} onPost={() => void run(() => postReceipt(d.id)).then(onChanged)} onDiscard={() => void run(() => discardReceipt(d.id)).then(onChanged)} onReverse={() => setReverseId(d.id)} />
              </Stack>
            ),
          },
        ]}
      />
      <ConfirmDialog
        open={reverseId !== null}
        title={t('mfg.common.reverseTitle')}
        body={t('mfg.wo.reverseReceiptBody')}
        requireReason={{ label: t('mfg.common.reason') }}
        confirmColor="warning"
        onClose={() => setReverseId(null)}
        onConfirm={(r) => { const i = reverseId!; setReverseId(null); void run(() => reverseReceipt(i, r)).then(onChanged); }}
      />
    </Stack>
  );
}

function Floor({ wo, canWork }: { wo: WorkOrderRow; canWork: boolean }) {
  const qc = useQueryClient();
  const { run, error, clear } = useRun();
  const [sendCard, setSendCard] = useState<JobCard | null>(null);
  const cards = useQuery({ queryKey: ['mfg-cards', wo.id], queryFn: () => listJobCards({ workOrder: wo.id }) });
  const reload = () => void qc.invalidateQueries({ queryKey: ['mfg-cards', wo.id] });
  return (
    <Stack spacing={2}>
      <ErrorLine error={error} onClose={clear} />
      {(cards.data ?? []).length === 0 ? (
        <Button variant="outlined" sx={{ alignSelf: 'flex-start' }} disabled={!canWork} onClick={async () => { if (await run(() => createJobCards(wo.id))) reload(); }}>
          {t('mfg.wo.makeCards')}
        </Button>
      ) : null}
      <Grid
        query={cards}
        rows={cards.data ?? []}
        rowKey={(c) => c.id}
        cols={[
          { key: 'sq', label: t('mfg.recipe.step'), render: (c) => c.sequence },
          { key: 'n', label: t('mfg.common.name'), render: (c) => c.name },
          { key: 'w', label: t('mfg.recipe.workCentre'), render: (c) => c.workCentreCode },
          { key: 's', label: t('mfg.common.status'), render: (c) => <Pill value={c.status} /> },
          { key: 'g', label: t('mfg.wo.good'), align: 'right', render: (c) => qty(c.qtyGood) },
          { key: 'm', label: t('mfg.floor.minutes'), align: 'right', render: (c) => qty(c.minutesWorked) },
          {
            key: 'a',
            label: '',
            render: (c) => (
              <Stack direction="row" spacing={1}>
                {c.isSubcontract && !c.jobworkOrderId && ['PLANNED', 'PAUSED'].includes(c.status) && isRuntimeFlagEnabled('MFG_JOB_WORK') ? (
                  <Button size="small" variant="contained" disabled={!canWork} onClick={() => setSendCard(c)}>{t('mfg.sub.sendButton')}</Button>
                ) : null}
                {c.isSubcontract && c.jobworkOrderId ? <Typography variant="body2" color="text.secondary">{t('mfg.sub.atJobWorker')}</Typography> : null}
                {!c.isSubcontract && ['PLANNED', 'PAUSED'].includes(c.status) ? <Button size="small" disabled={!canWork} onClick={async () => { if (await run(() => jobCardAction(c.id, 'start'))) reload(); }}>{t('mfg.floor.start')}</Button> : null}
                {!c.isSubcontract && c.status === 'IN_PROGRESS' ? <Button size="small" disabled={!canWork} onClick={async () => { if (await run(() => jobCardAction(c.id, 'pause'))) reload(); }}>{t('mfg.floor.pause')}</Button> : null}
                {!c.isSubcontract && ['IN_PROGRESS', 'PAUSED'].includes(c.status) ? <Button size="small" disabled={!canWork} onClick={async () => { if (await run(() => jobCardAction(c.id, 'finish'))) reload(); }}>{t('mfg.floor.finish')}</Button> : null}
              </Stack>
            ),
          },
        ]}
      />
      <SubcontractDialog card={sendCard} onClose={() => setSendCard(null)} onDone={reload} />
    </Stack>
  );
}
