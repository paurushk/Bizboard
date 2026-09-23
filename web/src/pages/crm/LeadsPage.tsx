import { useMemo, useRef, useState } from 'react';
import axios from 'axios';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import FormControlLabel from '@mui/material/FormControlLabel';
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
  assignLead,
  convertLead,
  createLead,
  createLeadActivity,
  importLeadsCsv,
  issueLeadFormToken,
  listLeadActivities,
  listLeadsPage,
  updateLead,
  type Lead,
} from '@/api/crm';
import { listCompanyUsers, listCustomersPage } from '@/api/resources';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { StatusChip } from '@/components/StatusChip';
import { PageTitle } from '@/contextHelp';
import { t } from '@/i18n';
import { ModuleGate, MvpModuleBanner } from '@/pages/erp/erpShared';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { documentStatusTone, statusLabelKey } from '@/utils/status';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';

const PAGE_SIZE = 50;
const LEAD_STATUSES = ['NEW', 'CONTACTED', 'QUALIFIED', 'LOST'] as const;
const LEAD_SOURCES = ['referral', 'website', 'whatsapp', 'walk_in', 'import', 'phone'] as const;
const ACTIVITY_KINDS = ['NOTE', 'CALL', 'EMAIL'] as const;
type LeadStatus = (typeof LEAD_STATUSES)[number];

const emptyForm = {
  name: '',
  phone: '',
  email: '',
  status: 'NEW' as LeadStatus,
  source: '' as '' | (typeof LEAD_SOURCES)[number],
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
  const { writesBlocked } = useSubscriptionGate();
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
  const [convertWon, setConvertWon] = useState(true);
  const [sourceFilter, setSourceFilter] = useState('');
  const [reviewOnly, setReviewOnly] = useState(false);
  const [mineOnly, setMineOnly] = useState(false);
  const [dedupe, setDedupe] = useState<{ customers?: number[]; leads?: number[] } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const query = useQuery({
    queryKey: ['leads', page, sourceFilter, reviewOnly, mineOnly],
    queryFn: () => listLeadsPage({
      page,
      pageSize: PAGE_SIZE,
      source: sourceFilter || undefined,
      dedupe_review: reviewOnly ? 'PENDING_REVIEW' : undefined,
      mine: mineOnly || undefined,
    }),
  });
  const members = useQuery({ queryKey: ['company-users'], queryFn: listCompanyUsers });
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
    mutationFn: async (decision?: string) => {
      const payload = {
        name: form.name,
        phone: form.phone,
        email: form.email,
        status: form.status,
        source: form.source || null,
        customer: form.customer ? Number(form.customer) : null,
      };
      if (editing) return updateLead(editing.id, payload);
      return createLead({ ...payload, dedupeDecision: decision });
    },
    onSuccess: () => {
      setOpen(false);
      setEditing(null);
      setDedupe(null);
      setForm(emptyForm);
      void qc.invalidateQueries({ queryKey: ['leads'] });
    },
    onError: (err) => {
      if (axios.isAxiosError(err) && err.response?.status === 409) {
        const body = err.response.data as { candidates?: { customers?: number[]; leads?: number[] }; data?: { candidates?: { customers?: number[]; leads?: number[] } } };
        setDedupe(body.candidates ?? body.data?.candidates ?? { customers: [], leads: [] });
        return;
      }
      setError(getErrorMessage(err));
    },
  });
  const importCsv = useMutation({
    mutationFn: (file: File) => importLeadsCsv(file),
    onSuccess: (result) => {
      setNotice(result.accepted ? t('osPlan.importStillRunning') : `${t('osPlan.importCsv')}: ${result.created}`);
      void qc.invalidateQueries({ queryKey: ['leads'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const formLink = useMutation({
    mutationFn: issueLeadFormToken,
    onSuccess: async (result) => {
      const url = `${window.location.origin}/lead-form/${result.token}`;
      await navigator.clipboard.writeText(url);
      setNotice(t('osPlan.formLinkCopied'));
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const convertMutation = useMutation({
    mutationFn: ({ lead, amount, won }: { lead: Lead; amount: number; won: boolean }) =>
      convertLead(lead.id, { amount, won }),
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
    setError(null);
    setEditing(null);
    setForm(emptyForm);
    setOpen(true);
  };

  const openEdit = (lead: Lead) => {
    setError(null);
    setEditing(lead);
    setForm({
      name: lead.name,
      phone: lead.phone ?? '',
      email: lead.email ?? '',
      status: (lead.status ?? 'NEW') as LeadStatus,
      source: (lead.source ?? '') as typeof emptyForm.source,
      customer: lead.customer ?? '',
    });
    setOpen(true);
  };

  return (
    <Stack spacing={2}>
      <MvpModuleBanner module="crm" />
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <PageTitle>{t('nav.leads')}</PageTitle>
        <Stack direction="row" spacing={1}>
          <Button variant="outlined" disabled={writesBlocked || formLink.isPending} onClick={() => formLink.mutate()}>
            {t('osPlan.formLink')}
          </Button>
          <Button variant="outlined" disabled={writesBlocked} onClick={() => fileRef.current?.click()}>
            {t('osPlan.importCsv')}
          </Button>
          <input
            ref={fileRef}
            hidden
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) importCsv.mutate(file);
              e.target.value = '';
            }}
          />
          <Button variant="contained" onClick={openCreate} disabled={writesBlocked}>
            {t('common.add')}
          </Button>
        </Stack>
      </Stack>
      {error ? <HelpErrorAlert message={error} /> : null}
      {notice ? <Typography variant="body2">{notice}</Typography> : null}
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
        <TextField select label={t('osPlan.source')} value={sourceFilter} onChange={(e) => { setSourceFilter(e.target.value); setPage(1); }} sx={{ minWidth: 160 }}>
          <MenuItem value="">{t('common.all')}</MenuItem>
          {LEAD_SOURCES.map((source) => <MenuItem key={source} value={source}>{source}</MenuItem>)}
        </TextField>
        <FormControlLabel control={<Checkbox checked={reviewOnly} onChange={(e) => { setReviewOnly(e.target.checked); setPage(1); }} />} label={t('osPlan.pendingReview')} />
        <FormControlLabel control={<Checkbox checked={mineOnly} onChange={(e) => { setMineOnly(e.target.checked); setPage(1); }} />} label={t('osPlan.myLeads')} />
      </Stack>
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
                <TableCell>{t('osPlan.source')}</TableCell>
                <TableCell>{t('osPlan.assignee')}</TableCell>
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
                  <TableCell>{lead.source || '—'}</TableCell>
                  <TableCell>
                    <TextField
                      select
                      size="small"
                      value={lead.assignedTo ?? ''}
                      onChange={(e) => {
                        const value = e.target.value;
                        void assignLead(lead.id, value ? Number(value) : null).then(() => {
                          void qc.invalidateQueries({ queryKey: ['leads'] });
                        }).catch((err) => setError(getErrorMessage(err)));
                      }}
                      sx={{ minWidth: 140 }}
                    >
                      <MenuItem value="">{t('osPlan.unassigned')}</MenuItem>
                      {(members.data ?? []).map((member) => (
                        <MenuItem key={member.id} value={member.id}>{member.fullName || member.email}</MenuItem>
                      ))}
                    </TextField>
                    {lead.dedupeReview === 'PENDING_REVIEW' ? (
                      <Typography variant="caption" display="block">{t('osPlan.pendingReview')}</Typography>
                    ) : null}
                  </TableCell>
                  <TableCell>
                    <StatusChip
                      tone={documentStatusTone(lead.status ?? 'NEW')}
                      labelKey={statusLabelKey(lead.status ?? 'NEW')}
                    />
                  </TableCell>
                  <TableCell align="right">
                    <Button size="small" onClick={() => openEdit(lead)} disabled={writesBlocked}>
                      {t('common.edit')}
                    </Button>
                    <Button size="small" onClick={() => { setError(null); setTimelineLead(lead); }}>
                      {t('erp.activities')}
                    </Button>
                    <Button
                      size="small"
                      disabled={writesBlocked || convertMutation.isPending}
                      onClick={() => {
                        setError(null);
                        setConvertLeadRow(lead);
                        setConvertAmount('0');
                        setConvertWon(true);
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

      <Dialog open={open} onClose={() => { setError(null); setOpen(false); }} fullWidth maxWidth="sm">
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
              label={t('osPlan.source')}
              value={form.source}
              onChange={(e) => setForm((f) => ({ ...f, source: e.target.value as typeof form.source }))}
            >
              <MenuItem value="">{t('osPlan.unassigned')}</MenuItem>
              {LEAD_SOURCES.map((source) => (
                <MenuItem key={source} value={source}>{source}</MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label={t('common.status')}
              value={form.status}
              onChange={(e) => setForm((f) => ({ ...f, status: e.target.value as LeadStatus }))}
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
          <Button onClick={() => { setError(null); setOpen(false); }}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={!form.name || writesBlocked || saveMutation.isPending}
            onClick={() => saveMutation.mutate()}
          >
            {t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={Boolean(timelineLead)}
        onClose={() => { setError(null); setTimelineLead(null); }}
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
              label={t('erp.activityKind')}
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
          <Button onClick={() => { setError(null); setTimelineLead(null); }}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={!activityBody.trim() || writesBlocked || activityMutation.isPending}
            onClick={() => activityMutation.mutate()}
          >
            {t('erp.addActivity')}
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog open={Boolean(convertLeadRow)} onClose={() => { setError(null); setConvertLeadRow(null); }} fullWidth maxWidth="xs">
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
            <FormControlLabel
              control={
                <Checkbox checked={convertWon} onChange={(e) => setConvertWon(e.target.checked)} />
              }
              label={t('erp.markAsWon')}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => { setError(null); setConvertLeadRow(null); }}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={writesBlocked || convertMutation.isPending || !convertLeadRow}
            onClick={() => {
              if (!convertLeadRow) return;
              convertMutation.mutate({
                lead: convertLeadRow,
                amount: Number(convertAmount) || 0,
                won: convertWon,
              });
              setConvertLeadRow(null);
            }}
          >
            {t('erp.convertLead')}
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog open={dedupe !== null} onClose={() => setDedupe(null)} fullWidth maxWidth="sm">
        <DialogTitle>{t('osPlan.dedupeTitle')}</DialogTitle>
        <DialogContent>
          <Stack spacing={1} sx={{ mt: 1 }}>
            {(dedupe?.customers ?? []).map((id) => (
              <Typography key={`c-${id}`} variant="body2">{customerMap.get(id) ?? id}</Typography>
            ))}
            {(dedupe?.leads ?? []).map((id) => (
              <Typography key={`l-${id}`} variant="body2">{rows.find((lead) => lead.id === id)?.name ?? id}</Typography>
            ))}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDedupe(null)}>{t('common.cancel')}</Button>
          <Button onClick={() => saveMutation.mutate('review')}>{t('osPlan.dedupeReview')}</Button>
          <Button variant="contained" onClick={() => saveMutation.mutate('create')}>{t('osPlan.dedupeCreate')}</Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
