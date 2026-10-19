import { useState } from 'react';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Divider from '@mui/material/Divider';
import FormControlLabel from '@mui/material/FormControlLabel';
import Checkbox from '@mui/material/Checkbox';
import Link from '@mui/material/Link';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom';
import { apiClient, getErrorMessage } from '@/api/client';
import { contracts, type Contract, type ServiceEvent, type Ticket } from '@/api/care';
import { useAuth } from '@/auth/AuthContext';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { CreateDialog } from '@/components/CreateDialog';
import { EmptyState, ErrorState, ListSkeleton } from '@/components/PageState';
import { isContractsEnabled } from '@/config/features';
import { t } from '@/i18n';
import { AttachmentPanel } from '@/care/attachments';
import { dayInput, formatDay, formatStamp, fromLocalInput, toLocalInput } from '@/care/format';
import {
  ActivityTimeline,
  CareHeader,
  CareTable,
  CustomerLink,
  Field,
  LinkedRecords,
  MasterDetail,
  Pager,
  SearchField,
  StatusPill,
  type CareColumn,
} from '@/care/kit';
import { canChangeCare, conflictInfo, useListPath, useNotice, useUrlFilters } from '@/care/hooks';
import { CatalogPicker, TicketPicker } from '@/care/pickers';
import { triggerBlobDownload } from '@/utils/blob';
import { enumLabel } from '@/utils/enumLabels';
import { formatMoney } from '@/utils/money';
import { CustomerField } from '@/pages/growth/widgets';
import { PageShell } from '@/pages/phase/phaseShared';
import type { Customer, Product } from '@/types/domain';

const TYPES = ['WARRANTY', 'AMC', 'SUBSCRIPTION', 'OTHER'] as const;
const STATUSES = ['ACTIVE', 'EXPIRING', 'EXPIRED', 'CANCELLED'] as const;
const CADENCES = ['MONTHLY', 'QUARTERLY', 'HALF_YEARLY', 'ANNUALLY', 'WEEKLY'] as const;
const PAGE_SIZE = 20;
const BASE = '/contracts';
const DAY_MS = 24 * 3600 * 1000;
/** The wall clock, read at render time. Module level so the render rules see no impure call. */
const wallClockMs = () => Date.now();

export function ContractsPage() {
  if (!isContractsEnabled()) {
    return <PageShell title={t('nav.contracts')}><Typography>{t('erp.moduleDisabled')}</Typography></PageShell>;
  }
  return <ContractsWorkspace />;
}

function termLabel(type: string) {
  return type === 'WARRANTY' ? t('care.contracts.warrantyPeriod') : t('care.contracts.contractPeriod');
}

function expiryText(row: Contract) {
  if (row.status === 'CANCELLED' || row.daysToExpiry == null) return '';
  if (row.daysToExpiry < 0) return t('care.contracts.expiredAgo', { days: Math.abs(row.daysToExpiry) });
  if (row.daysToExpiry === 0) return t('care.contracts.expiresToday');
  return t('care.contracts.expiresIn', { days: row.daysToExpiry });
}

function ContractsWorkspace() {
  const { id } = useParams();
  const selectedId = id ? Number(id) : null;
  const { user } = useAuth();
  const canChange = canChangeCare(user);
  const listPath = useListPath(BASE);
  const { values, set } = useUrlFilters({ q: '', status: '', type: '', soon: '', page: '1' });
  const [createOpen, setCreateOpen] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);
  const page = Math.max(1, Number(values.page) || 1);
  const list = useQuery({
    queryKey: ['contracts', 'list', values, page],
    queryFn: () =>
      contracts.list({
        q: values.q || undefined,
        status: values.status || undefined,
        contract_type: values.type || undefined,
        expiring_within_days: values.soon ? 30 : undefined,
        page,
        pageSize: PAGE_SIZE,
      }),
  });
  const rows = list.data?.results ?? [];
  const columns: CareColumn<Contract>[] = [
    { key: 'number', header: t('care.contracts.col.contract'), primary: true, render: (row) => row.number },
    { key: 'customer', header: t('growth.customer'), render: (row) => row.customerName },
    { key: 'type', header: t('growth.type'), render: (row) => enumLabel('contractType', row.contractType) },
    { key: 'products', header: t('care.contracts.col.products'), render: (row) => row.productNames.join(', ') },
    { key: 'end', header: t('growth.endDate'), render: (row) => formatDay(row.endDate) },
    { key: 'left', header: t('care.contracts.col.left'), render: expiryText },
    { key: 'value', header: t('growth.value'), align: 'right', render: (row) => (row.value ? formatMoney(row.value) : '—') },
    { key: 'status', header: t('growth.status'), render: (row) => <StatusPill group="contractStatus" value={row.status} /> },
  ];
  const listNode = (
    <Stack spacing={1.5}>
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
        <SearchField value={values.q} onChange={(q) => set({ q })} />
        <TextField select size="small" label={t('growth.status')} value={values.status} onChange={(e) => set({ status: e.target.value })} sx={{ minWidth: 160 }}>
          <MenuItem value="">{t('growth.all')}</MenuItem>
          {STATUSES.map((value) => <MenuItem key={value} value={value}>{enumLabel('contractStatus', value)}</MenuItem>)}
        </TextField>
        <TextField select size="small" label={t('growth.type')} value={values.type} onChange={(e) => set({ type: e.target.value })} sx={{ minWidth: 160 }}>
          <MenuItem value="">{t('growth.all')}</MenuItem>
          {TYPES.map((value) => <MenuItem key={value} value={value}>{enumLabel('contractType', value)}</MenuItem>)}
        </TextField>
        <FormControlLabel control={<Checkbox checked={Boolean(values.soon)} onChange={(e) => set({ soon: e.target.checked ? '1' : '' })} />} label={t('care.contracts.endingSoon')} />
      </Stack>
      {list.isLoading ? <ListSkeleton rows={6} /> : null}
      {list.isError ? <ErrorState message={getErrorMessage(list.error)} error={list.error} onRetry={() => void list.refetch()} /> : null}
      {!list.isLoading && !list.isError && rows.length === 0 ? (
        <EmptyState
          description={t('cog.emptyContracts')}
          action={canChange ? <Button variant="contained" onClick={() => setCreateOpen(true)}>{t('growth.addContract')}</Button> : undefined}
        />
      ) : null}
      {rows.length > 0 ? (
        <CareTable
          caption={t('nav.contracts')}
          columns={selectedId ? columns.filter((c) => ['number', 'customer', 'status'].includes(c.key)) : columns}
          rows={rows}
          rowKey={(row) => row.id}
          rowHref={(row) => listPath(`/${row.id}`)}
          selectedId={selectedId}
        />
      ) : null}
      <Pager page={page} count={list.data?.count ?? 0} pageSize={PAGE_SIZE} onPage={(next) => set({ page: String(next) })} />
    </Stack>
  );
  return (
    <Stack spacing={2}>
      <CareHeader
        title={t('nav.contracts')}
        subtitle={t('care.contracts.subtitle')}
        actions={
          <>
            <Button variant="outlined" aria-expanded={reportOpen} onClick={() => setReportOpen((open) => !open)}>{t('growth.report')}</Button>
            {canChange ? <Button variant="contained" onClick={() => setCreateOpen(true)}>{t('growth.addContract')}</Button> : null}
          </>
        }
      />
      {reportOpen ? <ContractReport /> : null}
      <MasterDetail
        list={listNode}
        detail={selectedId ? <ContractDetail key={selectedId} id={selectedId} canChange={canChange} isOwner={user?.role === 'OWNER'} backTo={listPath()} /> : null}
        hasSelection={selectedId != null}
        backTo={listPath()}
        detailLabel={t('care.contracts.detail')}
      />
      <ContractFormDialog open={createOpen} onClose={() => setCreateOpen(false)} />
    </Stack>
  );
}

function ContractReport() {
  const [cancelled, setCancelled] = useState(false);
  const report = useQuery({ queryKey: ['contracts', 'report', cancelled], queryFn: () => contracts.report(cancelled ? { include_cancelled: 1 } : undefined) });
  const summary = useQuery({ queryKey: ['contracts', 'summary'], queryFn: contracts.summary });
  const download = async () => {
    const response = await apiClient.get(contracts.exportUrl(cancelled ? { include_cancelled: 1 } : {}), { responseType: 'blob' });
    triggerBlobDownload(response.data as Blob, 'contracts-report.csv');
  };
  return (
    <Paper variant="outlined" sx={{ p: 2 }} component="section" aria-label={t('growth.report')}>
      <Stack spacing={1}>
        <FormControlLabel control={<Checkbox checked={cancelled} onChange={(e) => setCancelled(e.target.checked)} />} label={t('care.contracts.includeCancelled')} />
        {report.isError ? <Typography color="error">{getErrorMessage(report.error)}</Typography> : null}
        {(report.data ?? []).map((row) => (
          <Typography key={`${row.status}-${row.contractType}`} variant="body2">
            {enumLabel('contractStatus', row.status)} · {enumLabel('contractType', row.contractType)} · {formatMoney(row.value ?? 0)}
          </Typography>
        ))}
        {summary.data ? (
          <>
            <Typography variant="body2">{t('care.contracts.monthlyBilling', { value: formatMoney(summary.data.monthlyRecurringValue) })}</Typography>
            <Typography variant="caption" color="text.secondary">{t('care.contracts.endingByMonth')}</Typography>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              {summary.data.expiringByMonth.map((row) => <Chip key={row.month} size="small" label={`${row.month}: ${row.count}`} />)}
            </Stack>
          </>
        ) : null}
        <Button size="small" sx={{ alignSelf: 'flex-start' }} onClick={() => void download()}>{t('care.contracts.exportCsv')}</Button>
      </Stack>
    </Paper>
  );
}

/** Create and edit share one form. The server warns about an overlapping term; the person may go ahead. */
function ContractFormDialog({ open, onClose, existing }: { open: boolean; onClose: () => void; existing?: Contract }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const listPath = useListPath(BASE);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [type, setType] = useState<string>(existing?.contractType ?? 'WARRANTY');
  const [start, setStart] = useState(existing?.startDate ?? dayInput());
  const [end, setEnd] = useState(existing?.endDate ?? '');
  const [value, setValue] = useState(existing?.value ?? '');
  const [reminder, setReminder] = useState(String(existing?.renewalReminderDays ?? 30));
  const [notes, setNotes] = useState(existing?.notes ?? '');
  const [items, setItems] = useState<Product[]>([]);
  const [picker, setPicker] = useState<Product | null>(null);
  const [error, setError] = useState('');
  const [overlap, setOverlap] = useState('');
  const body = () => ({
    ...(existing ? {} : { customer: customer!.id }),
    contract_type: type,
    start_date: start,
    end_date: end,
    value: value === '' ? null : value,
    notes,
    renewal_reminder_days: Number(reminder),
    ...(items.length || !existing ? { products: items.map((item) => item.id) } : {}),
  });
  const save = useMutation({
    mutationFn: (allowOverlap: boolean) => {
      const payload = { ...body(), ...(allowOverlap ? { allow_overlap: true } : {}) };
      return existing ? contracts.update(existing.id, payload, existing.updatedAt) : contracts.create(payload);
    },
    onSuccess: (row) => {
      void qc.invalidateQueries({ queryKey: ['contracts'] });
      setError(''); setOverlap('');
      onClose();
      if (!existing) navigate(listPath(`/${row.id}`));
    },
    onError: (err) => {
      const conflict = conflictInfo(err);
      if (conflict?.code === 'overlap') setOverlap(conflict.message);
      else setError(getErrorMessage(err));
    },
  });
  const valid = (existing || customer) && end && start && end >= start && /^\d+$/.test(reminder) && Number(reminder) <= 365 && (value === '' || Number(value) >= 0);
  return (
    <>
      <CreateDialog
        open={open && !overlap}
        onClose={onClose}
        title={existing ? t('care.contracts.editTitle', { number: existing.number }) : t('growth.addContract')}
        submitLabel={existing ? t('growth.save') : t('growth.addContract')}
        submitDisabled={!valid || save.isPending}
        dirty={Boolean(customer || notes || value)}
        onSubmit={() => save.mutate(false)}
      >
        {existing ? null : <CustomerField value={customer} onChange={setCustomer} />}
        <TextField select size="small" label={t('growth.type')} value={type} onChange={(e) => setType(e.target.value)}>
          {TYPES.map((item) => <MenuItem key={item} value={item}>{enumLabel('contractType', item)}</MenuItem>)}
        </TextField>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
          <TextField fullWidth size="small" type="date" required label={t('growth.startDate')} value={start} onChange={(e) => setStart(e.target.value)} InputLabelProps={{ shrink: true }} />
          <TextField fullWidth size="small" type="date" required label={t('growth.endDate')} value={end} onChange={(e) => setEnd(e.target.value)} InputLabelProps={{ shrink: true }} error={Boolean(end && end < start)} helperText={end && end < start ? t('care.contracts.endBeforeStart') : undefined} />
        </Stack>
        <TextField size="small" label={t('growth.value')} value={value ?? ''} onChange={(e) => setValue(e.target.value)} helperText={t('growth.valueCopiesToSchedule')} inputProps={{ inputMode: 'decimal' }} />
        <TextField size="small" label={t('growth.reminderDays')} value={reminder} onChange={(e) => setReminder(e.target.value)} helperText={t('care.contracts.reminderHelp')} error={!/^\d+$/.test(reminder) || Number(reminder) > 365} />
        <Box>
          <Typography variant="caption" color="text.secondary">
            {existing ? t('care.contracts.productsKept', { names: existing.productNames.join(', ') || '—' }) : t('care.contracts.productsHelp')}
          </Typography>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 0.5 }}>
            <CatalogPicker kind="ANY" label={t('care.contracts.addProduct')} value={picker} onChange={(next) => {
              if (next && !items.some((item) => item.id === next.id)) setItems((prev) => [...prev, next]);
              setPicker(null);
            }} />
          </Stack>
          <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mt: 0.5 }}>
            {items.map((item) => (
              <Chip key={item.id} size="small" label={item.name} onDelete={() => setItems((prev) => prev.filter((row) => row.id !== item.id))} />
            ))}
          </Stack>
        </Box>
        <TextField size="small" multiline minRows={2} label={t('growth.notes')} value={notes} onChange={(e) => setNotes(e.target.value)} />
        {error ? <Typography role="alert" color="error" variant="body2">{error}</Typography> : null}
      </CreateDialog>
      <ConfirmDialog
        open={open && Boolean(overlap)}
        title={t('care.contracts.overlapTitle')}
        body={overlap}
        confirmLabel={t('care.contracts.saveAnyway')}
        confirmColor="warning"
        confirming={save.isPending}
        onClose={() => setOverlap('')}
        onConfirm={() => { setOverlap(''); save.mutate(true); }}
      />
    </>
  );
}

export function ContractDetail({
  id,
  canChange,
  isOwner,
  backTo,
}: {
  id: number;
  canChange: boolean;
  isOwner: boolean;
  backTo: { pathname: string; search: string };
}) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const feedback = useNotice();
  const [editOpen, setEditOpen] = useState(false);
  const [renewOpen, setRenewOpen] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [billingOpen, setBillingOpen] = useState(false);
  const [cadence, setCadence] = useState<string>('MONTHLY');
  const [renewEnd, setRenewEnd] = useState('');
  const [renewValue, setRenewValue] = useState('');
  const [renewNote, setRenewNote] = useState('');
  const timeline = useQuery({ queryKey: ['contracts', 'timeline', id], queryFn: () => contracts.timeline(id) });
  const row = timeline.data?.contract;
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['contracts'] });
    void qc.invalidateQueries({ queryKey: ['care-activity', 'Contract', id] });
    void qc.invalidateQueries({ queryKey: ['care-links'] });
  };
  const run = useMutation({
    mutationFn: async (job: { work: () => Promise<unknown>; done: string }) => {
      await job.work();
      return job.done;
    },
    onSuccess: (done) => { feedback.ok(done); refresh(); },
    onError: (err) => feedback.fail(err),
  });
  if (timeline.isLoading) return <ListSkeleton rows={4} />;
  if (timeline.isError || !row) {
    return <ErrorState message={getErrorMessage(timeline.error)} error={timeline.error} onRetry={() => void timeline.refetch()} />;
  }
  const cancelled = row.status === 'CANCELLED';
  const ended = row.status === 'EXPIRED';
  const schedule = row.schedule;
  const events = timeline.data?.events ?? [];
  const renewals = timeline.data?.renewals ?? [];
  const startRenew = () => {
    const end = new Date(`${row.endDate}T00:00:00`);
    end.setFullYear(end.getFullYear() + 1);
    setRenewEnd(dayInput(0, end));
    setRenewValue(row.value ?? '');
    setRenewNote('');
    setRenewOpen(true);
  };
  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Stack spacing={2}>
        <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={1}>
          <Box>
            <Typography variant="h6" component="h2">{row.number}</Typography>
            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
              <StatusPill group="contractStatus" value={row.status} />
              <Typography variant="body2">{enumLabel('contractType', row.contractType)}</Typography>
              <Typography variant="body2" color="text.secondary">{expiryText(row)}</Typography>
            </Stack>
          </Box>
          <Button size="small" component={RouterLink} to={`/contracts/${id}/certificate`} target="_blank">{t('care.contracts.printCertificate')}</Button>
        </Stack>
        {feedback.node}
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} flexWrap="wrap" useFlexGap>
          <Field label={t('growth.customer')}><CustomerLink id={row.customer} name={row.customerName} /></Field>
          <Field label={termLabel(row.contractType)}>{formatDay(row.startDate)} – {formatDay(row.endDate)}</Field>
          <Field label={t('growth.value')}>{row.value ? formatMoney(row.value) : ''}</Field>
          <Field label={t('growth.reminderDays')}>{row.renewalReminderDays}</Field>
        </Stack>
        <Field label={t('care.contracts.col.products')}>{row.productNames.join(', ')}</Field>
        {row.notes ? <Field label={t('growth.notes')}><Box sx={{ whiteSpace: 'pre-wrap' }}>{row.notes}</Box></Field> : null}
        {canChange ? (
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            {!cancelled ? <Button size="small" onClick={() => setEditOpen(true)}>{t('common.edit')}</Button> : null}
            {!cancelled ? <Button size="small" variant={ended || row.status === 'EXPIRING' ? 'contained' : 'outlined'} onClick={startRenew}>{t('care.contracts.renew')}</Button> : null}
            {!cancelled ? (
              <Button size="small" color="error" onClick={() => setCancelOpen(true)}>{t('growth.cancel')}</Button>
            ) : (
              <Button size="small" onClick={() => run.mutate({ work: () => contracts.update(id, { status: 'ACTIVE' }, row.updatedAt), done: t('care.contracts.uncancelled') })}>
                {t('growth.uncancel')}
              </Button>
            )}
            {isOwner ? <Button size="small" color="error" onClick={() => setDeleteOpen(true)}>{t('common.delete')}</Button> : null}
          </Stack>
        ) : null}
        <Divider />
        <Box component="section" aria-label={t('care.contracts.billing')}>
          <Typography variant="subtitle2" component="h3">{t('care.contracts.billing')}</Typography>
          {schedule ? (
            <Stack spacing={0.5}>
              <Typography variant="body2">
                {enumLabel('billingCadence', schedule.cadence)} · {schedule.isActive ? t('care.contracts.billingActive', { when: formatStamp(schedule.nextRunAt) }) : (schedule.pausedReason === 'CONTRACT_ENDED' ? t('care.contracts.billingEnded') : t('care.contracts.billingPaused'))}
              </Typography>
              {isOwner && !cancelled ? (
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                  {schedule.isActive ? (
                    <Button size="small" onClick={() => run.mutate({ work: () => contracts.pauseSchedule(id), done: t('care.contracts.billingPausedDone') })}>{t('care.contracts.pauseBilling')}</Button>
                  ) : (
                    <Button size="small" onClick={() => run.mutate({ work: () => contracts.resumeSchedule(id), done: t('care.contracts.billingResumedDone') })}>{t('care.contracts.resumeBilling')}</Button>
                  )}
                  <Button size="small" onClick={() => run.mutate({ work: () => contracts.syncSchedule(id), done: t('care.contracts.billingSynced') })}>{t('care.contracts.syncBilling')}</Button>
                </Stack>
              ) : null}
            </Stack>
          ) : (
            <Stack spacing={0.5}>
              <Typography variant="body2" color="text.secondary">{t('care.contracts.noBilling')}</Typography>
              {isOwner && !cancelled ? (
                <Button size="small" variant="outlined" sx={{ alignSelf: 'flex-start' }} onClick={() => setBillingOpen(true)}>{t('care.contracts.startBilling')}</Button>
              ) : !isOwner ? (
                <Typography variant="caption" color="text.secondary">{t('care.contracts.ownerOnlyBilling')}</Typography>
              ) : null}
            </Stack>
          )}
        </Box>
        {renewals.length ? (
          <Box component="section" aria-label={t('care.contracts.renewals')}>
            <Typography variant="subtitle2" component="h3">{t('care.contracts.renewals')}</Typography>
            {renewals.map((renewal) => (
              <Typography key={renewal.id} variant="body2">
                {formatDay(renewal.previousEndDate)} → {formatDay(renewal.newEndDate)}
                {renewal.newValue ? ` · ${formatMoney(renewal.newValue)}` : ''}{renewal.note ? ` · ${renewal.note}` : ''}
              </Typography>
            ))}
          </Box>
        ) : null}
        <Divider />
        <ServiceEvents contractId={id} customerId={row.customer} events={events} canChange={canChange && !cancelled} notice={feedback} onChanged={() => { void timeline.refetch(); refresh(); }} />
        <Divider />
        <AttachmentPanel
          queryKey={['contracts', 'files', id]}
          list={() => contracts.attachments.list(id)}
          upload={(file) => contracts.attachments.upload(id, file)}
          remove={(attachment) => contracts.attachments.remove(id, attachment)}
          canEdit={canChange}
          lockedReason={cancelled || ended ? t('care.contracts.lockedFiles') : undefined}
        />
        <Divider />
        <LinkedRecords entity="contract" id={id} />
        <ActivityTimeline entity="Contract" id={id} fetcher={() => contracts.activity(id)} />
      </Stack>

      <ContractFormDialog open={editOpen} onClose={() => setEditOpen(false)} existing={row} />

      <CreateDialog
        open={renewOpen}
        onClose={() => setRenewOpen(false)}
        title={t('care.contracts.renewTitle', { number: row.number })}
        submitLabel={t('care.contracts.renew')}
        submitDisabled={!renewEnd || renewEnd <= row.endDate || run.isPending}
        onSubmit={() => {
          setRenewOpen(false);
          run.mutate({
            work: () => contracts.renew(id, { new_end_date: renewEnd, value: renewValue || undefined, note: renewNote }),
            done: t('care.contracts.renewed'),
          });
        }}
      >
        <Typography variant="body2">{t('care.contracts.renewHelp', { end: formatDay(row.endDate) })}</Typography>
        <TextField size="small" type="date" required label={t('care.contracts.newEnd')} value={renewEnd} onChange={(e) => setRenewEnd(e.target.value)} InputLabelProps={{ shrink: true }} error={Boolean(renewEnd && renewEnd <= row.endDate)} helperText={renewEnd && renewEnd <= row.endDate ? t('care.contracts.mustExtend') : undefined} />
        <TextField size="small" label={t('growth.value')} value={renewValue} onChange={(e) => setRenewValue(e.target.value)} inputProps={{ inputMode: 'decimal' }} />
        <TextField size="small" label={t('growth.notes')} value={renewNote} onChange={(e) => setRenewNote(e.target.value)} />
      </CreateDialog>

      <CreateDialog
        open={billingOpen}
        onClose={() => setBillingOpen(false)}
        title={t('care.contracts.startBilling')}
        submitLabel={t('care.contracts.startBilling')}
        submitDisabled={!row.value || run.isPending}
        onSubmit={() => {
          setBillingOpen(false);
          run.mutate({
            work: async () => {
              const made = await contracts.createSchedule(id, cadence, `contract-${id}-${cadence}`);
              if (made.invoice) navigate(`/sales/history/${made.invoice}`);
            },
            done: t('care.contracts.billingStarted'),
          });
        }}
      >
        <Typography variant="body2">{row.value ? t('care.contracts.startBillingHelp', { value: formatMoney(row.value) }) : t('care.contracts.needsValue')}</Typography>
        <TextField select size="small" label={t('care.contracts.cadence')} value={cadence} onChange={(e) => setCadence(e.target.value)}>
          {CADENCES.map((item) => <MenuItem key={item} value={item}>{enumLabel('billingCadence', item)}</MenuItem>)}
        </TextField>
      </CreateDialog>

      <ConfirmDialog
        open={cancelOpen}
        title={t('cog.confirmCancelContract', { name: row.number })}
        body={t('care.contracts.cancelBody')}
        requireTyped={row.number}
        confirmColor="error"
        onClose={() => setCancelOpen(false)}
        onConfirm={() => {
          setCancelOpen(false);
          run.mutate({ work: () => contracts.update(id, { status: 'CANCELLED' }, row.updatedAt), done: t('care.contracts.cancelled') });
        }}
      />
      <ConfirmDialog
        open={deleteOpen}
        title={t('care.contracts.deleteTitle', { number: row.number })}
        body={t('care.contracts.deleteBody')}
        confirmLabel={t('common.delete')}
        confirmColor="error"
        onClose={() => setDeleteOpen(false)}
        onConfirm={() => {
          setDeleteOpen(false);
          run.mutate({ work: async () => { await contracts.remove(id); navigate(backTo); }, done: t('care.contracts.deleted') });
        }}
      />
    </Paper>
  );
}

function ServiceEvents({
  contractId,
  customerId,
  events,
  canChange,
  notice,
  onChanged,
}: {
  contractId: number;
  customerId: number;
  events: ServiceEvent[];
  canChange: boolean;
  notice: ReturnType<typeof useNotice>;
  onChanged: () => void;
}) {
  const [notes, setNotes] = useState('');
  const [when, setWhen] = useState(toLocalInput(new Date().toISOString()));
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [editing, setEditing] = useState<{ id: number; notes: string } | null>(null);
  const add = useMutation({
    mutationFn: () => contracts.addEvent(contractId, { notes: notes.trim(), ticket: ticket?.id, occurred_at: fromLocalInput(when) }),
    onSuccess: () => { setNotes(''); setTicket(null); notice.ok(t('care.contracts.eventAdded')); onChanged(); },
    onError: (err) => notice.fail(err),
  });
  const edit = useMutation({
    mutationFn: () => contracts.editEvent(contractId, editing!.id, editing!.notes.trim()),
    onSuccess: () => { setEditing(null); notice.ok(t('care.tickets.saved')); onChanged(); },
    onError: (err) => notice.fail(err),
  });
  const remove = useMutation({
    mutationFn: (event: number) => contracts.removeEvent(contractId, event),
    onSuccess: () => { notice.ok(t('care.contracts.eventRemoved')); onChanged(); },
    onError: (err) => notice.fail(err),
  });
  return (
    <Box component="section" aria-label={t('growth.timeline')}>
      <Typography variant="subtitle2" component="h3">{t('growth.timeline')}</Typography>
      {events.length === 0 ? <Typography variant="body2" color="text.secondary">{t('care.contracts.noEvents')}</Typography> : null}
      <Stack spacing={1} component="ul" style={{ listStyle: 'none', padding: 0, margin: '8px 0' }}>
        {events.map((event) => {
          const fresh = wallClockMs() - new Date(event.createdAt).getTime() < DAY_MS;
          return (
            <li key={event.id}>
              <Typography variant="caption" color="text.secondary">
                {formatStamp(event.occurredAt)}{event.authorName ? ` · ${event.authorName}` : ''}
                {event.ticket ? <> · <Link component={RouterLink} to={`/support/tickets/${event.ticket}`}>{event.ticketNumber}</Link></> : null}
              </Typography>
              {editing?.id === event.id ? (
                <Stack direction="row" spacing={1}>
                  <TextField size="small" fullWidth value={editing.notes} onChange={(e) => setEditing({ id: event.id, notes: e.target.value })} />
                  <Button size="small" disabled={!editing.notes.trim() || edit.isPending} onClick={() => edit.mutate()}>{t('growth.save')}</Button>
                  <Button size="small" onClick={() => setEditing(null)}>{t('common.cancel')}</Button>
                </Stack>
              ) : (
                <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>{event.notes}</Typography>
              )}
              {canChange && fresh && editing?.id !== event.id ? (
                <Stack direction="row" spacing={1}>
                  <Button size="small" onClick={() => setEditing({ id: event.id, notes: event.notes })}>{t('common.edit')}</Button>
                  <Button size="small" color="error" onClick={() => remove.mutate(event.id)}>{t('growth.remove')}</Button>
                </Stack>
              ) : null}
            </li>
          );
        })}
      </Stack>
      {canChange ? (
        <Stack spacing={1}>
          <TextField size="small" multiline minRows={2} required label={t('care.contracts.eventNotes')} value={notes} onChange={(e) => setNotes(e.target.value)} />
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
            <TextField size="small" type="datetime-local" label={t('care.contracts.eventWhen')} value={when} onChange={(e) => setWhen(e.target.value)} InputLabelProps={{ shrink: true }} />
            <TicketPicker customerId={customerId} value={ticket} onChange={setTicket} label={t('care.contracts.eventTicket')} />
          </Stack>
          <Button size="small" variant="outlined" sx={{ alignSelf: 'flex-start' }} disabled={!notes.trim() || add.isPending} onClick={() => add.mutate()}>
            {t('growth.serviceEvent')}
          </Button>
        </Stack>
      ) : null}
    </Box>
  );
}
