import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Divider from '@mui/material/Divider';
import LinearProgress from '@mui/material/LinearProgress';
import Link from '@mui/material/Link';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { projects, type Contract, type Milestone, type Project } from '@/api/care';
import { useAuth } from '@/auth/AuthContext';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { CreateDialog } from '@/components/CreateDialog';
import { EmptyState, ErrorState, ListSkeleton } from '@/components/PageState';
import { isProjectsEnabled } from '@/config/features';
import { t } from '@/i18n';
import { daysFromToday, formatDay } from '@/care/format';
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
  VisuallyHidden,
} from '@/care/kit';
import { canChangeCare, useListPath, useNotice, useUrlFilters } from '@/care/hooks';
import { CatalogPicker, ContractPicker } from '@/care/pickers';
import { enumLabel } from '@/utils/enumLabels';
import { formatMoney } from '@/utils/money';
import { CustomerField } from '@/pages/growth/widgets';
import { PageShell } from '@/pages/phase/phaseShared';
import type { Customer, Product } from '@/types/domain';

const PAGE_SIZE = 20;
const BASE = '/projects';
const STATUSES = ['OPEN', 'CLOSED', 'CANCELLED'] as const;

export function ProjectsPage() {
  if (!isProjectsEnabled()) {
    return <PageShell title={t('nav.projects')}><Typography>{t('erp.moduleDisabled')}</Typography></PageShell>;
  }
  return <ProjectsWorkspace />;
}

function ProjectsWorkspace() {
  const { id } = useParams();
  const selectedId = id ? Number(id) : null;
  const { user } = useAuth();
  const canChange = canChangeCare(user);
  const listPath = useListPath(BASE);
  const { values, set } = useUrlFilters({ q: '', status: '', page: '1' });
  const [createOpen, setCreateOpen] = useState(false);
  const page = Math.max(1, Number(values.page) || 1);
  const list = useQuery({
    queryKey: ['projects', 'list', values, page],
    queryFn: () => projects.list({ q: values.q || undefined, status: values.status || undefined, page, pageSize: PAGE_SIZE }),
  });
  const rows = list.data?.results ?? [];
  const columns: CareColumn<Project>[] = [
    { key: 'number', header: t('care.projects.col.project'), primary: true, render: (row) => `${row.number} · ${row.name}` },
    { key: 'customer', header: t('growth.customer'), render: (row) => row.customerName },
    { key: 'status', header: t('growth.status'), render: (row) => <StatusPill group="projectStatus" value={row.status} /> },
    {
      key: 'progress', header: t('care.projects.col.progress'),
      render: (row) => (
        <Box sx={{ minWidth: 110 }}>
          <LinearProgress variant="determinate" value={row.percentComplete} aria-label={t('care.projects.progressOf', { number: row.number })} />
          <Typography variant="caption">{row.percentComplete}% · {formatMoney(row.invoicedTotal)} / {formatMoney(row.plannedTotal)}</Typography>
        </Box>
      ),
    },
    { key: 'ends', header: t('growth.endDate'), render: (row) => formatDay(row.endDate) },
  ];
  const listNode = (
    <Stack spacing={1.5}>
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
        <SearchField value={values.q} onChange={(q) => set({ q })} />
        <TextField select size="small" label={t('growth.status')} value={values.status} onChange={(e) => set({ status: e.target.value })} sx={{ minWidth: 160 }}>
          <MenuItem value="">{t('growth.all')}</MenuItem>
          {STATUSES.map((value) => <MenuItem key={value} value={value}>{enumLabel('projectStatus', value)}</MenuItem>)}
        </TextField>
      </Stack>
      {list.isLoading ? <ListSkeleton rows={5} /> : null}
      {list.isError ? <ErrorState message={getErrorMessage(list.error)} error={list.error} onRetry={() => void list.refetch()} /> : null}
      {!list.isLoading && !list.isError && rows.length === 0 ? (
        <EmptyState
          description={t('cog.emptyProjects')}
          action={canChange ? <Button variant="contained" onClick={() => setCreateOpen(true)}>{t('growth.startProject')}</Button> : undefined}
        />
      ) : null}
      {rows.length > 0 ? (
        <CareTable
          caption={t('nav.projects')}
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
        title={t('nav.projects')}
        subtitle={t('growth.projectMilestone')}
        actions={canChange ? <Button variant="contained" onClick={() => setCreateOpen(true)}>{t('growth.startProject')}</Button> : undefined}
      />
      <MasterDetail
        list={listNode}
        detail={selectedId ? <ProjectDetail key={selectedId} id={selectedId} canChange={canChange} isOwner={user?.role === 'OWNER'} /> : null}
        hasSelection={selectedId != null}
        backTo={listPath()}
        detailLabel={t('care.projects.detail')}
      />
      <ProjectFormDialog open={createOpen} onClose={() => setCreateOpen(false)} />
    </Stack>
  );
}

function ProjectFormDialog({ open, onClose, existing }: { open: boolean; onClose: () => void; existing?: Project }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const listPath = useListPath(BASE);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [name, setName] = useState(existing?.name ?? '');
  const [notes, setNotes] = useState(existing?.notes ?? '');
  const [start, setStart] = useState(existing?.startDate ?? '');
  const [end, setEnd] = useState(existing?.endDate ?? '');
  const [value, setValue] = useState(existing?.contractValue ?? '');
  const [contract, setContract] = useState<Contract | null>(existing?.contract ? ({ id: existing.contract, number: existing.contractNumber } as Contract) : null);
  const [error, setError] = useState('');
  const save = useMutation({
    mutationFn: () => {
      const body = {
        name: name.trim(), notes, start_date: start || null, end_date: end || null,
        contract_value: value === '' ? null : value, contract: contract?.id ?? null,
      };
      return existing
        ? projects.update(existing.id, body, existing.updatedAt)
        : projects.create({ ...body, customer: customer!.id }, `project-${customer!.id}-${name.trim()}`);
    },
    onSuccess: (row) => {
      void qc.invalidateQueries({ queryKey: ['projects'] });
      setError('');
      if (!existing) { setName(''); setNotes(''); }
      onClose();
      if (!existing) navigate(listPath(`/${row.id}`));
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const badDates = Boolean(start && end && end < start);
  return (
    <CreateDialog
      open={open}
      onClose={onClose}
      title={existing ? t('care.projects.editTitle', { number: existing.number }) : t('growth.startProject')}
      submitLabel={existing ? t('growth.save') : t('growth.startProject')}
      submitDisabled={(!existing && !customer) || !name.trim() || badDates || save.isPending}
      dirty={Boolean(name.trim() || customer)}
      onSubmit={() => save.mutate()}
    >
      {existing ? null : <CustomerField value={customer} onChange={(next) => { setCustomer(next); setContract(null); }} />}
      <TextField size="small" required label={t('growth.name')} value={name} onChange={(e) => setName(e.target.value)} />
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
        <TextField fullWidth size="small" type="date" label={t('growth.startDate')} value={start ?? ''} onChange={(e) => setStart(e.target.value)} InputLabelProps={{ shrink: true }} />
        <TextField fullWidth size="small" type="date" label={t('growth.endDate')} value={end ?? ''} onChange={(e) => setEnd(e.target.value)} InputLabelProps={{ shrink: true }} error={badDates} helperText={badDates ? t('care.contracts.endBeforeStart') : undefined} />
      </Stack>
      <TextField size="small" label={t('care.projects.contractValue')} value={value ?? ''} onChange={(e) => setValue(e.target.value)} helperText={t('care.projects.contractValueHelp')} inputProps={{ inputMode: 'decimal' }} />
      <ContractPicker customerId={existing ? existing.customer : customer?.id ?? null} value={contract} onChange={setContract} />
      <TextField size="small" multiline minRows={2} label={t('growth.notes')} value={notes} onChange={(e) => setNotes(e.target.value)} />
      {error ? <Typography role="alert" color="error" variant="body2">{error}</Typography> : null}
    </CreateDialog>
  );
}

type MilestoneDialog = null | { mode: 'add' } | { mode: 'edit'; milestone: Milestone };

export function ProjectDetail({ id, canChange, isOwner }: { id: number; canChange: boolean; isOwner: boolean }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const feedback = useNotice();
  const [editOpen, setEditOpen] = useState(false);
  const [milestoneDialog, setMilestoneDialog] = useState<MilestoneDialog>(null);
  const [closeOpen, setCloseOpen] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [removing, setRemoving] = useState<Milestone | null>(null);
  const detail = useQuery({ queryKey: ['projects', 'detail', id], queryFn: () => projects.get(id) });
  const project = detail.data;
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['projects'] });
    void qc.invalidateQueries({ queryKey: ['care-activity', 'Project', id] });
    void qc.invalidateQueries({ queryKey: ['care-links'] });
  };
  const run = useMutation({
    mutationFn: async (work: { do: () => Promise<unknown>; done: string }) => {
      const result = await work.do();
      return { done: work.done, result };
    },
    onSuccess: ({ done, result }) => {
      const warning = (result as Project | undefined)?.warning;
      if (warning) feedback.ok(`${done} ${warning}`);
      else feedback.ok(done);
      refresh();
    },
    onError: (err) => feedback.fail(err),
  });
  if (detail.isLoading) return <ListSkeleton rows={4} />;
  if (detail.isError || !project) {
    return <ErrorState message={getErrorMessage(detail.error)} error={detail.error} onRetry={() => void detail.refetch()} />;
  }
  const open = project.status === 'OPEN';
  const milestones = project.milestones ?? [];
  const moveUp = (index: number, delta: number) => {
    const order = milestones.map((m) => m.id);
    const target = index + delta;
    [order[index], order[target]] = [order[target], order[index]];
    run.mutate({ do: () => projects.reorder(id, order), done: t('care.projects.reordered') });
  };
  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Stack spacing={2}>
        <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={1}>
          <Box>
            <Typography variant="h6" component="h2">{project.number} · {project.name}</Typography>
            <StatusPill group="projectStatus" value={project.status} />
          </Box>
          {canChange && open ? <Button size="small" onClick={() => setEditOpen(true)}>{t('common.edit')}</Button> : null}
        </Stack>
        {feedback.node}
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} flexWrap="wrap" useFlexGap>
          <Field label={t('growth.customer')}><CustomerLink id={project.customer} name={project.customerName} /></Field>
          <Field label={t('growth.startDate')}>{formatDay(project.startDate)}</Field>
          <Field label={t('growth.endDate')}>{formatDay(project.endDate)}</Field>
          {project.contract ? <Field label={t('care.pick.contract')}><Link component={RouterLink} to={`/contracts/${project.contract}`}>{project.contractNumber}</Link></Field> : null}
        </Stack>
        {project.notes ? <Field label={t('growth.notes')}><Box sx={{ whiteSpace: 'pre-wrap' }}>{project.notes}</Box></Field> : null}

        <Box component="section" aria-label={t('care.projects.money')}>
          <LinearProgress variant="determinate" value={project.percentComplete} aria-label={t('care.projects.progressOf', { number: project.number })} sx={{ height: 8, borderRadius: 4 }} />
          <Stack direction="row" spacing={3} flexWrap="wrap" useFlexGap sx={{ mt: 1 }}>
            <Field label={t('care.projects.planned')}>{formatMoney(project.plannedTotal)}</Field>
            <Field label={t('care.projects.invoiced')}>{formatMoney(project.invoicedTotal)}</Field>
            <Field label={t('care.projects.remaining')}>{formatMoney(project.remainingTotal)}</Field>
            <Field label={t('care.projects.percent')}>{project.percentComplete}%</Field>
            {project.contractValue ? <Field label={t('care.projects.contractValue')}>{formatMoney(project.contractValue)}</Field> : null}
          </Stack>
          <Typography variant="caption" color="text.secondary">{t('care.projects.exGst')}</Typography>
          {project.overBudget ? <Alert severity="warning" sx={{ mt: 1 }}>{t('care.projects.overBudget')}</Alert> : null}
        </Box>

        <Box component="section" aria-label={t('growth.milestone')}>
          <Stack direction="row" justifyContent="space-between" alignItems="center">
            <Typography variant="subtitle2" component="h3">{t('growth.milestone')}</Typography>
            {canChange && open ? <Button size="small" variant="outlined" onClick={() => setMilestoneDialog({ mode: 'add' })}>{t('growth.addMilestone')}</Button> : null}
          </Stack>
          {milestones.length === 0 ? <Typography variant="body2" color="text.secondary">{t('care.projects.noMilestones')}</Typography> : (
            <Box sx={{ overflowX: 'auto' }}>
              <Table size="small" aria-label={t('growth.milestone')}>
                <TableHead>
                  <TableRow>
                    <TableCell scope="col">#</TableCell>
                    <TableCell scope="col">{t('growth.milestone')}</TableCell>
                    <TableCell scope="col">{t('growth.targetDate')}</TableCell>
                    <TableCell scope="col" align="right">{t('growth.amount')}</TableCell>
                    <TableCell scope="col">{t('growth.status')}</TableCell>
                    <TableCell scope="col"><VisuallyHidden>{t('care.common.actions')}</VisuallyHidden></TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {milestones.map((milestone, index) => {
                    const days = daysFromToday(milestone.targetCompletionDate);
                    const late = days != null && days < 0 && milestone.status !== 'INVOICED';
                    return (
                      <TableRow key={milestone.id}>
                        <TableCell>{index + 1}</TableCell>
                        <TableCell>{milestone.name}<Typography variant="caption" display="block" color="text.secondary">{milestone.serviceProductName}</Typography></TableCell>
                        <TableCell>
                          {formatDay(milestone.targetCompletionDate)}
                          {late ? <Chip size="small" color="error" label={t('care.projects.overdue', { days: Math.abs(days) })} sx={{ ml: 0.5 }} /> : null}
                        </TableCell>
                        <TableCell align="right">
                          {formatMoney(milestone.amount)}
                          <Typography variant="caption" display="block" color="text.secondary">{t('care.projects.inclGst', { amount: formatMoney(milestone.amountInclGst) })}</Typography>
                        </TableCell>
                        <TableCell><StatusPill group="milestoneStatus" value={milestone.status} /></TableCell>
                        <TableCell align="right">
                          <MilestoneActions
                            milestone={milestone}
                            index={index}
                            count={milestones.length}
                            canChange={canChange && open}
                            busy={run.isPending}
                            onReady={() => run.mutate({ do: () => projects.ready(id, milestone.id), done: t('care.projects.markedReady') })}
                            onUnready={() => run.mutate({ do: () => projects.unready(id, milestone.id), done: t('care.projects.backToPlanned') })}
                            onInvoice={() => run.mutate({
                              do: async () => {
                                const next = await projects.invoice(id, milestone.id, `milestone-${milestone.id}`);
                                const made = next.milestones?.find((row) => row.id === milestone.id)?.salesInvoice;
                                if (made) navigate(`/sales/history/${made}`);
                                return next;
                              },
                              done: t('care.projects.invoiceDrafted'),
                            })}
                            onEdit={() => setMilestoneDialog({ mode: 'edit', milestone })}
                            onDelete={() => setRemoving(milestone)}
                            onMove={moveUp}
                          />
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </Box>
          )}
        </Box>

        {canChange && open ? (
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <Button size="small" variant="contained" onClick={() => setCloseOpen(true)}>{t('care.projects.close')}</Button>
            {isOwner ? <Button size="small" color="error" onClick={() => setCancelOpen(true)}>{t('care.projects.cancel')}</Button> : null}
          </Stack>
        ) : null}
        <Divider />
        <LinkedRecords entity="project" id={id} />
        <ActivityTimeline entity="Project" id={id} fetcher={() => projects.activity(id)} />
      </Stack>

      <ProjectFormDialog open={editOpen} onClose={() => setEditOpen(false)} existing={project} />
      {milestoneDialog ? (
        <MilestoneFormDialog
          projectId={id}
          existing={milestoneDialog.mode === 'edit' ? milestoneDialog.milestone : undefined}
          nextSequence={milestones.length + 1}
          onClose={() => setMilestoneDialog(null)}
          onSaved={(text) => { feedback.ok(text); refresh(); }}
        />
      ) : null}
      <ConfirmDialog
        open={closeOpen}
        title={t('care.projects.close')}
        body={t('growth.closeProjectConfirm')}
        confirmLabel={t('common.confirm')}
        onClose={() => setCloseOpen(false)}
        onConfirm={() => { setCloseOpen(false); run.mutate({ do: () => projects.close(id), done: t('care.projects.closed') }); }}
      />
      <ConfirmDialog
        open={cancelOpen}
        title={t('care.projects.cancelTitle', { number: project.number })}
        body={t('care.projects.cancelBody')}
        confirmLabel={t('care.projects.cancel')}
        confirmColor="error"
        requireReason={{ label: t('care.projects.cancelReason'), maxLength: 200 }}
        onClose={() => setCancelOpen(false)}
        onConfirm={(reason) => { setCancelOpen(false); run.mutate({ do: () => projects.cancel(id, reason), done: t('care.projects.cancelled') }); }}
      />
      <ConfirmDialog
        open={removing != null}
        title={t('growth.deleteMilestone')}
        body={removing ? removing.name : ''}
        confirmLabel={t('common.delete')}
        confirmColor="error"
        onClose={() => setRemoving(null)}
        onConfirm={() => {
          const target = removing;
          setRemoving(null);
          if (target) run.mutate({ do: () => projects.deleteMilestone(id, target.id), done: t('care.projects.milestoneRemoved') });
        }}
      />
    </Paper>
  );
}

function MilestoneActions({
  milestone,
  index,
  count,
  canChange,
  busy,
  onReady,
  onUnready,
  onInvoice,
  onEdit,
  onDelete,
  onMove,
}: {
  milestone: Milestone;
  index: number;
  count: number;
  canChange: boolean;
  busy: boolean;
  onReady: () => void;
  onUnready: () => void;
  onInvoice: () => void;
  onEdit: () => void;
  onDelete: () => void;
  onMove: (index: number, delta: number) => void;
}) {
  const name = milestone.name;
  return (
    <Stack direction="row" spacing={0.5} justifyContent="flex-end" flexWrap="wrap" useFlexGap>
      {milestone.salesInvoice ? (
        <Button size="small" component={RouterLink} to={`/sales/history/${milestone.salesInvoice}`}>
          {milestone.status === 'INVOICED' ? t('growth.viewInvoice') : t('growth.openInvoice')}
        </Button>
      ) : null}
      {canChange && milestone.status === 'PLANNED' ? (
        <>
          <Button size="small" disabled={busy} onClick={onReady} aria-label={t('care.projects.readyNamed', { name })}>{t('growth.ready')}</Button>
          <Button size="small" onClick={onEdit} aria-label={t('care.projects.editNamed', { name })}>{t('growth.editMilestone')}</Button>
        </>
      ) : null}
      {canChange && milestone.status === 'READY' && !milestone.salesInvoice ? (
        <>
          <Button size="small" variant="contained" disabled={busy} onClick={onInvoice} aria-label={t('care.projects.invoiceNamed', { name })}>{t('growth.invoice')}</Button>
          <Button size="small" disabled={busy} onClick={onUnready} aria-label={t('care.projects.unreadyNamed', { name })}>{t('care.projects.backToPlannedShort')}</Button>
        </>
      ) : null}
      {canChange && milestone.status !== 'INVOICED' && !milestone.salesInvoice ? (
        <Button size="small" color="error" onClick={onDelete} aria-label={t('care.projects.deleteNamed', { name })}>{t('common.delete')}</Button>
      ) : null}
      {canChange && count > 1 ? (
        <>
          <Button size="small" disabled={index === 0 || busy} onClick={() => onMove(index, -1)} aria-label={t('care.projects.moveUp', { name })}>↑</Button>
          <Button size="small" disabled={index === count - 1 || busy} onClick={() => onMove(index, 1)} aria-label={t('care.projects.moveDown', { name })}>↓</Button>
        </>
      ) : null}
    </Stack>
  );
}

function MilestoneFormDialog({
  projectId,
  existing,
  nextSequence,
  onClose,
  onSaved,
}: {
  projectId: number;
  existing?: Milestone;
  nextSequence: number;
  onClose: () => void;
  onSaved: (text: string) => void;
}) {
  const [name, setName] = useState(existing?.name ?? '');
  const [amount, setAmount] = useState(existing?.amount ?? '');
  const [target, setTarget] = useState(existing?.targetCompletionDate ?? '');
  const [service, setService] = useState<Product | null>(null);
  const [error, setError] = useState('');
  const save = useMutation({
    mutationFn: () =>
      existing
        ? projects.editMilestone(projectId, existing.id, { name: name.trim(), amount, target_completion_date: target || null })
        : projects.addMilestone(projectId, {
            name: name.trim(), amount, service_product: service!.id, target_completion_date: target || undefined, sequence: nextSequence,
          }),
    onSuccess: () => { onSaved(existing ? t('care.projects.milestoneSaved') : t('care.projects.milestoneAdded')); onClose(); },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const bad = !name.trim() || !(Number(amount) > 0) || (!existing && !service);
  return (
    <CreateDialog
      open
      onClose={onClose}
      title={existing ? t('growth.editMilestone') : t('growth.addMilestone')}
      submitLabel={t('growth.save')}
      submitDisabled={bad || save.isPending}
      onSubmit={() => save.mutate()}
    >
      <TextField size="small" required label={t('growth.milestone')} value={name} onChange={(e) => setName(e.target.value)} />
      <TextField size="small" required label={t('growth.amount')} value={amount} onChange={(e) => setAmount(e.target.value)} helperText={t('care.projects.amountHelp')} inputProps={{ inputMode: 'decimal' }} error={amount !== '' && !(Number(amount) > 0)} />
      <TextField size="small" type="date" label={t('growth.targetDate')} value={target} onChange={(e) => setTarget(e.target.value)} InputLabelProps={{ shrink: true }} />
      {existing ? (
        <Typography variant="body2" color="text.secondary">{t('care.projects.serviceFixed', { name: existing.serviceProductName })}</Typography>
      ) : (
        <CatalogPicker kind="SERVICE" label={t('growth.service')} value={service} onChange={setService} required />
      )}
      {error ? <Typography role="alert" color="error" variant="body2">{error}</Typography> : null}
    </CreateDialog>
  );
}
