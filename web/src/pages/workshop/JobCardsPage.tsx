import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Divider from '@mui/material/Divider';
import FormControlLabel from '@mui/material/FormControlLabel';
import Link from '@mui/material/Link';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import {
  bays,
  contracts,
  jobs,
  type Contract,
  type Job,
  type JobLine,
  type ServiceBay,
} from '@/api/care';
import { useAuth } from '@/auth/AuthContext';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { CreateDialog } from '@/components/CreateDialog';
import { EmptyState, ErrorState, ListSkeleton } from '@/components/PageState';
import { isWorkshopEnabled } from '@/config/features';
import { t } from '@/i18n';
import { ageSeconds, formatDay, formatSpan, formatStamp, fromLocalInput, plainNumber, toLocalInput } from '@/care/format';
import {
  ActivityTimeline,
  CareHeader,
  CareTable,
  CustomerLink,
  Field,
  LinkedRecords,
  MasterDetail,
  MemberPicker,
  Pager,
  SearchField,
  StatusPill,
  type CareColumn,
  VisuallyHidden,
} from '@/care/kit';
import { canChangeCare, conflictInfo, useListPath, useNotice, useUrlFilters } from '@/care/hooks';
import { BayPicker, CatalogPicker, ContractPicker, WarehousePicker } from '@/care/pickers';
import { getCustomer } from '@/api/resources';
import { enumLabel } from '@/utils/enumLabels';
import { formatMoney } from '@/utils/money';
import { CustomerField } from '@/pages/growth/widgets';
import { PageShell } from '@/pages/phase/phaseShared';
import type { Customer, Product } from '@/types/domain';

const STATUSES = ['DRAFT', 'IN_PROGRESS', 'INVOICED', 'CANCELLED'] as const;
const PAGE_SIZE = 20;
const BASE = '/workshop/jobs';

export function JobCardsPage() {
  if (!isWorkshopEnabled()) {
    return <PageShell title={t('nav.jobCards')}><Typography>{t('erp.moduleDisabled')}</Typography></PageShell>;
  }
  return <JobsWorkspace />;
}

function isOpen(job: Job) {
  return job.status === 'DRAFT' || job.status === 'IN_PROGRESS';
}

function JobsWorkspace() {
  const { id } = useParams();
  const creating = id === 'new';
  const selectedId = id && !creating ? Number(id) : null;
  const { user } = useAuth();
  const canChange = canChangeCare(user);
  const listPath = useListPath(BASE);
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { values, set } = useUrlFilters({ q: '', status: '', technician: '', view: 'list', day: '', page: '1' });
  const [baysOpen, setBaysOpen] = useState(false);
  const page = Math.max(1, Number(values.page) || 1);
  const list = useQuery({
    queryKey: ['jobs', 'list', values, page],
    queryFn: () =>
      jobs.list({
        q: values.q || undefined,
        status: values.status || undefined,
        technician: values.technician || undefined,
        page,
        pageSize: PAGE_SIZE,
      }),
    enabled: values.view === 'list',
  });
  const rows = list.data?.results ?? [];
  const columns: CareColumn<Job>[] = [
    { key: 'number', header: t('care.jobs.col.job'), primary: true, render: (row) => row.number },
    { key: 'customer', header: t('growth.customer'), render: (row) => row.customerName },
    {
      key: 'vehicle', header: t('care.jobs.col.vehicle'),
      render: (row) => [row.registrationNo, row.vehicleModel].filter(Boolean).join(' · '),
    },
    { key: 'tech', header: t('care.jobs.technician'), render: (row) => row.technicianName },
    {
      key: 'bay', header: t('care.jobs.col.booking'),
      render: (row) => (row.serviceBayName ? `${row.serviceBayName} · ${formatStamp(row.scheduledStart)}` : ''),
    },
    { key: 'status', header: t('growth.status'), render: (row) => <StatusPill group="jobStatus" value={row.status} /> },
    { key: 'total', header: t('care.jobs.total'), align: 'right', render: (row) => formatMoney(row.total) },
    { key: 'age', header: t('care.tickets.col.age'), render: (row) => formatSpan(ageSeconds(row.createdAt)) },
  ];
  const listNode = (
    <Stack spacing={1.5}>
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
        <SearchField value={values.q} onChange={(q) => set({ q })} label={t('care.jobs.search')} />
        <TextField select size="small" label={t('growth.status')} value={values.status} onChange={(e) => set({ status: e.target.value })} sx={{ minWidth: 160 }}>
          <MenuItem value="">{t('growth.all')}</MenuItem>
          {STATUSES.map((value) => <MenuItem key={value} value={value}>{enumLabel('jobStatus', value)}</MenuItem>)}
        </TextField>
        <MemberPicker label={t('care.jobs.technician')} value={values.technician ? Number(values.technician) : null} onChange={(m) => set({ technician: m ? String(m) : '' })} minWidth={180} />
        <ToggleButtonGroup size="small" exclusive value={values.view} onChange={(_, next) => next && set({ view: next })} aria-label={t('care.tickets.view')}>
          <ToggleButton value="list">{t('care.tickets.viewList')}</ToggleButton>
          <ToggleButton value="bays">{t('care.jobs.viewBays')}</ToggleButton>
        </ToggleButtonGroup>
      </Stack>
      {values.view === 'bays' ? (
        <BayBoard day={values.day} onDay={(day) => set({ day })} />
      ) : (
        <>
          {list.isLoading ? <ListSkeleton rows={6} /> : null}
          {list.isError ? <ErrorState message={getErrorMessage(list.error)} error={list.error} onRetry={() => void list.refetch()} /> : null}
          {!list.isLoading && !list.isError && rows.length === 0 ? (
            <EmptyState
              description={t('cog.emptyJobCards')}
              action={canChange ? <Button variant="contained" onClick={() => navigate(listPath('/new'))}>{t('growth.createJobCard')}</Button> : undefined}
            />
          ) : null}
          {rows.length > 0 ? (
            <CareTable
              caption={t('nav.jobCards')}
              columns={selectedId ? columns.filter((c) => ['number', 'customer', 'status'].includes(c.key)) : columns}
              rows={rows}
              rowKey={(row) => row.id}
              rowHref={(row) => listPath(`/${row.id}`)}
              selectedId={selectedId}
            />
          ) : null}
          <Pager page={page} count={list.data?.count ?? 0} pageSize={PAGE_SIZE} onPage={(next) => set({ page: String(next) })} />
        </>
      )}
    </Stack>
  );
  return (
    <Stack spacing={2}>
      <CareHeader
        title={t('nav.jobCards')}
        subtitle={t('care.jobs.subtitle')}
        actions={
          <>
            {canChange ? <Button variant="outlined" onClick={() => setBaysOpen(true)}>{t('care.jobs.manageBays')}</Button> : null}
            {canChange ? <Button variant="contained" onClick={() => navigate(listPath('/new'))}>{t('growth.createJobCard')}</Button> : null}
          </>
        }
      />
      <MasterDetail
        list={listNode}
        detail={selectedId ? <JobDetail key={selectedId} id={selectedId} canChange={canChange} /> : null}
        hasSelection={selectedId != null}
        backTo={listPath()}
        detailLabel={t('care.jobs.detail')}
      />
      <NewJobDialog open={creating && canChange} onClose={() => navigate(listPath())} prefill={searchParams} />
      <BaysDialog open={baysOpen} onClose={() => setBaysOpen(false)} />
    </Stack>
  );
}

// ---- bays ---------------------------------------------------------------------------------------------------------------------

function BaysDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const feedback = useNotice();
  const [name, setName] = useState('');
  const list = useQuery({ queryKey: ['bays', 'all'], queryFn: () => bays.list(true), enabled: open });
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['bays'] });
    void qc.invalidateQueries({ queryKey: ['care-pick', 'bay'] });
  };
  const add = useMutation({
    mutationFn: () => bays.create(name.trim()),
    onSuccess: () => { setName(''); feedback.ok(t('care.jobs.bayAdded')); refresh(); },
    onError: (err) => feedback.fail(err),
  });
  const toggle = useMutation({
    mutationFn: (bay: ServiceBay) => bays.update(bay.id, { is_active: !bay.isActive }),
    onSuccess: refresh,
    onError: (err) => feedback.fail(err),
  });
  const remove = useMutation({
    mutationFn: (bay: ServiceBay) => bays.remove(bay.id),
    onSuccess: () => { feedback.ok(t('care.jobs.bayRemoved')); refresh(); },
    onError: (err) => feedback.fail(err),
  });
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="xs" aria-labelledby="bays-title">
      <DialogTitle id="bays-title">{t('care.jobs.manageBays')}</DialogTitle>
      <DialogContent>
        <Stack spacing={1.5} sx={{ pt: 1 }}>
          {feedback.node}
          {(list.data?.results ?? []).length === 0 && !list.isLoading ? (
            <Typography variant="body2" color="text.secondary">{t('care.jobs.noBays')}</Typography>
          ) : null}
          {(list.data?.results ?? []).map((bay) => (
            <Stack key={bay.id} direction="row" alignItems="center" spacing={1}>
              <Typography sx={{ flex: 1 }}>{bay.name}</Typography>
              <FormControlLabel
                control={<Switch checked={bay.isActive} onChange={() => toggle.mutate(bay)} />}
                label={bay.isActive ? t('care.jobs.bayOn') : t('care.jobs.bayOff')}
              />
              <Button size="small" color="error" onClick={() => remove.mutate(bay)}>{t('common.delete')}</Button>
            </Stack>
          ))}
          <Stack direction="row" spacing={1}>
            <TextField size="small" fullWidth label={t('care.jobs.bayName')} value={name} onChange={(e) => setName(e.target.value)} />
            <Button variant="contained" disabled={!name.trim() || add.isPending} onClick={() => add.mutate()}>{t('common.add')}</Button>
          </Stack>
        </Stack>
      </DialogContent>
      <DialogActions><Button onClick={onClose}>{t('common.close')}</Button></DialogActions>
    </Dialog>
  );
}

/** One column per bay for a day, jobs in time order. */
function BayBoard({ day, onDay }: { day: string; onDay: (day: string) => void }) {
  const today = new Date();
  const value = day || `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
  const baysQuery = useQuery({ queryKey: ['bays', 'active'], queryFn: () => bays.list() });
  const board = useQuery({
    queryKey: ['jobs', 'board', value],
    queryFn: () => jobs.list({ scheduled_from: value, scheduled_to: value, pageSize: 100 }),
  });
  const listPath = useListPath(BASE);
  const rows = (board.data?.results ?? []).filter((job) => job.status !== 'CANCELLED');
  const columns = baysQuery.data?.results ?? [];
  return (
    <Stack spacing={1}>
      <TextField size="small" type="date" label={t('care.jobs.boardDay')} value={value} onChange={(e) => onDay(e.target.value)} InputLabelProps={{ shrink: true }} sx={{ alignSelf: 'flex-start' }} />
      {board.isError ? <Typography color="error">{getErrorMessage(board.error)}</Typography> : null}
      {columns.length === 0 && !baysQuery.isLoading ? <Typography variant="body2" color="text.secondary">{t('care.jobs.noBays')}</Typography> : null}
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1}>
        {columns.map((bay) => {
          const inBay = rows.filter((job) => job.serviceBay === bay.id).sort((a, b) => String(a.scheduledStart).localeCompare(String(b.scheduledStart)));
          return (
            <Paper key={bay.id} variant="outlined" sx={{ p: 1.5, flex: 1, minWidth: 0 }} component="section" aria-label={bay.name}>
              <Typography variant="subtitle2" component="h2">{bay.name}</Typography>
              {inBay.length === 0 ? <Typography variant="caption" color="text.secondary">{t('care.jobs.bayFree')}</Typography> : null}
              <Stack spacing={1} sx={{ mt: 1 }}>
                {inBay.map((job) => (
                  <Box key={job.id}>
                    <Typography variant="caption" color="text.secondary">
                      {formatStamp(job.scheduledStart).split(',').pop()} – {formatStamp(job.scheduledEnd).split(',').pop()}
                    </Typography>
                    <Link component={RouterLink} to={listPath(`/${job.id}`)} underline="hover" display="block">
                      {job.number} · {job.customerName}
                    </Link>
                    <Typography variant="caption" color="text.secondary">{job.registrationNo} {job.technicianName}</Typography>
                  </Box>
                ))}
              </Stack>
            </Paper>
          );
        })}
      </Stack>
    </Stack>
  );
}

// ---- create -------------------------------------------------------------------------------------------------------------------

function NewJobDialog({ open, onClose, prefill }: { open: boolean; onClose: () => void; prefill: URLSearchParams }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [complaint, setComplaint] = useState('');
  const [registration, setRegistration] = useState('');
  const [model, setModel] = useState('');
  const [odometer, setOdometer] = useState('');
  const [technician, setTechnician] = useState<number | null>(null);
  const [contract, setContract] = useState<Contract | null>(null);
  const [warehouse, setWarehouse] = useState<number | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const prefillCustomer = Number(prefill.get('customer')) || null;
  const ticket = Number(prefill.get('ticket')) || null;
  const sourceComplaint = Number(prefill.get('complaint')) || null;
  useQuery({
    queryKey: ['care-prefill-customer', prefillCustomer],
    enabled: open && prefillCustomer != null && customer == null,
    queryFn: async () => {
      const row = await getCustomer(prefillCustomer!);
      setCustomer(row);
      return row;
    },
  });
  const coverage = useQuery({
    queryKey: ['care-coverage', customer?.id],
    enabled: open && customer != null,
    queryFn: () => contracts.coverage(customer!.id),
  });
  const offered = (coverage.data ?? []).filter((row) => row.id !== contract?.id);
  const create = useMutation({
    mutationFn: (allowOverlap: boolean) =>
      jobs.create({
        customer: customer!.id,
        complaint,
        registration_no: registration,
        vehicle_model: model,
        odometer_reading: odometer || undefined,
        technician,
        contract: contract?.id ?? null,
        warehouse,
        ticket,
        source_complaint: sourceComplaint,
        ...(allowOverlap ? { allow_overlap: true } : {}),
      }),
    onSuccess: (row) => {
      void qc.invalidateQueries({ queryKey: ['jobs'] });
      setComplaint(''); setRegistration(''); setModel(''); setOdometer(''); setError(''); setBusy('');
      navigate({ pathname: `${BASE}/${row.id}` });
    },
    onError: (err) => {
      const conflict = conflictInfo(err);
      if (conflict?.code === 'technician_busy') setBusy(conflict.message);
      else setError(getErrorMessage(err));
    },
  });
  return (
    <>
      <CreateDialog
        open={open && !busy}
        onClose={onClose}
        title={t('growth.createJobCard')}
        submitLabel={t('growth.createJobCard')}
        submitDisabled={!customer || create.isPending}
        dirty={Boolean(complaint || registration || model)}
        onSubmit={() => create.mutate(false)}
      >
        <CustomerField value={customer} onChange={(next) => { setCustomer(next); setContract(null); }} />
        {ticket || sourceComplaint ? <Alert severity="info">{t('care.jobs.fromRecord')}</Alert> : null}
        <TextField size="small" multiline minRows={2} label={t('growth.complaint')} value={complaint} onChange={(e) => setComplaint(e.target.value)} />
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
          <TextField fullWidth size="small" label={t('growth.registrationNo')} value={registration} onChange={(e) => setRegistration(e.target.value)} />
          <TextField fullWidth size="small" label={t('growth.vehicleModel')} value={model} onChange={(e) => setModel(e.target.value)} />
          <TextField fullWidth size="small" label={t('growth.odometer')} value={odometer} onChange={(e) => setOdometer(e.target.value)} inputProps={{ inputMode: 'decimal' }} />
        </Stack>
        <MemberPicker label={t('care.jobs.technician')} value={technician} onChange={setTechnician} minWidth={0} />
        {offered.length > 0 && !contract ? (
          <Alert severity="info" action={<Button size="small" onClick={() => setContract({ id: offered[0].id, number: offered[0].number, startDate: offered[0].startDate, endDate: offered[0].endDate } as Contract)}>{t('care.jobs.useContract')}</Button>}>
            {t('care.jobs.coverageFound', { number: offered[0].number, end: formatDay(offered[0].endDate) })}
          </Alert>
        ) : null}
        <ContractPicker customerId={customer?.id ?? null} value={contract} onChange={setContract} helperText={t('care.jobs.contractHelp')} />
        <WarehousePicker value={warehouse} onChange={setWarehouse} />
        {error ? <Typography role="alert" color="error" variant="body2">{error}</Typography> : null}
      </CreateDialog>
      <ConfirmDialog
        open={open && Boolean(busy)}
        title={t('care.jobs.technicianBusyTitle')}
        body={busy}
        confirmLabel={t('care.jobs.bookAnyway')}
        confirmColor="warning"
        onClose={() => setBusy('')}
        onConfirm={() => { setBusy(''); create.mutate(true); }}
      />
    </>
  );
}

// ---- detail ------------------------------------------------------------------------------------------------------------------

function lineTotal(line: JobLine) {
  return Number(line.quantity) * Number(line.unitPrice);
}

export function JobDetail({ id, canChange }: { id: number; canChange: boolean }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const feedback = useNotice();
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [reopenOpen, setReopenOpen] = useState(false);
  const [lineEdit, setLineEdit] = useState<JobLine | null>(null);
  const detail = useQuery({ queryKey: ['jobs', 'detail', id], queryFn: () => jobs.get(id) });
  const job = detail.data;
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['jobs'] });
    void qc.invalidateQueries({ queryKey: ['care-activity', 'JobCard', id] });
    void qc.invalidateQueries({ queryKey: ['care-links'] });
  };
  const run = useMutation({
    mutationFn: async (work: { do: () => Promise<unknown>; done: string }) => {
      await work.do();
      return work.done;
    },
    onSuccess: (done) => { feedback.ok(done); refresh(); },
    onError: (err) => feedback.fail(err),
  });
  if (detail.isLoading) return <ListSkeleton rows={4} />;
  if (detail.isError || !job) {
    return <ErrorState message={getErrorMessage(detail.error)} error={detail.error} onRetry={() => void detail.refetch()} />;
  }
  const open = isOpen(job);
  const hasInvoice = job.salesInvoice != null;
  const editable = canChange && open && !hasInvoice;
  const lines = job.lines ?? [];
  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Stack spacing={2}>
        <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={1}>
          <Box>
            <Typography variant="h6" component="h2">{job.number}</Typography>
            <Stack direction="row" spacing={1} alignItems="center">
              <StatusPill group="jobStatus" value={job.status} />
              {job.contractNumber ? <Typography variant="body2" color="success.main">{t('care.jobs.coveredBy', { number: job.contractNumber })}</Typography> : null}
            </Stack>
          </Box>
          <Button size="small" component={RouterLink} to={`/workshop/jobs/${id}/slip`} target="_blank">{t('care.jobs.printSlip')}</Button>
        </Stack>
        {feedback.node}
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} flexWrap="wrap" useFlexGap>
          <Field label={t('growth.customer')}><CustomerLink id={job.customer} name={job.customerName} /></Field>
          <Field label={t('care.jobs.col.vehicle')}>{[job.registrationNo, job.vehicleModel, job.odometerReading ? `${plainNumber(job.odometerReading)} km` : ''].filter(Boolean).join(' · ')}</Field>
          <Field label={t('care.jobs.technician')}>{job.technicianName}</Field>
          <Field label={t('care.jobs.col.booking')}>
            {job.serviceBayName ? `${job.serviceBayName} · ${formatStamp(job.scheduledStart)} – ${formatStamp(job.scheduledEnd)}` : ''}
          </Field>
          {job.ticket ? <Field label={t('care.pick.ticket')}><Link component={RouterLink} to={`/support/tickets/${job.ticket}`}>{job.ticketNumber}</Link></Field> : null}
          {job.sourceComplaint ? <Field label={t('care.jobs.complaintRecord')}><Link component={RouterLink} to={`/complaints/${job.sourceComplaint}`}>{job.complaintNumber}</Link></Field> : null}
        </Stack>
        <Field label={t('growth.complaint')}><Box sx={{ whiteSpace: 'pre-wrap' }}>{job.complaint}</Box></Field>

        {canChange ? (
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            {job.status === 'DRAFT' ? (
              <Button size="small" variant="contained" disabled={run.isPending} onClick={() => run.mutate({ do: () => jobs.start(id), done: t('care.jobs.started') })}>{t('care.jobs.start')}</Button>
            ) : null}
            {open && !hasInvoice && lines.length > 0 ? (
              <Button
                size="small"
                variant="contained"
                disabled={run.isPending}
                onClick={() => run.mutate({
                  do: async () => {
                    const made = await jobs.convert(id, `job-${id}-convert-${lines.length}`);
                    if (made.salesInvoice) navigate(`/sales/history/${made.salesInvoice}`);
                  },
                  done: t('care.jobs.invoiceDrafted'),
                })}
              >
                {t('growth.createDraftInvoice')}
              </Button>
            ) : null}
            {hasInvoice ? (
              <Button size="small" variant="contained" component={RouterLink} to={`/sales/history/${job.salesInvoice}`}>
                {t('care.jobs.openInvoice', { number: job.invoiceNumber || `#${job.salesInvoice}` })}
              </Button>
            ) : null}
            {open && hasInvoice && job.invoiceStatus === 'DRAFT' ? (
              <Button size="small" onClick={() => setReopenOpen(true)}>{t('care.jobs.revert')}</Button>
            ) : null}
            {open ? <Button size="small" onClick={() => setEditOpen(true)}>{t('common.edit')}</Button> : null}
            {isOpen(job) ? <Button size="small" onClick={() => setScheduleOpen(true)}>{t('care.jobs.schedule')}</Button> : null}
            {job.status !== 'CANCELLED' && job.invoiceStatus !== 'COMPLETED' && job.status !== 'INVOICED' ? (
              <Button size="small" color="error" onClick={() => setCancelOpen(true)}>{t('growth.cancel')}</Button>
            ) : null}
          </Stack>
        ) : null}
        {hasInvoice && open ? <Alert severity="info">{t('care.jobs.lockedByInvoice')}</Alert> : null}

        <Box component="section" aria-label={t('growth.lines')}>
          <Typography variant="subtitle2" component="h3">{t('growth.lines')}</Typography>
          {lines.length === 0 ? <Typography variant="body2" color="text.secondary">{t('care.jobs.noLines')}</Typography> : (
            <Box sx={{ overflowX: 'auto' }}>
              <Table size="small" aria-label={t('growth.lines')}>
                <TableHead>
                  <TableRow>
                    <TableCell scope="col">{t('care.jobs.kind')}</TableCell>
                    <TableCell scope="col">{t('growth.product')}</TableCell>
                    <TableCell scope="col" align="right">{t('growth.quantity')}</TableCell>
                    <TableCell scope="col" align="right">{t('growth.unitPrice')}</TableCell>
                    <TableCell scope="col" align="right">{t('care.jobs.amount')}</TableCell>
                    {editable ? <TableCell scope="col"><VisuallyHidden>{t('care.common.actions')}</VisuallyHidden></TableCell> : null}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {lines.map((line) => (
                    <TableRow key={line.id}>
                      <TableCell>{enumLabel('lineKind', line.kind)}</TableCell>
                      <TableCell>
                        {line.productName}
                        {line.batchNo ? <Typography variant="caption" display="block">{t('care.jobs.batch')}: {line.batchNo}</Typography> : null}
                        {line.serial ? <Typography variant="caption" display="block">{t('care.jobs.serial')} #{line.serial}</Typography> : null}
                      </TableCell>
                      <TableCell align="right">{plainNumber(line.quantity)}</TableCell>
                      <TableCell align="right">
                        {line.coveredByContract ? t('care.jobs.covered') : Number(line.unitPrice) === 0 ? t('care.jobs.noCharge') : formatMoney(line.unitPrice)}
                      </TableCell>
                      <TableCell align="right">{formatMoney(lineTotal(line))}</TableCell>
                      {editable ? (
                        <TableCell align="right">
                          <Button size="small" onClick={() => setLineEdit(line)} aria-label={t('care.jobs.editLine', { name: line.productName })}>{t('common.edit')}</Button>
                          <Button size="small" color="error" onClick={() => run.mutate({ do: () => jobs.removeLine(id, line.id), done: t('care.jobs.lineRemoved') })} aria-label={t('care.jobs.removeLine', { name: line.productName })}>{t('growth.remove')}</Button>
                        </TableCell>
                      ) : null}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Box>
          )}
          <Stack alignItems="flex-end" sx={{ mt: 1 }}>
            <Typography variant="body2">{t('care.jobs.subtotal')}: {formatMoney(job.subtotal)}</Typography>
            <Typography variant="body2">{t('care.jobs.gst')}: {formatMoney(job.gstTotal)}</Typography>
            <Typography variant="subtitle2" component="p">{t('care.jobs.total')}: {formatMoney(job.total)}</Typography>
          </Stack>
        </Box>
        {editable ? <AddLine job={job} onAdded={() => { feedback.ok(t('care.jobs.lineAdded')); refresh(); }} onError={feedback.fail} /> : null}
        {job.serialHistory?.length ? (
          <Box>
            <Typography variant="subtitle2" component="h3">{t('growth.serialHistory')}</Typography>
            {job.serialHistory.map((group) => (
              <Typography key={group.serialId} variant="body2">
                #{group.serialId}: {group.jobs.map((past) => `${past.number} (${enumLabel('jobStatus', past.status)}, ${formatDay(past.date)})`).join(', ')}
                {group.capped ? ` · ${t('growth.serialHistoryCapped')}` : ''}
              </Typography>
            ))}
          </Box>
        ) : null}
        <Divider />
        <LinkedRecords entity="job_card" id={id} />
        <ActivityTimeline entity="JobCard" id={id} fetcher={() => jobs.activity(id)} />
      </Stack>

      <EditHeaderDialog job={job} open={editOpen} onClose={() => setEditOpen(false)} onSaved={refresh} />
      <ScheduleDialog job={job} open={scheduleOpen} onClose={() => setScheduleOpen(false)} onSaved={() => { feedback.ok(t('care.jobs.scheduled')); refresh(); }} />
      {lineEdit ? (
        <EditLineDialog job={job} line={lineEdit} onClose={() => setLineEdit(null)} onSaved={() => { feedback.ok(t('care.jobs.lineSaved')); refresh(); }} />
      ) : null}
      <ConfirmDialog
        open={cancelOpen}
        title={t('care.jobs.cancelTitle', { number: job.number })}
        body={t('care.jobs.cancelBody')}
        confirmColor="error"
        confirmLabel={t('care.jobs.cancelConfirm')}
        onClose={() => setCancelOpen(false)}
        onConfirm={() => { setCancelOpen(false); run.mutate({ do: () => jobs.cancel(id), done: t('care.jobs.cancelled') }); }}
      />
      <ConfirmDialog
        open={reopenOpen}
        title={t('care.jobs.revertTitle')}
        body={t('care.jobs.revertBody')}
        confirmLabel={t('care.jobs.revert')}
        confirmColor="warning"
        onClose={() => setReopenOpen(false)}
        onConfirm={() => { setReopenOpen(false); run.mutate({ do: () => jobs.reopen(id), done: t('care.jobs.reverted') }); }}
      />
    </Paper>
  );
}

function AddLine({ job, onAdded, onError }: { job: Job; onAdded: () => void; onError: (error: unknown) => void }) {
  const [kind, setKind] = useState<'PART' | 'LABOUR'>('PART');
  const [product, setProduct] = useState<Product | null>(null);
  const [quantity, setQuantity] = useState('1');
  const [price, setPrice] = useState('');
  const [free, setFree] = useState(false);
  const [covered, setCovered] = useState(false);
  const [minutes, setMinutes] = useState('');
  const [serial, setSerial] = useState('');
  const [batch, setBatch] = useState('');
  const options = useQuery({
    queryKey: ['jobs', 'stock-options', product?.id],
    enabled: kind === 'PART' && product != null,
    queryFn: () => jobs.stockOptions(product!.id),
  });
  const needsSerial = Boolean(options.data?.trackSerial);
  const needsBatch = Boolean(options.data?.trackBatch);
  const add = useMutation({
    mutationFn: () =>
      jobs.addLine(job.id, {
        kind,
        product: product!.id,
        quantity: needsSerial ? '1' : quantity,
        unit_price: covered || free ? '0' : price.trim() || String(product?.sellingPrice ?? '0'),
        serial: serial ? Number(serial) : null,
        batch: batch ? Number(batch) : null,
        labour_minutes: kind === 'LABOUR' && minutes ? Number(minutes) : undefined,
        covered_by_contract: covered || undefined,
      }),
    onSuccess: () => {
      setProduct(null); setQuantity('1'); setPrice(''); setFree(false); setCovered(false); setMinutes(''); setSerial(''); setBatch('');
      onAdded();
    },
    onError,
  });
  const invalid = !product || !(Number(quantity) > 0) || (needsSerial && !serial) || (needsBatch && !batch) || (!covered && !free && price.trim() !== '' && Number(price) < 0);
  return (
    <Paper variant="outlined" sx={{ p: 1.5 }} component="section" aria-label={t('care.jobs.addLine')}>
      <Stack spacing={1.5}>
        <Typography variant="subtitle2" component="h3">{t('care.jobs.addLine')}</Typography>
        <ToggleButtonGroup size="small" exclusive value={kind} onChange={(_, next) => { if (next) { setKind(next); setProduct(null); setSerial(''); setBatch(''); } }} aria-label={t('care.jobs.kind')}>
          <ToggleButton value="PART">{t('care.jobs.part')}</ToggleButton>
          <ToggleButton value="LABOUR">{t('care.jobs.labour')}</ToggleButton>
        </ToggleButtonGroup>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ sm: 'center' }}>
          <CatalogPicker kind={kind === 'PART' ? 'GOODS' : 'SERVICE'} value={product} onChange={(next) => { setProduct(next); setSerial(''); setBatch(''); setPrice(next ? String(next.sellingPrice ?? '') : ''); }} />
          <TextField size="small" label={t('growth.quantity')} value={needsSerial ? '1' : quantity} disabled={needsSerial} onChange={(e) => setQuantity(e.target.value)} sx={{ width: 100 }} inputProps={{ inputMode: 'decimal' }} />
          <TextField size="small" label={t('growth.unitPrice')} value={covered || free ? '0' : price} disabled={covered || free} onChange={(e) => setPrice(e.target.value)} sx={{ width: 130 }} inputProps={{ inputMode: 'decimal' }} />
          {kind === 'LABOUR' ? <TextField size="small" label={t('care.jobs.minutes')} value={minutes} onChange={(e) => setMinutes(e.target.value)} sx={{ width: 110 }} inputProps={{ inputMode: 'numeric' }} /> : null}
        </Stack>
        {needsSerial ? (
          <TextField select size="small" required label={t('care.jobs.serial')} value={serial} onChange={(e) => setSerial(e.target.value)} helperText={options.data?.serials.length ? undefined : t('care.jobs.noSerials')}>
            {(options.data?.serials ?? []).map((row) => <MenuItem key={row.id} value={String(row.id)}>{row.serialNumber}</MenuItem>)}
          </TextField>
        ) : null}
        {needsBatch ? (
          <TextField select size="small" required label={t('care.jobs.batch')} value={batch} onChange={(e) => setBatch(e.target.value)} helperText={options.data?.batches.length ? undefined : t('care.jobs.noBatches')}>
            {(options.data?.batches ?? []).map((row) => (
              <MenuItem key={row.id} value={String(row.id)}>
                {row.batchNo}{row.expiryDate ? ` · ${t('care.jobs.expires', { date: formatDay(row.expiryDate) })}` : ''} · {t('care.jobs.available', { qty: plainNumber(row.available) })}
              </MenuItem>
            ))}
          </TextField>
        ) : null}
        <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
          <FormControlLabel control={<Checkbox checked={free} disabled={covered} onChange={(e) => setFree(e.target.checked)} />} label={t('care.jobs.noChargeLabel')} />
          {job.contract ? (
            <FormControlLabel control={<Checkbox checked={covered} onChange={(e) => setCovered(e.target.checked)} />} label={t('care.jobs.coveredLabel', { number: job.contractNumber })} />
          ) : null}
        </Stack>
        <Button size="small" variant="contained" sx={{ alignSelf: 'flex-start' }} disabled={invalid || add.isPending} onClick={() => add.mutate()}>
          {t('growth.addLine')}
        </Button>
      </Stack>
    </Paper>
  );
}

function EditLineDialog({ job, line, onClose, onSaved }: { job: Job; line: JobLine; onClose: () => void; onSaved: () => void }) {
  const [quantity, setQuantity] = useState(plainNumber(line.quantity));
  const [price, setPrice] = useState(line.unitPrice);
  const [error, setError] = useState('');
  const save = useMutation({
    mutationFn: () => jobs.editLine(job.id, line.id, { quantity, unit_price: price }),
    onSuccess: () => { onSaved(); onClose(); },
    onError: (err) => setError(getErrorMessage(err)),
  });
  return (
    <CreateDialog
      open
      onClose={onClose}
      title={t('care.jobs.editLine', { name: line.productName })}
      submitLabel={t('growth.save')}
      submitDisabled={!(Number(quantity) > 0) || Number(price) < 0 || save.isPending}
      onSubmit={() => save.mutate()}
    >
      <TextField size="small" label={t('growth.quantity')} value={quantity} onChange={(e) => setQuantity(e.target.value)} inputProps={{ inputMode: 'decimal' }} />
      <TextField size="small" label={t('growth.unitPrice')} value={line.coveredByContract ? '0' : price} disabled={line.coveredByContract} onChange={(e) => setPrice(e.target.value)} inputProps={{ inputMode: 'decimal' }} helperText={line.coveredByContract ? t('care.jobs.coveredPriceFixed') : undefined} />
      {error ? <Typography role="alert" color="error" variant="body2">{error}</Typography> : null}
    </CreateDialog>
  );
}

function EditHeaderDialog({ job, open, onClose, onSaved }: { job: Job; open: boolean; onClose: () => void; onSaved: () => void }) {
  const [complaint, setComplaint] = useState(job.complaint);
  const [registration, setRegistration] = useState(job.registrationNo);
  const [model, setModel] = useState(job.vehicleModel);
  const [odometer, setOdometer] = useState(job.odometerReading ?? '');
  const [technician, setTechnician] = useState<number | null>(job.technician);
  const [contract, setContract] = useState<Contract | null>(job.contract ? ({ id: job.contract, number: job.contractNumber } as Contract) : null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const save = useMutation({
    mutationFn: (allowOverlap: boolean) =>
      jobs.update(job.id, {
        complaint, registration_no: registration, vehicle_model: model, odometer_reading: odometer === '' ? null : odometer,
        technician, contract: contract?.id ?? null, ...(allowOverlap ? { allow_overlap: true } : {}),
      }, job.updatedAt),
    onSuccess: () => { setError(''); setBusy(''); onSaved(); onClose(); },
    onError: (err) => {
      const conflict = conflictInfo(err);
      if (conflict?.code === 'technician_busy') setBusy(conflict.message);
      else setError(getErrorMessage(err));
    },
  });
  return (
    <>
      <CreateDialog open={open && !busy} onClose={onClose} title={t('care.jobs.editTitle', { number: job.number })} submitLabel={t('growth.save')} submitDisabled={save.isPending} onSubmit={() => save.mutate(false)}>
        <TextField size="small" multiline minRows={2} label={t('growth.complaint')} value={complaint} onChange={(e) => setComplaint(e.target.value)} />
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
          <TextField fullWidth size="small" label={t('growth.registrationNo')} value={registration} onChange={(e) => setRegistration(e.target.value)} />
          <TextField fullWidth size="small" label={t('growth.vehicleModel')} value={model} onChange={(e) => setModel(e.target.value)} />
          <TextField fullWidth size="small" label={t('growth.odometer')} value={odometer} onChange={(e) => setOdometer(e.target.value)} inputProps={{ inputMode: 'decimal' }} />
        </Stack>
        <MemberPicker label={t('care.jobs.technician')} value={technician} onChange={setTechnician} minWidth={0} />
        <ContractPicker customerId={job.customer} value={contract} onChange={setContract} helperText={t('care.jobs.contractHelp')} />
        {error ? <Typography role="alert" color="error" variant="body2">{error}</Typography> : null}
      </CreateDialog>
      <ConfirmDialog open={open && Boolean(busy)} title={t('care.jobs.technicianBusyTitle')} body={busy} confirmLabel={t('care.jobs.bookAnyway')} confirmColor="warning" onClose={() => setBusy('')} onConfirm={() => { setBusy(''); save.mutate(true); }} />
    </>
  );
}

function ScheduleDialog({ job, open, onClose, onSaved }: { job: Job; open: boolean; onClose: () => void; onSaved: () => void }) {
  const [bay, setBay] = useState<ServiceBay | null>(job.serviceBay ? { id: job.serviceBay, name: job.serviceBayName, isActive: true } : null);
  const [start, setStart] = useState(toLocalInput(job.scheduledStart));
  const [end, setEnd] = useState(toLocalInput(job.scheduledEnd));
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const save = useMutation({
    mutationFn: (allowOverlap: boolean) =>
      jobs.schedule(job.id, {
        service_bay: bay!.id, scheduled_start: fromLocalInput(start), scheduled_end: fromLocalInput(end),
        ...(allowOverlap ? { allow_overlap: true } : {}),
      }),
    onSuccess: () => { setError(''); setBusy(''); onSaved(); onClose(); },
    onError: (err) => {
      const conflict = conflictInfo(err);
      if (conflict?.code === 'technician_busy') setBusy(conflict.message);
      else setError(getErrorMessage(err));
    },
  });
  const invalid = !bay || !start || !end || end <= start;
  return (
    <>
      <CreateDialog open={open && !busy} onClose={onClose} title={t('care.jobs.scheduleTitle', { number: job.number })} submitLabel={t('care.jobs.schedule')} submitDisabled={invalid || save.isPending} onSubmit={() => save.mutate(false)}>
        <BayPicker value={bay} onChange={setBay} required />
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
          <TextField fullWidth size="small" type="datetime-local" required label={t('care.jobs.from')} value={start} onChange={(e) => setStart(e.target.value)} InputLabelProps={{ shrink: true }} />
          <TextField fullWidth size="small" type="datetime-local" required label={t('care.jobs.to')} value={end} onChange={(e) => setEnd(e.target.value)} InputLabelProps={{ shrink: true }} error={Boolean(start && end && end <= start)} helperText={start && end && end <= start ? t('care.jobs.endAfterStart') : undefined} />
        </Stack>
        {error ? <Typography role="alert" color="error" variant="body2">{error}</Typography> : null}
      </CreateDialog>
      <ConfirmDialog open={open && Boolean(busy)} title={t('care.jobs.technicianBusyTitle')} body={busy} confirmLabel={t('care.jobs.bookAnyway')} confirmColor="warning" onClose={() => setBusy('')} onConfirm={() => { setBusy(''); save.mutate(true); }} />
    </>
  );
}

