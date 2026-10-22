import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import FormControlLabel from '@mui/material/FormControlLabel';
import IconButton from '@mui/material/IconButton';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import DeleteIcon from '@mui/icons-material/Delete';
import { useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';
import {
  closeJobWorkOrder,
  createChallan,
  createJobWorkOrder,
  createJwReceipt,
  downloadItc04,
  getItc04,
  getItc04Due,
  getJwAgeing,
  getJwBalance,
  issueChallan,
  listChallans,
  listItc04Filings,
  listJobWorkOrders,
  listJwReceipts,
  markItc04Filed,
  postJwReceipt,
  prepareItc04,
  receiveCustomerMaterial,
  recordCustomerLoss,
  returnCustomerMaterial,
  reverseChallan,
  reverseJwReceipt,
  saveBlob,
  type JobWorkOrder,
  type JwReceiptKind,
} from '@/api/mfg';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { t } from '@/i18n';
import { CustomerPick, ErrorLine, Grid, MfgPage, NumField, Pill, ProductPick, SelectField, Stat, SupplierPick, TabPanels, day, money, qty, todayIso, fyStartYear, useMfgRights, useRun } from './mfgShared';

/** Every job-work document changes what the others show (open quantities, who holds what, ageing, ITC-04), so they all refresh together. */
const refreshJobWork = (qc: QueryClient) =>
  void qc.invalidateQueries({ predicate: (q) => /^mfg-(jw|itc)/.test(String(q.queryKey[0])) });

export function JobWorkPage() {
  return (
    <MfgPage title={t('mfg.jw.title')} subtitle={t('mfg.jw.subtitle')} flag="MFG_JOB_WORK">
      <TabPanels
        tabs={[
          { key: 'orders', label: t('mfg.jw.tabOrders'), node: () => <Orders /> },
          { key: 'ch', label: t('mfg.jw.tabChallans'), node: () => <Challans /> },
          { key: 'rc', label: t('mfg.jw.tabReceipts'), node: () => <Receipts /> },
          { key: 'bal', label: t('mfg.jw.tabBalance'), node: () => <Balance /> },
          { key: 'age', label: t('mfg.jw.tabAgeing'), node: () => <Ageing /> },
          { key: 'itc', label: t('mfg.jw.tabItc04'), node: () => <Itc04 /> },
        ]}
      />
    </MfgPage>
  );
}

function Orders() {
  const qc = useQueryClient();
  const { canWork } = useMfgRights();
  const { run, busy, error, clear } = useRun();
  const q = useQuery({ queryKey: ['mfg-jw-orders'], queryFn: () => listJobWorkOrders() });
  const [dir, setDir] = useState<'OUT' | 'IN'>('OUT');
  const [supplier, setSupplier] = useState<number | ''>('');
  const [customer, setCustomer] = useState<number | ''>('');
  const [process, setProcess] = useState('');
  const [direct, setDirect] = useState(false);
  const [material, setMaterial] = useState<JobWorkOrder | null>(null);
  const reload = () => refreshJobWork(qc);
  return (
    <Stack spacing={2}>
      <ErrorLine error={error} onClose={clear} />
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems={{ md: 'center' }}>
        <SelectField label={t('mfg.jw.direction')} value={dir} onChange={setDir} options={[{ value: 'OUT', label: t('mfg.jw.dirOut') }, { value: 'IN', label: t('mfg.jw.dirIn') }]} />
        {dir === 'OUT' ? <SupplierPick label={t('mfg.jw.worker')} value={supplier} onChange={setSupplier} /> : <CustomerPick label={t('mfg.jw.principal')} value={customer} onChange={setCustomer} />}
        <TextField size="small" label={t('mfg.jw.process')} value={process} onChange={(e) => setProcess(e.target.value)} />
        {dir === 'OUT' ? <FormControlLabel control={<Switch checked={direct} onChange={(e) => setDirect(e.target.checked)} />} label={t('mfg.jw.direct')} /> : null}
        <Button
          variant="contained"
          disabled={!canWork || busy || (dir === 'OUT' ? supplier === '' : customer === '')}
          onClick={async () => {
            const r = await run(() =>
              createJobWorkOrder({
                direction: dir,
                supplier: dir === 'OUT' && supplier !== '' ? supplier : undefined,
                customer: dir === 'IN' && customer !== '' ? customer : undefined,
                process,
                directSupplyDeclared: dir === 'OUT' ? direct : undefined,
              }),
            );
            if (r) {
              setProcess('');
              reload();
            }
          }}
        >
          {t('mfg.jw.newOrder')}
        </Button>
      </Stack>
      <Grid
        query={q}
        rows={q.data ?? []}
        rowKey={(r) => r.id}
        cols={[
          { key: 'n', label: t('mfg.common.number'), render: (r) => r.number },
          { key: 'd', label: t('mfg.jw.direction'), render: (r) => (r.direction === 'OUT' ? t('mfg.jw.dirOut') : t('mfg.jw.dirIn')) },
          { key: 'p', label: t('mfg.jw.party'), render: (r) => r.supplierName || r.customerName },
          { key: 'pr', label: t('mfg.jw.process'), render: (r) => r.process },
          { key: 's', label: t('mfg.common.status'), render: (r) => <Pill value={r.status} /> },
          {
            key: 'a',
            label: '',
            render: (r) => (
              <Stack direction="row" spacing={1}>
                {r.direction === 'IN' && r.status === 'OPEN' ? <Button size="small" disabled={!canWork} onClick={() => setMaterial(r)}>{t('mfg.jw.material')}</Button> : null}
                {r.status === 'OPEN' ? <Button size="small" color="warning" disabled={!canWork} onClick={async () => { if (await run(() => closeJobWorkOrder(r.id))) reload(); }}>{t('mfg.jw.closeOrder')}</Button> : null}
              </Stack>
            ),
          },
        ]}
      />
      {material ? <CustomerMaterial order={material} onClose={() => setMaterial(null)} /> : null}
    </Stack>
  );
}

function CustomerMaterial({ order, onClose }: { order: JobWorkOrder; onClose: () => void }) {
  const { run, busy, error, clear } = useRun();
  const [mode, setMode] = useState<'receive' | 'return' | 'loss'>('receive');
  const [product, setProduct] = useState<number | ''>('');
  const [quantity, setQuantity] = useState('');
  const [done, setDone] = useState('');
  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{t('mfg.jw.customerMaterial', { n: order.number })}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <ErrorLine error={error} onClose={clear} />
          {done ? <Alert severity="success">{done}</Alert> : null}
          <Typography variant="body2" color="text.secondary">{t('mfg.jw.materialHelp')}</Typography>
          <SelectField label={t('mfg.jw.what')} size="medium" value={mode} onChange={setMode} options={[{ value: 'receive', label: t('mfg.jw.receiveMaterial') }, { value: 'return', label: t('mfg.jw.returnMaterial') }, { value: 'loss', label: t('mfg.jw.recordLoss') }]} />
          <ProductPick value={product} onChange={setProduct} />
          <NumField label={t('mfg.common.quantity')} value={quantity} onChange={setQuantity} />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.close')}</Button>
        <Button
          variant="contained"
          disabled={busy || product === '' || !quantity}
          onClick={async () => {
            const lines = [{ product: product as number, qty: quantity }];
            const r = await run(async () => {
              if (mode === 'receive') return receiveCustomerMaterial(order.id, { challanDate: todayIso(), lines });
              if (mode === 'return') return returnCustomerMaterial(order.id, { challanDate: todayIso(), lines });
              return recordCustomerLoss(order.id, { product: product as number, qty: quantity });
            });
            if (r) {
              setDone(t('mfg.jw.recorded'));
              setQuantity('');
            }
          }}
        >
          {t('mfg.common.post')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function Challans() {
  const qc = useQueryClient();
  const { canWork, canPlan } = useMfgRights();
  const { run, busy, error, clear } = useRun();
  const orders = useQuery({ queryKey: ['mfg-jw-orders'], queryFn: () => listJobWorkOrders({ direction: 'OUT', status: 'OPEN' }) });
  const q = useQuery({ queryKey: ['mfg-jw-challans'], queryFn: () => listChallans() });
  const [order, setOrder] = useState<number | ''>('');
  const [vehicle, setVehicle] = useState('');
  const [lines, setLines] = useState<Array<{ product: number | ''; qty: string; goodsKind: string }>>([{ product: '', qty: '', goodsKind: 'INPUT' }]);
  const [reverseId, setReverseId] = useState<number | null>(null);
  const reload = () => refreshJobWork(qc);
  const valid = order !== '' && lines.every((l) => l.product !== '' && Number(l.qty) > 0);
  return (
    <Stack spacing={2}>
      <ErrorLine error={error} onClose={clear} />
      <Typography variant="subtitle2">{t('mfg.jw.sendOut')}</Typography>
      <Stack spacing={1}>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
          <SelectField label={t('mfg.jw.order')} value={String(order)} onChange={(v) => setOrder(v === '' ? '' : Number(v))} options={[{ value: '', label: '—' }, ...(orders.data ?? []).map((o) => ({ value: String(o.id), label: `${o.number} · ${o.supplierName}` }))]} />
          <TextField size="small" label={t('mfg.jw.vehicle')} value={vehicle} onChange={(e) => setVehicle(e.target.value)} />
        </Stack>
        {lines.map((l, i) => (
          <Stack key={i} direction="row" spacing={1} alignItems="center">
            <ProductPick value={l.product} onChange={(v) => setLines(lines.map((x, k) => (k === i ? { ...x, product: v } : x)))} />
            <NumField label={t('mfg.common.quantity')} value={l.qty} onChange={(v) => setLines(lines.map((x, k) => (k === i ? { ...x, qty: v } : x)))} />
            <SelectField label={t('mfg.jw.goodsKind')} value={l.goodsKind} onChange={(v) => setLines(lines.map((x, k) => (k === i ? { ...x, goodsKind: v } : x)))} options={[{ value: 'INPUT', label: t('mfg.jw.kindInput') }, { value: 'CAPITAL', label: t('mfg.jw.kindCapital') }]} />
            {lines.length > 1 ? <IconButton aria-label={t('common.delete')} onClick={() => setLines(lines.filter((_, k) => k !== i))}><DeleteIcon fontSize="small" /></IconButton> : null}
          </Stack>
        ))}
        <Stack direction="row" spacing={2}>
          <Button onClick={() => setLines([...lines, { product: '', qty: '', goodsKind: 'INPUT' }])}>{t('mfg.jw.addLine')}</Button>
          <Button
            variant="contained"
            disabled={!canWork || busy || !valid}
            onClick={async () => {
              const r = await run(async () => {
                const ch = await createChallan({
                  order: order as number,
                  challanDate: todayIso(),
                  vehicleNo: vehicle || undefined,
                  lines: lines.map((l) => ({ product: l.product as number, qty: l.qty, goodsKind: l.goodsKind })),
                });
                return issueChallan(ch.id);
              });
              if (r) {
                setLines([{ product: '', qty: '', goodsKind: 'INPUT' }]);
                reload();
              }
            }}
          >
            {t('mfg.jw.issueChallan')}
          </Button>
        </Stack>
      </Stack>
      <Grid
        query={q}
        rows={q.data ?? []}
        rowKey={(r) => r.id}
        cols={[
          { key: 'n', label: t('mfg.common.number'), render: (r) => r.number },
          { key: 'o', label: t('mfg.jw.order'), render: (r) => r.orderNumber },
          { key: 'd', label: t('mfg.common.date'), render: (r) => day(r.challanDate) },
          { key: 's', label: t('mfg.common.status'), render: (r) => <Pill value={r.status} /> },
          { key: 'l', label: t('mfg.wo.lines'), render: (r) => r.lines.map((l) => `${l.productName} ${qty(l.qty)} (${t('mfg.jw.open')} ${qty(l.qtyOpen)})`).join(', ') },
          { key: 'a', label: '', render: (r) => (r.status === 'ISSUED' ? <Button size="small" color="warning" disabled={!canPlan} onClick={() => setReverseId(r.id)}>{t('mfg.common.reverse')}</Button> : null) },
        ]}
      />
      <ConfirmDialog
        open={reverseId !== null}
        title={t('mfg.common.reverseTitle')}
        body={t('mfg.jw.reverseChallanBody')}
        requireReason={{ label: t('mfg.common.reason') }}
        confirmColor="warning"
        onClose={() => setReverseId(null)}
        onConfirm={(reason) => { const id = reverseId!; setReverseId(null); void run(() => reverseChallan(id, reason)).then(reload); }}
      />
    </Stack>
  );
}

type RLine = { kind: JwReceiptKind; product: number | ''; qty: string; inputProduct: number | ''; inputQty: string; chargeAmount: string; invoiceRef: string };

function Receipts() {
  const qc = useQueryClient();
  const { canWork, canPlan } = useMfgRights();
  const { run, busy, error, clear } = useRun();
  const orders = useQuery({ queryKey: ['mfg-jw-orders'], queryFn: () => listJobWorkOrders({ direction: 'OUT', status: 'OPEN' }) });
  const q = useQuery({ queryKey: ['mfg-jw-receipts'], queryFn: () => listJwReceipts() });
  const [order, setOrder] = useState<number | ''>('');
  const blank = (): RLine => ({ kind: 'PROCESSED', product: '', qty: '', inputProduct: '', inputQty: '', chargeAmount: '', invoiceRef: '' });
  const [lines, setLines] = useState<RLine[]>([blank()]);
  const [reverseId, setReverseId] = useState<number | null>(null);
  const reload = () => refreshJobWork(qc);
  const kinds: JwReceiptKind[] = ['PROCESSED', 'UNPROCESSED_RETURN', 'SCRAP_RETURNED', 'SCRAP_RETAINED', 'SUPPLIED_FROM_JW'];
  const valid = order !== '' && lines.every((l) => l.product !== '' && Number(l.qty) > 0);
  return (
    <Stack spacing={2}>
      <ErrorLine error={error} onClose={clear} />
      <Typography variant="subtitle2">{t('mfg.jw.receiveBack')}</Typography>
      <SelectField label={t('mfg.jw.order')} value={String(order)} onChange={(v) => setOrder(v === '' ? '' : Number(v))} options={[{ value: '', label: '—' }, ...(orders.data ?? []).map((o) => ({ value: String(o.id), label: `${o.number} · ${o.supplierName}` }))]} />
      {lines.map((l, i) => {
        const set = (p: Partial<RLine>) => setLines(lines.map((x, k) => (k === i ? { ...x, ...p } : x)));
        return (
          <Stack key={i} direction={{ xs: 'column', md: 'row' }} spacing={1} alignItems={{ md: 'center' }}>
            <SelectField label={t('mfg.jw.receiptKind')} value={l.kind} onChange={(v) => set({ kind: v })} options={kinds.map((k) => ({ value: k, label: t(`mfg.jw.kind_${k}`) }))} />
            <ProductPick value={l.product} onChange={(v) => set({ product: v })} />
            <NumField label={t('mfg.common.quantity')} value={l.qty} onChange={(v) => set({ qty: v })} />
            {l.kind === 'PROCESSED' ? (
              <>
                <ProductPick label={t('mfg.jw.inputUsed')} value={l.inputProduct} onChange={(v) => set({ inputProduct: v })} />
                <NumField label={t('mfg.jw.inputQty')} value={l.inputQty} onChange={(v) => set({ inputQty: v })} />
                <NumField label={t('mfg.jw.charge')} value={l.chargeAmount} onChange={(v) => set({ chargeAmount: v })} />
              </>
            ) : null}
            {l.kind === 'SUPPLIED_FROM_JW' ? <TextField size="small" label={t('mfg.jw.invoiceRef')} value={l.invoiceRef} onChange={(e) => set({ invoiceRef: e.target.value })} /> : null}
            {lines.length > 1 ? <IconButton aria-label={t('common.delete')} onClick={() => setLines(lines.filter((_, k) => k !== i))}><DeleteIcon fontSize="small" /></IconButton> : null}
          </Stack>
        );
      })}
      <Stack direction="row" spacing={2}>
        <Button onClick={() => setLines([...lines, blank()])}>{t('mfg.jw.addLine')}</Button>
        <Button
          variant="contained"
          disabled={!canWork || busy || !valid}
          onClick={async () => {
            const r = await run(async () => {
              const doc = await createJwReceipt({
                order: order as number,
                receiptDate: todayIso(),
                lines: lines.map((l) => ({
                  kind: l.kind,
                  product: l.product as number,
                  qty: l.qty,
                  inputProduct: l.inputProduct === '' ? undefined : l.inputProduct,
                  inputQty: l.inputQty || undefined,
                  chargeAmount: l.chargeAmount || undefined,
                  invoiceRef: l.invoiceRef || undefined,
                })),
              });
              return postJwReceipt(doc.id);
            });
            if (r) {
              setLines([blank()]);
              reload();
            }
          }}
        >
          {t('mfg.jw.postReceipt')}
        </Button>
      </Stack>
      <Grid
        query={q}
        rows={q.data ?? []}
        rowKey={(r) => r.id}
        cols={[
          { key: 'n', label: t('mfg.common.number'), render: (r) => r.number },
          { key: 'o', label: t('mfg.jw.order'), render: (r) => r.orderNumber },
          { key: 'd', label: t('mfg.common.date'), render: (r) => day(r.receiptDate) },
          { key: 's', label: t('mfg.common.status'), render: (r) => <Pill value={r.status} /> },
          { key: 'l', label: t('mfg.wo.lines'), render: (r) => r.lines.map((l) => `${t(`mfg.jw.kind_${l.kind}`)}: ${l.productName} ${qty(l.qty)}`).join('; ') },
          { key: 'a', label: '', render: (r) => (r.status === 'POSTED' ? <Button size="small" color="warning" disabled={!canPlan} onClick={() => setReverseId(r.id)}>{t('mfg.common.reverse')}</Button> : null) },
        ]}
      />
      <ConfirmDialog
        open={reverseId !== null}
        title={t('mfg.common.reverseTitle')}
        body={t('mfg.jw.reverseReceiptBody')}
        requireReason={{ label: t('mfg.common.reason') }}
        confirmColor="warning"
        onClose={() => setReverseId(null)}
        onConfirm={(reason) => { const id = reverseId!; setReverseId(null); void run(() => reverseJwReceipt(id, reason)).then(reload); }}
      />
    </Stack>
  );
}

function Balance() {
  const q = useQuery({ queryKey: ['mfg-jw-balance'], queryFn: getJwBalance });
  return (
    <Stack spacing={2}>
      <Typography variant="subtitle2">{t('mfg.jw.atWorkers')}</Typography>
      <Grid
        query={q}
        rows={q.data?.atJobWorkers ?? []}
        rowKey={(r) => `${r.supplier}-${r.product}`}
        cols={[
          { key: 's', label: t('mfg.jw.worker'), render: (r) => r.supplierName },
          { key: 'p', label: t('mfg.common.item'), render: (r) => r.productName },
          { key: 'q', label: t('mfg.common.quantity'), align: 'right', render: (r) => qty(r.qty) },
          { key: 'v', label: t('mfg.common.value'), align: 'right', render: (r) => money(r.value) },
        ]}
      />
      <Typography variant="subtitle2">{t('mfg.jw.customersMaterial')}</Typography>
      <Grid
        query={q}
        rows={q.data?.customersMaterial ?? []}
        rowKey={(r) => `${r.principal}-${r.product}`}
        cols={[
          { key: 's', label: t('mfg.jw.principal'), render: (r) => r.principalName },
          { key: 'p', label: t('mfg.common.item'), render: (r) => r.productName },
          { key: 'q', label: t('mfg.common.quantity'), align: 'right', render: (r) => qty(r.qty) },
        ]}
      />
    </Stack>
  );
}

function Ageing() {
  const q = useQuery({ queryKey: ['mfg-jw-ageing'], queryFn: () => getJwAgeing() });
  return (
    <Stack spacing={2}>
      <Alert severity={q.data?.overdue ? 'warning' : 'info'}>{t('mfg.jw.ageingHelp')}</Alert>
      <Grid
        query={q}
        rows={q.data?.rows ?? []}
        rowKey={(r) => r.challanLine}
        cols={[
          { key: 'c', label: t('mfg.jw.challan'), render: (r) => r.challan },
          { key: 's', label: t('mfg.jw.worker'), render: (r) => r.supplier },
          { key: 'p', label: t('mfg.common.item'), render: (r) => r.product },
          { key: 'q', label: t('mfg.jw.open'), align: 'right', render: (r) => qty(r.openQty) },
          { key: 'v', label: t('mfg.common.value'), align: 'right', render: (r) => money(r.value) },
          { key: 'k', label: t('mfg.jw.goodsKind'), render: (r) => (r.goodsKind === 'CAPITAL' ? t('mfg.jw.kindCapital') : t('mfg.jw.kindInput')) },
          { key: 'd', label: t('mfg.jw.days'), align: 'right', render: (r) => `${r.days} / ${r.limitDays}` },
          { key: 'b', label: t('mfg.jw.dueBy'), render: (r) => day(r.dueBy) },
          { key: 'st', label: t('mfg.common.status'), render: (r) => <Pill value={r.status} /> },
        ]}
      />
    </Stack>
  );
}

function Itc04() {
  const qc = useQueryClient();
  const { canPlan } = useMfgRights();
  const { run, error, clear } = useRun();
  const due = useQuery({ queryKey: ['mfg-itc-due'], queryFn: getItc04Due });
  const filings = useQuery({ queryKey: ['mfg-itc-filings'], queryFn: listItc04Filings });
  const y = fyStartYear();
  const [from, setFrom] = useState(`${y}-04-01`);
  const [to, setTo] = useState(todayIso());
  const [shown, setShown] = useState(false);
  const tables = useQuery({ queryKey: ['mfg-itc', from, to], queryFn: () => getItc04(from, to), enabled: shown });
  const [filing, setFiling] = useState<number | null>(null);
  const [ack, setAck] = useState('');
  const reload = () => void qc.invalidateQueries({ queryKey: ['mfg-itc-filings'] });
  return (
    <Stack spacing={2}>
      <ErrorLine error={error} onClose={clear} />
      <Alert severity="info">{t('mfg.jw.itcHelp')}</Alert>
      <Grid
        query={due}
        rows={due.data?.periods ?? []}
        rowKey={(p) => p.label}
        cols={[
          { key: 'l', label: t('mfg.jw.period'), render: (p) => p.label },
          { key: 'f', label: t('mfg.common.from'), render: (p) => day(p.from) },
          { key: 't', label: t('mfg.common.to'), render: (p) => day(p.to) },
          { key: 'd', label: t('mfg.jw.dueDate'), render: (p) => day(p.dueDate) },
          { key: 's', label: t('mfg.common.status'), render: (p) => (p.filed ? <Pill value="FILED" /> : <Pill value="OPEN" />) },
        ]}
      />
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems={{ sm: 'center' }}>
        <TextField size="small" type="date" label={t('mfg.common.from')} value={from} onChange={(e) => setFrom(e.target.value)} InputLabelProps={{ shrink: true }} />
        <TextField size="small" type="date" label={t('mfg.common.to')} value={to} onChange={(e) => setTo(e.target.value)} InputLabelProps={{ shrink: true }} />
        <Button variant="contained" onClick={() => setShown(true)}>{t('mfg.jw.showTables')}</Button>
        <Button onClick={async () => { const b = await run(() => downloadItc04(from, to)); if (b) saveBlob(b, `itc04-${from}-${to}.csv`); }}>{t('mfg.common.exportCsv')}</Button>
      </Stack>
      {tables.data ? (
        <Stack spacing={2}>
          <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
            <Stat label={t('mfg.jw.table4')} value={tables.data.table4.length} />
            <Stat label={t('mfg.jw.table5a')} value={tables.data.table5a.length} />
            <Stat label={t('mfg.jw.table5b')} value={tables.data.table5b.length} />
            <Stat label={t('mfg.jw.table5c')} value={tables.data.table5c.length} />
            <Stat label={t('mfg.jw.unmatched')} value={String(tables.data.summary.unmatched ?? 0)} tone={Number(tables.data.summary.unmatched) > 0 ? 'bad' : undefined} />
          </Stack>
          <ItcTable title={t('mfg.jw.table4')} rows={tables.data.table4} />
          <ItcTable title={t('mfg.jw.table5a')} rows={tables.data.table5a} />
          <ItcTable title={t('mfg.jw.table5b')} rows={tables.data.table5b} />
          <ItcTable title={t('mfg.jw.table5c')} rows={tables.data.table5c} />
        </Stack>
      ) : null}
      <Typography variant="subtitle2">{t('mfg.jw.filings')}</Typography>
      <Stack direction="row" spacing={2}>
        <Button disabled={!canPlan} onClick={async () => { if (await run(() => prepareItc04(y))) reload(); }}>{t('mfg.jw.prepare')}</Button>
      </Stack>
      <Grid
        query={filings}
        rows={filings.data ?? []}
        rowKey={(f) => f.id}
        cols={[
          { key: 'l', label: t('mfg.jw.period'), render: (f) => f.periodLabel },
          { key: 's', label: t('mfg.common.status'), render: (f) => <Pill value={f.status} /> },
          { key: 'o', label: t('mfg.jw.filedOn'), render: (f) => day(f.filedOn) },
          { key: 'a', label: t('mfg.jw.ack'), render: (f) => f.acknowledgement || '—' },
          { key: 'x', label: '', render: (f) => (f.status !== 'FILED' ? <Button size="small" disabled={!canPlan} onClick={() => setFiling(f.id)}>{t('mfg.jw.markFiled')}</Button> : null) },
        ]}
      />
      {filing !== null ? (
        <Dialog open onClose={() => setFiling(null)}>
          <DialogTitle>{t('mfg.jw.markFiled')}</DialogTitle>
          <DialogContent>
            <TextField sx={{ mt: 1 }} size="small" label={t('mfg.jw.ack')} value={ack} onChange={(e) => setAck(e.target.value)} />
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setFiling(null)}>{t('common.cancel')}</Button>
            <Button variant="contained" onClick={async () => { if (await run(() => markItc04Filed(filing, { filedOn: todayIso(), acknowledgement: ack }))) { setFiling(null); setAck(''); reload(); } }}>{t('common.save')}</Button>
          </DialogActions>
        </Dialog>
      ) : null}
    </Stack>
  );
}

function ItcTable({ title, rows }: { title: string; rows: Array<Record<string, unknown>> }) {
  if (!rows.length) return null;
  const keys = Object.keys(rows[0]);
  return (
    <Stack spacing={0.5}>
      <Typography variant="subtitle2">{title}</Typography>
      <Grid
        rows={rows}
        rowKey={(r) => JSON.stringify(r)}
        cols={keys.map((k) => ({ key: k, label: k.replace(/_/g, ' '), render: (r: Record<string, unknown>) => String(r[k] ?? '') }))}
      />
    </Stack>
  );
}
