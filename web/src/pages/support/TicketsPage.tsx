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
import { PageTitle } from '@/contextHelp';
import { isSupportTicketsEnabled } from '@/config/features';
import { t } from '@/i18n';
import { AttachmentEditor, CustomerField } from '@/pages/growth/widgets';
import type { Customer } from '@/types/domain';
import { PageShell } from '@/pages/phase/phaseShared';

const STATUSES = ['OPEN', 'IN_PROGRESS', 'WAITING', 'RESOLVED', 'CLOSED'] as const;
const PRIORITIES = ['LOW', 'MEDIUM', 'HIGH', 'URGENT'] as const;
const NEXT: Record<string, string[]> = {
  OPEN: ['IN_PROGRESS'],
  IN_PROGRESS: ['WAITING', 'RESOLVED'],
  WAITING: ['IN_PROGRESS'],
  RESOLVED: ['CLOSED', 'IN_PROGRESS'],
  CLOSED: ['IN_PROGRESS'],
};
const OPENISH = new Set(['OPEN', 'IN_PROGRESS', 'WAITING']);

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
  const [selected, setSelected] = useState<number | null>(null);
  const [priorityFilter, setPriorityFilter] = useState('');
  const [assigneeFilter, setAssigneeFilter] = useState('');
  const [mineOnly, setMineOnly] = useState(false);
  const [error, setError] = useState('');
  const list = useQuery({
    queryKey: ['tickets', priorityFilter, assigneeFilter, mineOnly],
    queryFn: () => listTicketsPage({
      pageSize: 100,
      priority: priorityFilter || undefined,
      assigned_to: assigneeFilter || undefined,
      mine: mineOnly || undefined,
    }),
  });
  const users = useQuery({ queryKey: ['company-users'], queryFn: listCompanyUsers });
  const report = useQuery({ queryKey: ['ticket-report'], queryFn: ticketReport });
  const create = useMutation({
    mutationFn: () => createTicket({ customer: customer!.id, subject, priority }),
    onSuccess: () => {
      setSubject('');
      setError('');
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
      <PageTitle>{t('nav.tickets')}</PageTitle>
      <Typography variant="body2" color="text.secondary">{t('growth.ticketsInternal')}</Typography>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1}>
        <CustomerField value={customer} onChange={setCustomer} />
        <TextField size="small" label={t('growth.subject')} value={subject} onChange={(e) => setSubject(e.target.value)} />
        <TextField select size="small" label={t('growth.priority')} value={priority} onChange={(e) => setPriority(e.target.value)} sx={{ minWidth: 140 }}>
          {PRIORITIES.map((value) => <MenuItem key={value} value={value}>{value}</MenuItem>)}
        </TextField>
        <Button variant="contained" disabled={!customer || !subject.trim() || create.isPending} onClick={() => create.mutate()}>{t('growth.create')}</Button>
      </Stack>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} alignItems={{ md: 'center' }}>
        <TextField select size="small" label={t('growth.priority')} value={priorityFilter} onChange={(e) => setPriorityFilter(e.target.value)} sx={{ minWidth: 140 }}>
          <MenuItem value="">{t('growth.all')}</MenuItem>
          {PRIORITIES.map((value) => <MenuItem key={value} value={value}>{value}</MenuItem>)}
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
      {error ? <Typography color="error">{error}</Typography> : null}
      <Stack direction={{ xs: 'column', lg: 'row' }} spacing={1}>
        {STATUSES.map((status) => (
          <Paper key={status} variant="outlined" sx={{ p: 1.5, flex: 1 }}>
            <Typography variant="subtitle2">{status}</Typography>
            {rows.filter((row) => row.status === status).map((row) => (
              <Paper key={row.id} variant="outlined" sx={{ p: 1, mt: 1, cursor: 'pointer' }} onClick={() => setSelected(row.id)}>
                <Typography variant="body2">{row.number} · {row.subject}</Typography>
                <Typography variant="caption" display="block">{t('growth.assignee')}: {nameOf(row.assignedTo)}</Typography>
                <SlaChip row={row} />
              </Paper>
            ))}
          </Paper>
        ))}
      </Stack>
      {selected ? <TicketDetail key={selected} id={selected} assigneeName={nameOf} onError={setError} /> : null}
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography variant="subtitle2">{t('growth.report')}</Typography>
        <Typography variant="body2">{t('growth.average')}: {report.data?.averageResolutionSeconds ?? '—'}</Typography>
        {(report.data?.byStatus ?? []).map((row) => (
          <Typography key={row.status} variant="caption" display="block">{row.status}: {row.count}</Typography>
        ))}
      </Paper>
    </Stack>
  );
}

function SlaChip({ row }: { row: TicketRow }) {
  if (!row.slaDueAt) return null;
  const breached = OPENISH.has(row.status) && new Date(row.slaDueAt).getTime() < Date.now();
  return <Chip size="small" color={breached ? 'error' : 'default'} label={breached ? t('growth.slaBreached') : `${t('growth.sla')} ${row.slaDueAt}`} />;
}

function TicketDetail({ id, assigneeName, onError }: { id: number; assigneeName: (assigneeId: number | null) => string; onError: (message: string) => void }) {
  const qc = useQueryClient();
  const { user } = useAuth();
  const [includeDescription, setIncludeDescription] = useState(false);
  const [body, setBody] = useState('');
  const ticket = useQuery({ queryKey: ['ticket', id], queryFn: () => getTicket(id) });
  const comments = useQuery({ queryKey: ['ticket-comments', id], queryFn: () => listTicketComments(id) });
  const files = useQuery({ queryKey: ['ticket-files', id], queryFn: () => listTicketAttachments(id) });
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
      <Typography variant="body2">{t('growth.assignee')}: {assigneeName(row.assignedTo)} · {row.priority}</Typography>
      <SlaChip row={row} />
      <Stack direction="row" spacing={1} sx={{ mt: 1 }} flexWrap="wrap" useFlexGap>
        {user?.role === 'OWNER' ? (
          <>
            <FormControlLabel
              control={<Checkbox checked={includeDescription} onChange={(e) => setIncludeDescription(e.target.checked)} />}
              label="Include description"
            />
            <Button size="small" onClick={() => run.mutate(() => shareTicket(id, includeDescription))}>Share with BizBoard</Button>
            <Button size="small" onClick={() => run.mutate(() => stopSharingTicket(id))}>Stop sharing</Button>
          </>
        ) : null}
        {(NEXT[row.status] ?? []).map((status) => (
          <Button key={status} size="small" variant="outlined" onClick={() => run.mutate(() => transitionTicket(id, status))}>
            {t('growth.moveTo')} {status}
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
