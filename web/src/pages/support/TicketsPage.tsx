import { useState } from 'react';
import Checkbox from '@mui/material/Checkbox';
import Chip from '@mui/material/Chip';
import FormControlLabel from '@mui/material/FormControlLabel';
import Button from '@mui/material/Button';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { shareTicket, stopSharingTicket } from '@/api/roadmap';
import { useAuth } from '@/auth/AuthContext';
import {
  addTicketComment,
  createTicket,
  updateTicket,
  deleteTicketAttachment,
  getTicket,
  listTicketAttachments,
  listTicketComments,
  listTicketsPage,
  ticketReport,
  transitionTicket,
  uploadTicketAttachment,
  type TicketRow,
} from '@/api/growth';
import { listCompanyUsers } from '@/api/resources';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { PageTitle } from '@/contextHelp';
import { isSupportTicketsEnabled } from '@/config/features';
import { formatDuration } from '@/utils/duration';
import { CreateDialog } from '@/components/CreateDialog';
import { slaChipModel } from '@/cognitive/loadHelpers';
import { enumLabel } from '@/utils/enumLabels';
import { t } from '@/i18n';
import { AttachmentEditor, CustomerField } from '@/pages/growth/widgets';
import type { Customer } from '@/types/domain';
import { PageShell } from '@/pages/phase/phaseShared';

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

export function TicketsPage() {
  if (!isSupportTicketsEnabled()) {
    return <PageShell title={t('nav.tickets')}><Typography>{t('erp.moduleDisabled')}</Typography></PageShell>;
  }
  return <TicketsInner />;
}

function TicketsInner() {
  const qc = useQueryClient();
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [subject, setSubject] = useState('');
  const [priority, setPriority] = useState('MEDIUM');
  const [category, setCategory] = useState('GENERAL');
  const [assignee, setAssignee] = useState('');
  const [createOpen, setCreateOpen] = useState(false);
  const [selected, setSelected] = useState<number | null>(null);
  const [priorityFilter, setPriorityFilter] = useState('');
  const [assigneeFilter, setAssigneeFilter] = useState('');
  const [mineOnly, setMineOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState('');
  const [error, setError] = useState('');
  const list = useQuery({
    queryKey: ['tickets', priorityFilter, assigneeFilter, mineOnly, page, q],
    queryFn: () => listTicketsPage({
      page,
      pageSize: 20,
      q: q.trim() || undefined,
      priority: priorityFilter || undefined,
      assigned_to: assigneeFilter || undefined,
      mine: mineOnly || undefined,
    }),
  });
  const users = useQuery({ queryKey: ['company-users'], queryFn: listCompanyUsers });
  const report = useQuery({ queryKey: ['ticket-report'], queryFn: ticketReport });
  const create = useMutation({
    mutationFn: () => createTicket({
      customer: customer!.id,
      subject,
      priority,
      category,
      assigned_to: assignee ? Number(assignee) : null,
    }),
    onSuccess: () => {
      setSubject('');
      setError('');
      setCreateOpen(false);
      void qc.invalidateQueries({ queryKey: ['tickets'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const rows = list.data?.results ?? [];
  const nameOf = (id: number | null) => {
    if (!id) return t('growth.unassigned');
    const member = (users.data ?? []).find((user) => user.id === id);
    const fromRow = rows.find((row) => row.assignedTo === id)?.assigneeName;
    return member?.fullName || member?.email || fromRow || `#${id}`;
  };

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
        <PageTitle>{t('nav.tickets')}</PageTitle>
        <Button variant="contained" onClick={() => setCreateOpen(true)}>{t('growth.newTicket')}</Button>
      </Stack>
      <Typography variant="body2" color="text.secondary">{t('growth.ticketsInternal')}</Typography>
      <CreateDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title={t('growth.newTicket')}
        submitLabel={t('growth.openTicket')}
        submitDisabled={!customer || !subject.trim() || create.isPending}
        dirty={Boolean(subject.trim() || customer)}
        onSubmit={() => create.mutate()}
      >
        <CustomerField value={customer} onChange={setCustomer} />
        <TextField size="small" label={t('growth.subject')} value={subject} onChange={(e) => setSubject(e.target.value)} />
        <TextField select size="small" label={t('growth.priority')} value={priority} onChange={(e) => setPriority(e.target.value)}>
          {PRIORITIES.map((value) => <MenuItem key={value} value={value}>{enumLabel('ticketPriority', value)}</MenuItem>)}
        </TextField>
        <TextField select size="small" label={t('growth.category')} value={category} onChange={(e) => setCategory(e.target.value)}>
          {CATEGORIES.map((value) => (
            <MenuItem key={value} value={value}>{value === 'NUMBER_MISMATCH' ? t('growth.categoryNumberMismatch') : t('growth.categoryGeneral')}</MenuItem>
          ))}
        </TextField>
        <TextField select size="small" label={t('growth.assignee')} value={assignee} onChange={(e) => setAssignee(e.target.value)}>
          <MenuItem value="">{t('growth.unassigned')}</MenuItem>
          {(users.data ?? []).map((member) => (
            <MenuItem key={member.id} value={String(member.id)}>{member.fullName || member.email}</MenuItem>
          ))}
        </TextField>
      </CreateDialog>
      <TextField size="small" label={t('cog.searchGrowth')} value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} alignItems={{ md: 'center' }}>
        <TextField select size="small" label={t('growth.priority')} value={priorityFilter} onChange={(e) => setPriorityFilter(e.target.value)} sx={{ minWidth: 140 }}>
          <MenuItem value="">{t('growth.all')}</MenuItem>
          {PRIORITIES.map((value) => <MenuItem key={value} value={value}>{enumLabel('ticketPriority', value)}</MenuItem>)}
        </TextField>
        <TextField select size="small" label={t('growth.assignee')} value={assigneeFilter} onChange={(e) => setAssigneeFilter(e.target.value)} sx={{ minWidth: 180 }}>
          <MenuItem value="">{t('growth.all')}</MenuItem>
          {(users.data ?? []).map((member) => (
            <MenuItem key={member.id} value={String(member.id)}>{member.fullName || member.email}</MenuItem>
          ))}
          {(users.data ?? []).length === 0
            ? Array.from(
              new Map(rows.filter((row) => row.assignedTo).map((row) => [row.assignedTo, row])).values(),
            ).map((row) => (
              <MenuItem key={row.assignedTo} value={String(row.assignedTo)}>
                {row.assigneeName || `#${row.assignedTo}`}
              </MenuItem>
            ))
            : null}
        </TextField>
        <FormControlLabel control={<Checkbox checked={mineOnly} onChange={(e) => setMineOnly(e.target.checked)} />} label={t('growth.mine')} />
      </Stack>
      {list.isLoading ? <LoadingState /> : null}
      {list.isError ? <ErrorState message={getErrorMessage(list.error)} error={list.error} onRetry={() => void list.refetch()} /> : null}
      {!list.isLoading && !list.isError && rows.length === 0 ? (
        <EmptyState description={t('cog.emptyTickets')} action={<Button variant="contained" onClick={() => setCreateOpen(true)}>{t('growth.newTicket')}</Button>} />
      ) : null}
      {error ? <Typography color="error">{error}</Typography> : null}
      <Stack direction={{ xs: 'column', lg: 'row' }} spacing={1}>
        {STATUSES.map((status) => (
          <Paper key={status} variant="outlined" sx={{ p: 1.5, flex: 1 }}>
            <Typography variant="subtitle2">{enumLabel('ticketStatus', status)}</Typography>
            {rows.filter((row) => row.status === status).map((row) => (
              <Paper key={row.id} variant="outlined" sx={{ p: 1, mt: 1, cursor: 'pointer' }} onClick={() => setSelected(row.id)}>
                <Typography variant="body2">{row.number} · {row.subject}</Typography>
                <Typography variant="caption" display="block">
                  {t('growth.assignee')}: {nameOf(row.assignedTo)}
                  {' · '}
                  {t('growth.category')}: {row.category === 'NUMBER_MISMATCH' ? t('growth.categoryNumberMismatch') : t('growth.categoryGeneral')}
                </Typography>
                <SlaChip row={row} />
              </Paper>
            ))}
          </Paper>
        ))}
      </Stack>
      <Stack direction="row" spacing={1}>
        <Button size="small" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>{t('common.previous')}</Button>
        <Button size="small" disabled={!list.data?.next} onClick={() => setPage((p) => p + 1)}>{t('common.next')}</Button>
      </Stack>
      {selected ? <TicketDetail key={selected} id={selected} assigneeName={nameOf} onError={setError} /> : null}
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography variant="subtitle2">{t('growth.report')}</Typography>
        <Typography variant="body2">{t('growth.average')}: {formatDuration(report.data?.averageResolutionSeconds)}</Typography>
        {(report.data?.byStatus ?? []).map((row) => (
          <Typography key={row.status} variant="caption" display="block">{enumLabel('ticketStatus', row.status)}: {row.count}</Typography>
        ))}
      </Paper>
    </Stack>
  );
}

/** Wall clock read at render time of the chip. Module level so the render rules see no impure call. */
const wallClockMs = () => Date.now();

/** 90 -> "1h 30m", 45 -> "45m", 0 -> "0m". */
function formatMinutes(total: number): string {
  const minutes = Math.max(0, Math.round(total));
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours === 0) return `${rest}m`;
  return rest === 0 ? `${hours}h` : `${hours}h ${rest}m`;
}

function SlaChip({ row }: { row: TicketRow }) {
  const model = slaChipModel({
    status: row.status,
    slaDueAt: row.slaDueAt,
    createdAt: row.createdAt,
    now: wallClockMs(),
  });
  if (model.kind === 'none') return null;
  const label = model.kind === 'paused'
    ? t('cog.slaPaused')
    : model.kind === 'breached'
      ? t('cog.slaBreached', { time: formatMinutes(model.minutes) })
      : t('cog.slaRemaining', { time: formatMinutes(model.minutes) });
  return (
    <Chip
      size="small"
      color={model.kind === 'breached' ? 'error' : 'default'}
      label={`${label} · ${t('cog.slaElapsed', { time: formatMinutes(model.elapsedMinutes) })}`}
    />
  );
}

function TicketDetail({ id, assigneeName, onError }: { id: number; assigneeName: (assigneeId: number | null) => string; onError: (message: string) => void }) {
  const qc = useQueryClient();
  const { user } = useAuth();
  const [includeDescription, setIncludeDescription] = useState(false);
  const [body, setBody] = useState('');
  const ticket = useQuery({ queryKey: ['ticket', id], queryFn: () => getTicket(id) });
  const comments = useQuery({ queryKey: ['ticket-comments', id], queryFn: () => listTicketComments(id) });
  const files = useQuery({ queryKey: ['ticket-files', id], queryFn: () => listTicketAttachments(id) });
  const members = useQuery({ queryKey: ['company-users'], queryFn: listCompanyUsers });
  const row = ticket.data;
  const run = useMutation({
    mutationFn: async (work: () => Promise<unknown>) => work(),
    onSuccess: () => {
      onError('');
      void qc.invalidateQueries({ queryKey: ['tickets'] });
      void qc.invalidateQueries({ queryKey: ['ticket', id] });
      void qc.invalidateQueries({ queryKey: ['ticket-comments', id] });
      void qc.invalidateQueries({ queryKey: ['ticket-files', id] });
      void qc.invalidateQueries({ queryKey: ['ticket-report'] });
    },
    onError: (err) => onError(getErrorMessage(err)),
  });
  if (!row) return null;
  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Typography variant="subtitle2">{row.number} · {row.subject}</Typography>
      <Typography variant="body2">
        {t('growth.category')}: {row.category === 'NUMBER_MISMATCH' ? t('growth.categoryNumberMismatch') : t('growth.categoryGeneral')}
        {' · '}
        {t('growth.assignee')}: {assigneeName(row.assignedTo)} · {row.priority}
      </Typography>
      <TextField
        select
        size="small"
        sx={{ mt: 1, minWidth: 220, display: 'block' }}
        label={t('growth.assignee')}
        value={row.assignedTo ?? ''}
        onChange={(e) => run.mutate(() => updateTicket(id, { assigned_to: e.target.value ? Number(e.target.value) : null }))}
      >
        <MenuItem value="">{t('growth.unassigned')}</MenuItem>
        {(members.data ?? []).map((member) => (
          <MenuItem key={member.id} value={member.id}>{member.fullName || member.email}</MenuItem>
        ))}
      </TextField>
      <SlaChip row={row} />
      <Stack direction="row" spacing={1} sx={{ mt: 1 }} flexWrap="wrap" useFlexGap>
        {user?.role === 'OWNER' ? (
          <>
            <FormControlLabel
              control={<Checkbox checked={includeDescription} onChange={(e) => setIncludeDescription(e.target.checked)} />}
              label={t('growth.includeDescription')}
            />
            {row.shareAvailable !== false ? (
              <Button size="small" onClick={() => run.mutate(() => shareTicket(id, includeDescription))}>{t('growth.shareWithBizboard')}</Button>
            ) : null}
            <Button size="small" onClick={() => run.mutate(() => stopSharingTicket(id))}>{t('growth.stopSharing')}</Button>
          </>
        ) : null}
        {(NEXT[row.status] ?? []).map((status) => (
          <Button key={status} size="small" variant="outlined" onClick={() => run.mutate(() => transitionTicket(id, status))}>
            {t('growth.moveTo')} {enumLabel('ticketStatus', status)}
          </Button>
        ))}
      </Stack>
      <Typography variant="subtitle2" sx={{ mt: 2 }}>{t('growth.comments')}</Typography>
      {(comments.data ?? []).map((comment) => (
        <Typography key={comment.id} variant="body2">{comment.body} · {t('growth.internal')}</Typography>
      ))}
      <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
        <TextField size="small" label={t('growth.comment')} value={body} onChange={(e) => setBody(e.target.value)} />
        <Button disabled={!body.trim()} onClick={() => run.mutate(async () => { await addTicketComment(id, body); setBody(''); })}>{t('growth.save')}</Button>
      </Stack>
      <AttachmentEditor
        rows={files.data ?? []}
        onUpload={(file) => run.mutate(() => uploadTicketAttachment(id, file))}
        onDelete={(attachmentId) => run.mutate(() => deleteTicketAttachment(id, attachmentId))}
      />
    </Paper>
  );
}
