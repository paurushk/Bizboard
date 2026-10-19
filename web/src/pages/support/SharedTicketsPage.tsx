import { useState } from 'react';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { sharedTickets, type SharedTicket } from '@/api/care';
import { useAuth } from '@/auth/AuthContext';
import { EmptyState, ErrorState, ListSkeleton } from '@/components/PageState';
import { isSupportTicketsEnabled } from '@/config/features';
import { t } from '@/i18n';
import { formatStamp } from '@/care/format';
import {
  CareHeader,
  CareTable,
  Field,
  MasterDetail,
  Pager,
  SearchField,
  StatusPill,
  type CareColumn,
} from '@/care/kit';
import { canChangeCare, useListPath, useNotice, useUrlFilters } from '@/care/hooks';
import { enumLabel } from '@/utils/enumLabels';
import { PageShell } from '@/pages/phase/phaseShared';

const PAGE_SIZE = 20;
const BASE = '/support/shared';
const STATUSES = ['OPEN', 'IN_PROGRESS', 'WAITING', 'RESOLVED', 'CLOSED'] as const;

export function SharedTicketsPage() {
  if (!isSupportTicketsEnabled()) {
    return <PageShell title={t('nav.sharedTickets')}><Typography>{t('erp.moduleDisabled')}</Typography></PageShell>;
  }
  return <SharedWorkspace />;
}

function SharedWorkspace() {
  const { id } = useParams();
  const selectedId = id ? Number(id) : null;
  const { user } = useAuth();
  const listPath = useListPath(BASE);
  const { values, set } = useUrlFilters({ q: '', status: '', page: '1' });
  const page = Math.max(1, Number(values.page) || 1);
  const list = useQuery({
    queryKey: ['shared-tickets', values.q, values.status, page],
    queryFn: () => sharedTickets.list({ q: values.q || undefined, status: values.status || undefined, page, pageSize: PAGE_SIZE }),
  });
  const rows = list.data?.results ?? [];
  const columns: CareColumn<SharedTicket>[] = [
    { key: 'number', header: t('care.shared.col.ticket'), primary: true, render: (row) => `${row.sourceNumber} · ${row.subject}` },
    { key: 'company', header: t('care.shared.col.company'), render: (row) => row.sourceCompanyName },
    { key: 'status', header: t('growth.status'), render: (row) => <StatusPill group="ticketStatus" value={row.status} /> },
    { key: 'replies', header: t('care.shared.col.replies'), render: (row) => row.replyCount },
    { key: 'shared', header: t('care.shared.col.shared'), render: (row) => formatStamp(row.sharedAt) },
  ];
  const listNode = (
    <Stack spacing={1.5}>
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
        <SearchField value={values.q} onChange={(q) => set({ q })} />
        <TextField select size="small" label={t('growth.status')} value={values.status} onChange={(e) => set({ status: e.target.value })} sx={{ minWidth: 160 }}>
          <MenuItem value="">{t('growth.all')}</MenuItem>
          {STATUSES.map((value) => <MenuItem key={value} value={value}>{enumLabel('ticketStatus', value)}</MenuItem>)}
        </TextField>
      </Stack>
      {list.isLoading ? <ListSkeleton rows={5} /> : null}
      {list.isError ? <ErrorState message={getErrorMessage(list.error)} error={list.error} onRetry={() => void list.refetch()} /> : null}
      {!list.isLoading && !list.isError && rows.length === 0 ? <EmptyState description={t('care.shared.empty')} /> : null}
      {rows.length > 0 ? (
        <CareTable
          caption={t('nav.sharedTickets')}
          columns={selectedId ? columns.filter((c) => ['number', 'status'].includes(c.key)) : columns}
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
      <CareHeader title={t('nav.sharedTickets')} subtitle={t('care.shared.subtitle')} />
      <MasterDetail
        list={listNode}
        detail={selectedId ? <SharedDetail key={selectedId} id={selectedId} canReply={canChangeCare(user)} /> : null}
        hasSelection={selectedId != null}
        backTo={listPath()}
        detailLabel={t('care.shared.detail')}
      />
    </Stack>
  );
}

export function SharedDetail({ id, canReply }: { id: number; canReply: boolean }) {
  const qc = useQueryClient();
  const feedback = useNotice();
  const [body, setBody] = useState('');
  const share = useQuery({ queryKey: ['shared-tickets', 'detail', id], queryFn: () => sharedTickets.get(id), retry: false });
  const replies = useQuery({ queryKey: ['shared-tickets', 'replies', id], queryFn: () => sharedTickets.replies(id), retry: false });
  const send = useMutation({
    mutationFn: () => sharedTickets.reply(id, body.trim()),
    onSuccess: () => {
      setBody('');
      feedback.ok(t('care.shared.replySent'));
      void qc.invalidateQueries({ queryKey: ['shared-tickets'] });
    },
    onError: (err) => feedback.fail(err),
  });
  if (share.isLoading) return <ListSkeleton rows={3} />;
  if (share.isError || !share.data) {
    // A revoked share disappears for the vendor; say so instead of showing a bare error.
    return <Typography role="status">{t('care.shared.gone')}</Typography>;
  }
  const row = share.data;
  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Stack spacing={2}>
        <Box>
          <Typography variant="h6" component="h2">{row.sourceNumber} · {row.subject}</Typography>
          <StatusPill group="ticketStatus" value={row.status} />
        </Box>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
          <Field label={t('care.shared.col.company')}>{row.sourceCompanyName}</Field>
          <Field label={t('care.shared.col.shared')}>{formatStamp(row.sharedAt)}</Field>
        </Stack>
        <Field label={t('growth.description')}>
          {row.description ? <Box sx={{ whiteSpace: 'pre-wrap' }}>{row.description}</Box> : <Typography variant="body2" color="text.secondary">{t('care.shared.noDescription')}</Typography>}
        </Field>
        {feedback.node}
        <Box>
          <Typography variant="subtitle2" component="h3">{t('care.shared.yourReplies')}</Typography>
          {replies.isError ? <Typography variant="body2" color="error">{getErrorMessage(replies.error)}</Typography> : null}
          {!replies.isLoading && (replies.data ?? []).length === 0 ? (
            <Typography variant="body2" color="text.secondary">{t('care.shared.noReplies')}</Typography>
          ) : null}
          <Stack spacing={1} component="ul" style={{ listStyle: 'none', padding: 0, margin: '8px 0' }}>
            {(replies.data ?? []).map((reply) => (
              <li key={reply.id}>
                <Typography variant="caption" color="text.secondary">{reply.authorName} · {formatStamp(reply.createdAt)}</Typography>
                <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>{reply.body}</Typography>
              </li>
            ))}
          </Stack>
          {canReply ? (
            <Stack spacing={1}>
              <TextField size="small" multiline minRows={2} label={t('care.shared.replyLabel')} value={body} onChange={(e) => setBody(e.target.value)} helperText={t('care.shared.replyHelp')} />
              <Button size="small" variant="contained" sx={{ alignSelf: 'flex-start' }} disabled={!body.trim() || send.isPending} onClick={() => send.mutate()}>
                {t('care.shared.sendReply')}
              </Button>
            </Stack>
          ) : null}
        </Box>
      </Stack>
    </Paper>
  );
}
