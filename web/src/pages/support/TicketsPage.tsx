import { useState } from 'react';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import Divider from '@mui/material/Divider';
import FormControlLabel from '@mui/material/FormControlLabel';
import Link from '@mui/material/Link';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { tickets, type Ticket } from '@/api/care';
import { useAuth } from '@/auth/AuthContext';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { CreateDialog } from '@/components/CreateDialog';
import { EmptyState, ErrorState, ListSkeleton } from '@/components/PageState';
import { isSupportTicketsEnabled } from '@/config/features';
import { t } from '@/i18n';
import { AttachmentPanel } from '@/care/attachments';
import { formatSpan, formatStamp, ageSeconds } from '@/care/format';
import {
  ActivityTimeline,
  CareHeader,
  CareTable,
  Field,
  LinkedRecords,
  MasterDetail,
  MemberPicker,
  Pager,
  SearchField,
  SlaChip,
  StatusPill,
  CustomerLink,
  type CareColumn,
} from '@/care/kit';
import { canChangeCare, useListPath, useNotice, useUrlFilters } from '@/care/hooks';
import { ContractPicker, InvoicePicker } from '@/care/pickers';
import { enumLabel } from '@/utils/enumLabels';
import { CustomerField } from '@/pages/growth/widgets';
import { PageShell } from '@/pages/phase/phaseShared';
import type { Customer, SalesInvoice } from '@/types/domain';
import type { Contract } from '@/api/care';

const STATUSES = ['OPEN', 'IN_PROGRESS', 'WAITING', 'RESOLVED', 'CLOSED'] as const;
const PRIORITIES = ['LOW', 'MEDIUM', 'HIGH', 'URGENT'] as const;
const CATEGORIES = ['GENERAL', 'NUMBER_MISMATCH'] as const;
const NEXT: Record<string, string[]> = {
  OPEN: ['IN_PROGRESS'],
  IN_PROGRESS: ['WAITING', 'RESOLVED'],
  WAITING: ['IN_PROGRESS'],
  RESOLVED: ['CLOSED', 'IN_PROGRESS'],
  CLOSED: ['IN_PROGRESS'],
};
const PAGE_SIZE = 20;
const BASE = '/support/tickets';

export function TicketsPage() {
  if (!isSupportTicketsEnabled()) {
    return <PageShell title={t('nav.tickets')}><Typography>{t('erp.moduleDisabled')}</Typography></PageShell>;
  }
  return <TicketsWorkspace />;
}

function categoryLabel(value: string) {
  return value === 'NUMBER_MISMATCH' ? t('growth.categoryNumberMismatch') : t('growth.categoryGeneral');
}

function TicketsWorkspace() {
  const { id } = useParams();
  const selectedId = id ? Number(id) : null;
  const { user } = useAuth();
  const canChange = canChangeCare(user);
  const listPath = useListPath(BASE);
  // Someone who is not the owner starts on their own tickets; "0" is the explicit choice to see everyone's.
  const { values, set } = useUrlFilters({
    q: '', status: '', priority: '', assigned: '', mine: user?.role === 'OWNER' ? '' : '1', unassigned: '', view: 'list', page: '1', hideClosed: '1',
  });
  const [createOpen, setCreateOpen] = useState(false);
  const page = Math.max(1, Number(values.page) || 1);
  const filters = {
    q: values.q || undefined,
    status: values.status || undefined,
    priority: values.priority || undefined,
    assigned_to: values.assigned || undefined,
    mine: values.mine === '1' ? 1 : undefined,
    unassigned: values.unassigned ? 1 : undefined,
    hide_closed_after_days: values.hideClosed === '1' && !values.status ? 7 : undefined,
  };
  const list = useQuery({
    queryKey: ['tickets', 'list', filters, page, values.view],
    queryFn: () => tickets.list({ ...filters, page, pageSize: values.view === 'board' ? 1 : PAGE_SIZE }),
    enabled: values.view === 'list',
  });
  const report = useQuery({ queryKey: ['tickets', 'report', filters], queryFn: () => tickets.report(filters) });
  const rows = list.data?.results ?? [];
  const openCount = (report.data?.byStatus ?? [])
    .filter((row) => ['OPEN', 'IN_PROGRESS', 'WAITING'].includes(row.status))
    .reduce((sum, row) => sum + row.count, 0);

  const columns: CareColumn<Ticket>[] = [
    {
      key: 'subject',
      header: t('care.tickets.col.ticket'),
      primary: true,
      render: (row) => `${row.number} · ${row.subject}`,
    },
    { key: 'customer', header: t('growth.customer'), render: (row) => row.customerName },
    { key: 'priority', header: t('growth.priority'), render: (row) => <StatusPill group="ticketPriority" value={row.priority} /> },
    { key: 'status', header: t('growth.status'), render: (row) => <StatusPill group="ticketStatus" value={row.status} /> },
    { key: 'sla', header: t('care.tickets.col.sla'), render: (row) => <SlaChip state={row.slaState} remainingSeconds={row.slaRemainingSeconds} /> },
    { key: 'assignee', header: t('growth.assignee'), render: (row) => row.assigneeName || t('growth.unassigned') },
    { key: 'age', header: t('care.tickets.col.age'), render: (row) => formatSpan(ageSeconds(row.createdAt)) },
  ];

  const listNode = (
    <Stack spacing={1.5}>
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
        <SearchField key={values.q === '' ? 'blank' : 'typed'} value={values.q} onChange={(q) => set({ q })} />
        <TextField select size="small" label={t('growth.status')} value={values.status} onChange={(e) => set({ status: e.target.value })} sx={{ minWidth: 150 }}>
          <MenuItem value="">{t('growth.all')}</MenuItem>
          {STATUSES.map((value) => <MenuItem key={value} value={value}>{enumLabel('ticketStatus', value)}</MenuItem>)}
        </TextField>
        <TextField select size="small" label={t('growth.priority')} value={values.priority} onChange={(e) => set({ priority: e.target.value })} sx={{ minWidth: 140 }}>
          <MenuItem value="">{t('growth.all')}</MenuItem>
          {PRIORITIES.map((value) => <MenuItem key={value} value={value}>{enumLabel('ticketPriority', value)}</MenuItem>)}
        </TextField>
        <MemberPicker
          label={t('growth.assignee')}
          value={values.assigned ? Number(values.assigned) : null}
          onChange={(member) => set({ assigned: member ? String(member) : '' })}
          minWidth={180}
        />
        <FormControlLabel
          control={<Checkbox checked={values.mine === '1'} onChange={(e) => set({ mine: e.target.checked ? '1' : '0' })} />}
          label={t('growth.mine')}
        />
        <FormControlLabel
          control={<Checkbox checked={Boolean(values.unassigned)} onChange={(e) => set({ unassigned: e.target.checked ? '1' : '' })} />}
          label={t('care.tickets.unassignedQueue')}
        />
        <FormControlLabel
          control={<Checkbox checked={values.hideClosed === '1'} onChange={(e) => set({ hideClosed: e.target.checked ? '1' : '0' })} />}
          label={t('care.tickets.hideOldClosed')}
        />
        <ToggleButtonGroup
          size="small"
          exclusive
          value={values.view}
          onChange={(_, next) => next && set({ view: next })}
          aria-label={t('care.tickets.view')}
        >
          <ToggleButton value="list">{t('care.tickets.viewList')}</ToggleButton>
          <ToggleButton value="board">{t('care.tickets.viewBoard')}</ToggleButton>
        </ToggleButtonGroup>
      </Stack>
      {report.data ? (
        <Typography variant="body2" color="text.secondary" aria-live="polite">
          {t('care.tickets.summary', {
            open: openCount,
            breached: report.data.breached,
            average: formatSpan(report.data.averageResolutionSeconds) || '—',
          })}
        </Typography>
      ) : null}
      {values.view === 'board' ? (
        <Board filters={filters} />
      ) : (
        <>
          {list.isLoading ? <ListSkeleton rows={6} /> : null}
          {list.isError ? <ErrorState message={getErrorMessage(list.error)} error={list.error} onRetry={() => void list.refetch()} /> : null}
          {!list.isLoading && !list.isError && rows.length === 0 ? (
            <EmptyState
              description={t('cog.emptyTickets')}
              action={canChange ? <Button variant="contained" onClick={() => setCreateOpen(true)}>{t('growth.newTicket')}</Button> : undefined}
            />
          ) : null}
          {rows.length > 0 ? (
            <CareTable
              caption={t('nav.tickets')}
              columns={selectedId ? columns.filter((c) => ['subject', 'status', 'sla'].includes(c.key)) : columns}
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
        title={t('nav.tickets')}
        subtitle={t('care.tickets.subtitle')}
        actions={canChange ? <Button variant="contained" onClick={() => setCreateOpen(true)}>{t('growth.newTicket')}</Button> : undefined}
      />
      <MasterDetail
        list={listNode}
        detail={selectedId ? <TicketDetail key={selectedId} id={selectedId} canChange={canChange} isOwner={user?.role === 'OWNER'} backTo={listPath()} /> : null}
        hasSelection={selectedId != null}
        backTo={listPath()}
        detailLabel={t('care.tickets.detail')}
      />
      <NewTicketDialog open={createOpen} onClose={() => setCreateOpen(false)} />
    </Stack>
  );
}

/** Five columns, each filled from its own query so closed tickets never crowd out the open ones. */
function Board({ filters }: { filters: Record<string, unknown> }) {
  const listPath = useListPath(BASE);
  const { set } = useUrlFilters({ status: '', view: 'list' });
  return (
    <Stack direction={{ xs: 'column', lg: 'row' }} spacing={1} alignItems="stretch">
      {STATUSES.map((status) => (
        <BoardColumn key={status} status={status} filters={filters} href={listPath} onMore={() => set({ status, view: 'list' })} />
      ))}
    </Stack>
  );
}

function BoardColumn({
  status,
  filters,
  href,
  onMore,
}: {
  status: string;
  filters: Record<string, unknown>;
  href: (suffix?: string) => { pathname: string; search: string };
  onMore: () => void;
}) {
  const column = useQuery({
    queryKey: ['tickets', 'column', status, filters],
    queryFn: () => tickets.list({ ...filters, status, hide_closed_after_days: status === 'CLOSED' ? 7 : undefined, pageSize: 8 }),
  });
  const rows = column.data?.results ?? [];
  const count = column.data?.count ?? 0;
  return (
    <Paper variant="outlined" sx={{ p: 1.5, flex: 1, minWidth: 0 }} component="section" aria-label={enumLabel('ticketStatus', status)}>
      <Typography variant="subtitle2" component="h2">
        {enumLabel('ticketStatus', status)} <Typography component="span" variant="caption">({count})</Typography>
      </Typography>
      {column.isError ? <Typography variant="body2" color="error">{getErrorMessage(column.error)}</Typography> : null}
      <Stack spacing={1} sx={{ mt: 1 }}>
        {rows.map((row) => (
          <Paper key={row.id} variant="outlined" sx={{ p: 1 }}>
            <Link component={RouterLink} to={href(`/${row.id}`)} underline="hover" variant="body2" sx={{ display: 'block', minHeight: 24 }}>
              {row.number} · {row.subject}
            </Link>
            <Typography variant="caption" display="block" color="text.secondary">
              {row.customerName} · {row.assigneeName || t('growth.unassigned')}
            </Typography>
            <SlaChip state={row.slaState} remainingSeconds={row.slaRemainingSeconds} />
          </Paper>
        ))}
        {count > rows.length ? (
          <Button size="small" onClick={onMore}>{t('care.tickets.showAll', { count })}</Button>
        ) : null}
      </Stack>
    </Paper>
  );
}

function NewTicketDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const listPath = useListPath(BASE);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [subject, setSubject] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState('MEDIUM');
  const [category, setCategory] = useState('GENERAL');
  const [assignee, setAssignee] = useState<number | null>(null);
  const [invoice, setInvoice] = useState<SalesInvoice | null>(null);
  const [contract, setContract] = useState<Contract | null>(null);
  const [error, setError] = useState('');
  const create = useMutation({
    mutationFn: () =>
      tickets.create({
        customer: customer!.id,
        subject: subject.trim(),
        description,
        priority,
        category,
        assigned_to: assignee,
        source_invoice: invoice?.id ?? null,
        contract: contract?.id ?? null,
      }),
    onSuccess: (row) => {
      void qc.invalidateQueries({ queryKey: ['tickets'] });
      setSubject(''); setDescription(''); setInvoice(null); setContract(null); setError('');
      onClose();
      navigate(listPath(`/${row.id}`));
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  return (
    <CreateDialog
      open={open}
      onClose={onClose}
      title={t('growth.newTicket')}
      submitLabel={t('growth.openTicket')}
      submitDisabled={!customer || !subject.trim() || create.isPending}
      dirty={Boolean(subject.trim() || description.trim() || customer)}
      onSubmit={() => create.mutate()}
    >
      <CustomerField
        value={customer}
        onChange={(next) => { setCustomer(next); setInvoice(null); setContract(null); }}
      />
      <TextField size="small" required label={t('growth.subject')} value={subject} onChange={(e) => setSubject(e.target.value)} />
      <TextField size="small" multiline minRows={3} label={t('growth.description')} value={description} onChange={(e) => setDescription(e.target.value)} />
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
        <TextField select fullWidth size="small" label={t('growth.priority')} value={priority} onChange={(e) => setPriority(e.target.value)} helperText={t('care.tickets.priorityHelp')}>
          {PRIORITIES.map((value) => <MenuItem key={value} value={value}>{enumLabel('ticketPriority', value)}</MenuItem>)}
        </TextField>
        <TextField select fullWidth size="small" label={t('growth.category')} value={category} onChange={(e) => setCategory(e.target.value)}>
          {CATEGORIES.map((value) => <MenuItem key={value} value={value}>{categoryLabel(value)}</MenuItem>)}
        </TextField>
      </Stack>
      <MemberPicker label={t('growth.assignee')} value={assignee} onChange={setAssignee} minWidth={0} />
      <Typography variant="caption" color="text.secondary">{t('care.tickets.autoAssign')}</Typography>
      <InvoicePicker customerId={customer?.id ?? null} value={invoice} onChange={setInvoice} helperText={t('care.tickets.invoiceHelp')} />
      <ContractPicker customerId={customer?.id ?? null} value={contract} onChange={setContract} helperText={t('care.tickets.contractHelp')} />
      {error ? <Typography role="alert" color="error" variant="body2">{error}</Typography> : null}
    </CreateDialog>
  );
}

export function TicketDetail({
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
  const [body, setBody] = useState('');
  const [edit, setEdit] = useState(false);
  const [editSubject, setEditSubject] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [includeDescription, setIncludeDescription] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const ticket = useQuery({ queryKey: ['tickets', 'detail', id], queryFn: () => tickets.get(id) });
  const comments = useQuery({ queryKey: ['tickets', 'comments', id], queryFn: () => tickets.comments(id) });
  const row = ticket.data;
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['tickets'] });
    void qc.invalidateQueries({ queryKey: ['care-activity', 'Ticket', id] });
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
  if (ticket.isLoading) return <ListSkeleton rows={4} />;
  if (ticket.isError || !row) {
    return <ErrorState message={getErrorMessage(ticket.error)} error={ticket.error} onRetry={() => void ticket.refetch()} />;
  }
  const closed = row.status === 'CLOSED';
  const finished = row.status === 'RESOLVED' || closed;
  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Stack spacing={2}>
        <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={1}>
          <Box>
            <Typography variant="h6" component="h2">{row.number} · {row.subject}</Typography>
            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
              <StatusPill group="ticketStatus" value={row.status} />
              <SlaChip state={row.slaState} remainingSeconds={row.slaRemainingSeconds} />
            </Stack>
          </Box>
          {canChange && !closed ? (
            <Button size="small" onClick={() => { setEditSubject(row.subject); setEditDescription(row.description); setEdit(true); }}>
              {t('common.edit')}
            </Button>
          ) : null}
        </Stack>
        {feedback.node}
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} flexWrap="wrap" useFlexGap>
          <Field label={t('growth.customer')}><CustomerLink id={row.customer} name={row.customerName} /></Field>
          <Field label={t('growth.category')}>{categoryLabel(row.category)}</Field>
          <Field label={t('care.common.created')}>{formatStamp(row.createdAt)}</Field>
          {row.resolvedAt ? <Field label={t('care.tickets.resolvedAt')}>{formatStamp(row.resolvedAt)}</Field> : null}
          {row.sourceInvoice ? (
            <Field label={t('care.pick.invoice')}>
              <Link component={RouterLink} to={`/sales/history/${row.sourceInvoice}`}>{row.sourceInvoiceNumber}</Link>
            </Field>
          ) : null}
          {row.contract ? (
            <Field label={t('care.pick.contract')}>
              <Link component={RouterLink} to={`/contracts/${row.contract}`}>{row.contractNumber}</Link>
            </Field>
          ) : null}
        </Stack>
        <Field label={t('growth.description')}>
          <Box sx={{ whiteSpace: 'pre-wrap' }}>{row.description}</Box>
        </Field>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
          <TextField
            select
            size="small"
            label={t('growth.priority')}
            value={row.priority}
            disabled={!canChange || finished}
            helperText={finished ? t('care.tickets.reopenToChange') : undefined}
            onChange={(e) => run.mutate({ work: () => tickets.update(id, { priority: e.target.value }, row.updatedAt), done: t('care.tickets.saved') })}
            sx={{ minWidth: 160 }}
          >
            {PRIORITIES.map((value) => <MenuItem key={value} value={value}>{enumLabel('ticketPriority', value)}</MenuItem>)}
          </TextField>
          <MemberPicker
            label={t('growth.assignee')}
            value={row.assignedTo}
            disabled={!canChange || closed}
            onChange={(member) => run.mutate({ work: () => tickets.update(id, { assigned_to: member }, row.updatedAt), done: t('care.tickets.saved') })}
          />
        </Stack>
        {canChange ? (
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            {(NEXT[row.status] ?? []).map((status) => (
              <Button
                key={status}
                size="small"
                variant={status === 'RESOLVED' || status === 'IN_PROGRESS' ? 'contained' : 'outlined'}
                disabled={run.isPending}
                onClick={() => run.mutate({ work: () => tickets.transition(id, status), done: t('care.tickets.movedTo', { status: enumLabel('ticketStatus', status) }) })}
              >
                {t('growth.moveTo')} {enumLabel('ticketStatus', status)}
              </Button>
            ))}
            <Button size="small" component={RouterLink} to={`/workshop/jobs/new?ticket=${row.id}&customer=${row.customer}`}>
              {t('care.tickets.createJob')}
            </Button>
            <Button size="small" component={RouterLink} to={`/complaints?new=1&customer=${row.customer}&ticket=${row.id}${row.sourceInvoice ? `&invoice=${row.sourceInvoice}` : ''}`}>
              {t('care.tickets.logComplaint')}
            </Button>
            {isOwner && row.status === 'OPEN' ? (
              <Button size="small" color="error" onClick={() => setConfirmDelete(true)}>{t('common.delete')}</Button>
            ) : null}
          </Stack>
        ) : null}
        {isOwner && row.shareAvailable ? (
          <Paper variant="outlined" sx={{ p: 1.5 }}>
            <Typography variant="subtitle2" component="h3">{t('care.tickets.shareTitle')}</Typography>
            <Typography variant="body2" color="text.secondary">
              {row.shared
                ? t('care.tickets.sharedSince', { when: formatStamp(row.sharedAt), what: row.shareIncludesDescription ? t('care.tickets.withDescription') : t('care.tickets.subjectOnly') })
                : t('care.tickets.notShared')}
            </Typography>
            <Typography variant="caption" color="text.secondary" component="p">{t('care.tickets.shareWarning')}</Typography>
            {row.shared ? (
              <Button size="small" disabled={run.isPending} onClick={() => run.mutate({ work: () => tickets.stopSharing(id), done: t('care.tickets.shareStopped') })}>
                {t('growth.stopSharing')}
              </Button>
            ) : (
              <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                <FormControlLabel
                  control={<Checkbox checked={includeDescription} onChange={(e) => setIncludeDescription(e.target.checked)} />}
                  label={t('growth.includeDescription')}
                />
                <Button size="small" variant="outlined" disabled={run.isPending} onClick={() => run.mutate({ work: () => tickets.share(id, includeDescription), done: t('care.tickets.shareDone') })}>
                  {t('growth.shareWithBizboard')}
                </Button>
              </Stack>
            )}
          </Paper>
        ) : null}
        <Divider />
        <Box>
          <Typography variant="subtitle2" component="h3">{t('growth.comments')}</Typography>
          {comments.isError ? <Typography variant="body2" color="error">{getErrorMessage(comments.error)}</Typography> : null}
          {!comments.isLoading && (comments.data ?? []).length === 0 ? (
            <Typography variant="body2" color="text.secondary">{t('care.tickets.noComments')}</Typography>
          ) : null}
          <Stack spacing={1} sx={{ my: 1 }} component="ul" style={{ listStyle: 'none', padding: 0, margin: 0 }}>
            {(comments.data ?? []).map((comment) => (
              <li key={comment.id}>
                <Typography variant="caption" color="text.secondary">
                  {comment.authorName || '—'} · {formatStamp(comment.createdAt)}
                  {comment.fromVendor ? ` · ${t('care.tickets.vendorReply')}` : ` · ${t('growth.internal')}`}
                </Typography>
                <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>{comment.body}</Typography>
              </li>
            ))}
          </Stack>
          {canChange && !closed ? (
            <Stack spacing={1}>
              <TextField size="small" multiline minRows={2} label={t('growth.comment')} value={body} onChange={(e) => setBody(e.target.value)} />
              <Button
                size="small"
                variant="outlined"
                sx={{ alignSelf: 'flex-start' }}
                disabled={!body.trim() || run.isPending}
                onClick={() => run.mutate({ work: async () => { await tickets.comment(id, body.trim()); setBody(''); }, done: t('care.tickets.commentAdded') })}
              >
                {t('care.tickets.addComment')}
              </Button>
            </Stack>
          ) : (
            <Typography variant="caption" color="text.secondary">{closed ? t('care.tickets.closedNote') : ''}</Typography>
          )}
        </Box>
        <Divider />
        <AttachmentPanel
          queryKey={['tickets', 'files', id]}
          list={() => tickets.attachments.list(id)}
          upload={(file) => tickets.attachments.upload(id, file)}
          remove={(attachment) => tickets.attachments.remove(id, attachment)}
          canEdit={canChange}
          lockedReason={closed ? t('care.tickets.closedNote') : undefined}
        />
        <Divider />
        <LinkedRecords entity="ticket" id={id} />
        <ActivityTimeline entity="Ticket" id={id} />
      </Stack>
      <CreateDialog
        open={edit}
        onClose={() => setEdit(false)}
        title={t('care.tickets.editTitle')}
        submitLabel={t('growth.save')}
        submitDisabled={!editSubject.trim() || run.isPending}
        onSubmit={() => {
          run.mutate({ work: () => tickets.update(id, { subject: editSubject.trim(), description: editDescription }, row.updatedAt), done: t('care.tickets.saved') });
          setEdit(false);
        }}
      >
        <TextField size="small" required label={t('growth.subject')} value={editSubject} onChange={(e) => setEditSubject(e.target.value)} />
        <TextField size="small" multiline minRows={4} label={t('growth.description')} value={editDescription} onChange={(e) => setEditDescription(e.target.value)} />
      </CreateDialog>
      <ConfirmDialog
        open={confirmDelete}
        title={t('care.tickets.deleteTitle', { number: row.number })}
        body={t('care.tickets.deleteBody')}
        confirmLabel={t('common.delete')}
        confirmColor="error"
        onClose={() => setConfirmDelete(false)}
        onConfirm={() => {
          setConfirmDelete(false);
          run.mutate({
            work: async () => { await tickets.remove(id); navigate(backTo); },
            done: t('care.tickets.deleted'),
          });
        }}
      />
    </Paper>
  );
}
