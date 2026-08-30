import { useMemo, useState } from 'react';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
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
import { getErrorMessage } from '@/api/client';
import {
  convertLead,
  createLead,
  createLeadActivity,
  listLeadActivities,
  listLeadsPage,
  updateLead,
  type Lead,
} from '@/api/crm';
import { listCustomersPage } from '@/api/resources';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { StatusChip } from '@/components/StatusChip';
import { t } from '@/i18n';
import { ModuleGate, MvpModuleBanner } from '@/pages/erp/erpShared';
import { documentStatusTone, statusLabelKey } from '@/utils/status';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';

const PAGE_SIZE = 50;
const LEAD_STATUSES = ['NEW', 'CONTACTED', 'QUALIFIED', 'LOST'] as const;
const ACTIVITY_KINDS = ['NOTE', 'CALL', 'EMAIL'] as const;

const emptyForm = {
  name: '',
  phone: '',
  email: '',
  status: 'NEW',
  customer: '' as number | '',
};

export function LeadsPage() {
  return (
    <ModuleGate module="crm" title={t('nav.leads')}>
      <LeadsPageInner />
    </ModuleGate>
  );
}

function activityKindLabel(kind: string) {
  if (kind === 'CALL') return t('erp.activityCall');
  if (kind === 'EMAIL') return t('erp.activityEmail');
  return t('erp.activityNote');
}

function LeadsPageInner() {
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Lead | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState<string | null>(null);
  const [timelineLead, setTimelineLead] = useState<Lead | null>(null);
  const [activityKind, setActivityKind] = useState<string>('NOTE');
  const [activityBody, setActivityBody] = useState('');
  const [convertLeadRow, setConvertLeadRow] = useState<Lead | null>(null);
  const [convertAmount, setConvertAmount] = useState('0');

  const query = useQuery({
    queryKey: ['leads', page],
    queryFn: () => listLeadsPage({ page, pageSize: PAGE_SIZE }),
  });
  const customersQuery = useQuery({
    queryKey: ['customers', 'crm'],
    queryFn: () => listCustomersPage({ page: 1, pageSize: 200 }),
  });
  const activitiesQuery = useQuery({
    queryKey: ['lead-activities', timelineLead?.id],
    queryFn: () => listLeadActivities(timelineLead!.id),
    enabled: Boolean(timelineLead),
  });

  const customerMap = useMemo(() => {
    const map = new Map<number, string>();
    for (const c of customersQuery.data?.results ?? []) map.set(c.id, c.name);
    return map;
  }, [customersQuery.data]);

  const rows = query.data?.results ?? [];

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        name: form.name,
        phone: form.phone,
        email: form.email,
        status: form.status,
        customer: form.customer ? Number(form.customer) : null,
      };
      if (editing) return updateLead(editing.id, payload);
      return createLead(payload);
    },
    onSuccess: () => {
      setOpen(false);
      setEditing(null);
      setForm(emptyForm);
      void qc.invalidateQueries({ queryKey: ['leads'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const convertMutation = useMutation({
    mutationFn: ({ lead, amount }: { lead: Lead; amount: number }) =>
      convertLead(lead.id, { amount }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['leads'] });
      void qc.invalidateQueries({ queryKey: ['opportunities'] });
      void qc.invalidateQueries({ queryKey: ['customers'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const activityMutation = useMutation({
    mutationFn: () =>
      createLeadActivity(timelineLead!.id, { kind: activityKind, body: activityBody }),
    onSuccess: () => {
      setActivityBody('');
      setActivityKind('NOTE');
      void qc.invalidateQueries({ queryKey: ['lead-activities', timelineLead?.id] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const openCreate = () => {
    setEditing(null);
    setForm(emptyForm);
    setOpen(true);
  };

  const openEdit = (lead: Lead) => {
    setEditing(lead);
    setForm({
      name: lead.name,
      phone: lead.phone ?? '',
      email: lead.email ?? '',
      status: lead.status,
      customer: lead.customer ?? '',
    });
    setOpen(true);
  };

  return (
    <Stack spacing={2}>
      <MvpModuleBanner module="crm" />
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="h4">{t('nav.leads')}</Typography>
        <Button variant="contained" onClick={openCreate}>
          {t('common.add')}
        </Button>
      </Stack>
      {error ? <HelpErrorAlert message={error} /> : null}
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {rows.length === 0 && !query.isLoading && !query.isError ? (
        <EmptyState description={t('empty.leads')} />
      ) : null}
      {rows.length > 0 ? (
        <Paper sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('common.name')}</TableCell>
                <TableCell>{t('common.phone')}</TableCell>
                <TableCell>{t('common.email')}</TableCell>
                <TableCell>{t('nav.customers')}</TableCell>
                <TableCell>{t('common.status')}</TableCell>
                <TableCell align="right">{t('common.actions')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((lead) => (
                <TableRow key={lead.id}>
                  <TableCell>{lead.name}</TableCell>
                  <TableCell>{lead.phone || '—'}</TableCell>
                  <TableCell>{lead.email || '—'}</TableCell>
                  <TableCell>
                    {lead.customer ? customerMap.get(lead.customer) ?? lead.customer : '—'}
                  </TableCell>
                  <TableCell>
                    <StatusChip
                      tone={documentStatusTone(lead.status)}
                      labelKey={statusLabelKey(lead.status)}
                    />
                  </TableCell>
                  <TableCell align="right">
                    <Button size="small" onClick={() => openEdit(lead)}>
                      {t('common.edit')}
                    </Button>
                    <Button size="small" onClick={() => setTimelineLead(lead)}>
                      {t('erp.activities')}
                    </Button>
                    <Button
                      size="small"
                      disabled={convertMutation.isPending}
                      onClick={() => {
                        setConvertLeadRow(lead);
                        setConvertAmount('0');
                      }}
                    >
                      {t('erp.convertLead')}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}
      {query.data && (query.data.next || page > 1) ? (
        <Stack direction="row" spacing={1} justifyContent="flex-end" alignItems="center">
          <Typography variant="body2" color="text.secondary">
            {t('common.page')} {page}
          </Typography>
          <Button variant="outlined" size="small" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            {t('common.previous')}
          </Button>
          <Button
            variant="outlined"
            size="small"
            disabled={!query.data.next}
            onClick={() => setPage((p) => p + 1)}
          >
            {t('common.next')}
          </Button>
        </Stack>
      ) : null}

      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editing ? t('common.edit') : t('common.create')} lead</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label={t('common.name')}
              required
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            />
            <TextField
              label={t('common.phone')}
              value={form.phone}
              onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))}
            />
            <TextField
              label={t('common.email')}
              value={form.email}
              onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
            />
            <TextField
              select
              label={t('common.status')}
              value={form.status}
              onChange={(e) => setForm((f) => ({ ...f, status: e.target.value }))}
            >
              {LEAD_STATUSES.map((s) => (
                <MenuItem key={s} value={s}>
                  {t(statusLabelKey(s))}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label={t('nav.customers')}
              value={form.customer}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  customer: e.target.value ? Number(e.target.value) : '',
                }))
              }
            >
              <MenuItem value="">—</MenuItem>
              {(customersQuery.data?.results ?? []).map((c) => (
                <MenuItem key={c.id} value={c.id}>
                  {c.name}
                </MenuItem>
              ))}
            </TextField>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={!form.name || saveMutation.isPending}
            onClick={() => saveMutation.mutate()}
          >
            {t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={Boolean(timelineLead)}
        onClose={() => setTimelineLead(null)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>
          {t('erp.activities')}
          {timelineLead ? ` — ${timelineLead.name}` : ''}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {activitiesQuery.isLoading ? <LoadingState /> : null}
            {(activitiesQuery.data ?? []).length === 0 && !activitiesQuery.isLoading ? (
              <Typography variant="body2" color="text.secondary">
                {t('common.empty')}
              </Typography>
            ) : null}
            {(activitiesQuery.data ?? []).map((activity) => (
              <Paper key={activity.id} variant="outlined" sx={{ p: 1.5 }}>
                <Typography variant="caption" color="text.secondary">
                  {activityKindLabel(activity.kind)} · {activity.createdAt}
                </Typography>
                <Typography variant="body2">{activity.body}</Typography>
              </Paper>
            ))}
            <TextField
              select
              label={t('common.status')}
              value={activityKind}
              onChange={(e) => setActivityKind(e.target.value)}
            >
              {ACTIVITY_KINDS.map((kind) => (
                <MenuItem key={kind} value={kind}>
                  {activityKindLabel(kind)}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label={t('erp.activityBody')}
              multiline
              minRows={2}
              value={activityBody}
              onChange={(e) => setActivityBody(e.target.value)}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setTimelineLead(null)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={!activityBody.trim() || activityMutation.isPending}
            onClick={() => activityMutation.mutate()}
          >
            {t('erp.addActivity')}
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog open={Boolean(convertLeadRow)} onClose={() => setConvertLeadRow(null)} fullWidth maxWidth="xs">
        <DialogTitle>{t('erp.convertLead')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Typography variant="body2">{t('erp.convertLeadConfirm')}</Typography>
            <TextField
              label={t('erp.convertAmount')}
              type="number"
              value={convertAmount}
              onChange={(e) => setConvertAmount(e.target.value)}
              inputProps={{ min: 0, step: '0.01' }}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConvertLeadRow(null)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={convertMutation.isPending || !convertLeadRow}
            onClick={() => {
              if (!convertLeadRow) return;
              convertMutation.mutate({ lead: convertLeadRow, amount: Number(convertAmount) || 0 });
              setConvertLeadRow(null);
            }}
          >
            {t('erp.convertLead')}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
