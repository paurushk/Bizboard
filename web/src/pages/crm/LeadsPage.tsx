import { useMemo, useRef, useState, type HTMLAttributes } from 'react';
import axios from 'axios';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import FormControlLabel from '@mui/material/FormControlLabel';
import Menu from '@mui/material/Menu';
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
import { useNavigate } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { LOST_REASONS, listCampaignsPage } from '@/api/growth';
import {
  assignLead,
  convertLead,
  draftOpportunityInvoice,
  createLead,
  createLeadActivity,
  importLeadsCsv,
  issueLeadFormToken,
  issueWhatsappWebhookToken,
  whatsappWebhookUrl,
  listLeadActivities,
  listLeadsPage,
  updateLead,
  type DedupeDetails,
  type ImportResult,
  type Lead,
} from '@/api/crm';
import { listCompanyUsers, listCustomersPage } from '@/api/resources';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { StatusChip } from '@/components/StatusChip';
import { PageTitle } from '@/contextHelp';
import { t } from '@/i18n';
import { enumLabel } from '@/utils/enumLabels';
import { useAuth } from '@/auth/AuthContext';
import { isReferralsEnabled } from '@/config/features';
import { ModuleGate, MvpModuleBanner } from '@/pages/erp/erpShared';
import { CustomerField } from '@/pages/growth/widgets';
import { formatDateTime } from '@/utils/dateTime';
import type { Customer } from '@/types/domain';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { documentStatusTone, statusLabelKey } from '@/utils/status';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { isPastIso } from '@/utils/clock';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { CandidateList, DedupeReviewDialog } from '@/pages/crm/DedupeReviewDialog';
import { WhatsappSettingsDialog } from '@/pages/crm/WhatsappSettingsDialog';

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
  campaign: '' as number | '',
  referralCode: '',
  lostReason: '',
  lostReasonNote: '',
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
  const { user } = useAuth();
  const navigate = useNavigate();
  const isOwner = user?.role === 'OWNER';
  const isManager = isOwner || user?.role === 'MANAGER';
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Lead | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState<string | null>(null);
  const [timelineLead, setTimelineLead] = useState<Lead | null>(null);
  const [activityKind, setActivityKind] = useState<string>('NOTE');
  const [activityBody, setActivityBody] = useState('');
  const [activityDue, setActivityDue] = useState('');
  const [convertLeadRow, setConvertLeadRow] = useState<Lead | null>(null);
  const [convertAmount, setConvertAmount] = useState('0');
  const [convertWon, setConvertWon] = useState(false);
  const [sourceFilter, setSourceFilter] = useState('');
  const [campaignFilter, setCampaignFilter] = useState('');
  const [reviewOnly, setReviewOnly] = useState(false);
  const [mineOnly, setMineOnly] = useState(false);
  const [dedupe, setDedupe] = useState<DedupeDetails | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [importResult, setImportResult] = useState<ImportResult | null>(null);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [assigneeFilter, setAssigneeFilter] = useState('');
  const [reviewLead, setReviewLead] = useState<Lead | null>(null);
  const [whatsappOpen, setWhatsappOpen] = useState(false);
  const [replaceFormOpen, setReplaceFormOpen] = useState(false);
  const term = useDebouncedValue(search, 300).trim();
  const [captureAnchor, setCaptureAnchor] = useState<HTMLElement | null>(null);
  const [customerPick, setCustomerPick] = useState<Customer | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const query = useQuery({
    queryKey: ['leads', page, sourceFilter, campaignFilter, reviewOnly, mineOnly, term, statusFilter, assigneeFilter],
    queryFn: () => listLeadsPage({
      page,
      pageSize: PAGE_SIZE,
      source: sourceFilter || undefined,
      campaign: campaignFilter || undefined,
      dedupe_review: reviewOnly ? 'PENDING_REVIEW' : undefined,
      mine: mineOnly || undefined,
      q: term || undefined,
      status: statusFilter || undefined,
      assigned_to: assigneeFilter || undefined,
    }),
  });
  const members = useQuery({ queryKey: ['company-users'], queryFn: listCompanyUsers });
  const campaigns = useQuery({ queryKey: ['campaigns', 'filter'], queryFn: () => listCampaignsPage({ pageSize: 100 }) });
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
  const campaignMap = useMemo(() => {
    const map = new Map<number, string>();
    for (const campaign of campaigns.data?.results ?? []) map.set(campaign.id, campaign.name);
    return map;
  }, [campaigns.data]);

  const rows = query.data?.results ?? [];

  // Clipboard needs HTTPS and permission; when it fails the link is shown so it can still be copied by hand.
  const copyLink = async (url: string, doneKey: string) => {
    try {
      await navigator.clipboard.writeText(url);
      setNotice(t(doneKey));
    } catch {
      setNotice(t('growth.copyFailed', { url }));
    }
  };

  const saveMutation = useMutation({
    mutationFn: async (decision?: string) => {
      const payload = {
        name: form.name,
        phone: form.phone,
        email: form.email,
        status: form.status,
        source: form.source || null,
        customer: form.customer ? Number(form.customer) : null,
        campaign: form.campaign ? Number(form.campaign) : null,
        ...(form.status === 'LOST' && editing?.status !== 'LOST'
          ? { lostReason: form.lostReason, lostReasonNote: form.lostReasonNote }
          : {}),
      };
      if (editing) return updateLead(editing.id, payload);
      const code = form.referralCode.trim();
      return createLead({ ...payload, ...(code ? { referralCode: code } : {}), dedupeDecision: decision });
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
        const body = err.response.data as { details?: DedupeDetails; data?: { details?: DedupeDetails } };
        setDedupe(body.details ?? body.data?.details ?? { customers: [], leads: [] });
        return;
      }
      setError(getErrorMessage(err));
    },
  });
  const importCsv = useMutation({
    mutationFn: (file: File) => importLeadsCsv(file),
    onSuccess: (result) => {
      if (result.accepted) {
        setImportResult(null);
        setNotice(t('osPlan.importStillRunning'));
      } else {
        setNotice(null);
        setImportResult({ ...result, errors: result.errors ?? [] });
      }
      void qc.invalidateQueries({ queryKey: ['leads'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const formLink = useMutation({
    mutationFn: issueLeadFormToken,
    onSuccess: async (result) => {
      await copyLink(`${window.location.origin}/lead-form/${result.token}`, 'osPlan.formLinkCopied');
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const formReplace = useMutation({
    mutationFn: () => issueLeadFormToken({ rotate: true }),
    onSuccess: async (result) => {
      setReplaceFormOpen(false);
      await copyLink(`${window.location.origin}/lead-form/${result.token}`, 'osPlan.formLinkReplaced');
    },
    onError: (err) => {
      setReplaceFormOpen(false);
      setError(getErrorMessage(err));
    },
  });
  const whatsappLink = useMutation({
    mutationFn: () => issueWhatsappWebhookToken(false),
    onSuccess: async (result) => {
      await copyLink(whatsappWebhookUrl(result.token), 'osPlan.whatsappLinkCopied');
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const whatsappReplace = useMutation({
    mutationFn: () => issueWhatsappWebhookToken(true),
    onSuccess: async (result) => {
      await copyLink(whatsappWebhookUrl(result.token), 'osPlan.whatsappLinkReplaced');
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const convertMutation = useMutation({
    mutationFn: ({ lead, amount, won }: { lead: Lead; amount: number; won: boolean }) =>
      convertLead(lead.id, { amount, won }),
    onSuccess: (result, vars) => {
      void qc.invalidateQueries({ queryKey: ['leads'] });
      void qc.invalidateQueries({ queryKey: ['opportunities'] });
      void qc.invalidateQueries({ queryKey: ['customers'] });
      if (vars.won && result.opportunity?.id) {
        void draftOpportunityInvoice(result.opportunity.id)
          .then((draft) => {
            if (draft?.id) navigate(`/sales/history/${draft.id}/edit`);
          })
          .catch((err) => setError(t('growth.convertDraftFailed', { detail: getErrorMessage(err) }))); // a failed draft must not vanish silently
      }
    },
    onError: (err) => setError(getErrorMessage(err)),
    onSettled: () => setConvertLeadRow(null),
  });

  const activityMutation = useMutation({
    mutationFn: () =>
      createLeadActivity(timelineLead!.id, {
        kind: activityKind,
        body: activityBody,
        dueAt: activityDue ? new Date(activityDue).toISOString() : null,
      }),
    onSuccess: () => {
      setActivityBody('');
      setActivityKind('NOTE');
      setActivityDue('');
      void qc.invalidateQueries({ queryKey: ['lead-activities', timelineLead?.id] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const openCreate = () => {
    setError(null);
    setEditing(null);
    setForm(emptyForm);
    setCustomerPick(null);
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
      campaign: lead.campaign ?? '',
      referralCode: '',
      lostReason: lead.lostReason ?? '',
      lostReasonNote: lead.lostReasonNote ?? '',
    });
    setCustomerPick(
      lead.customer ? ({ id: lead.customer, name: lead.customerName ?? `#${lead.customer}` } as Customer) : null,
    );
    setOpen(true);
  };

  return (
    <Stack spacing={2}>
      <MvpModuleBanner module="crm" />
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <PageTitle>{t('nav.leads')}</PageTitle>
        <Stack direction="row" spacing={1}>
          <Button
            variant="outlined"
            aria-haspopup="menu"
            aria-expanded={captureAnchor ? 'true' : undefined}
            onClick={(e) => setCaptureAnchor(e.currentTarget)}
          >
            {t('growth.leadCapture')}
          </Button>
          <Menu anchorEl={captureAnchor} open={Boolean(captureAnchor)} onClose={() => setCaptureAnchor(null)}>
            <MenuItem disabled={writesBlocked || formLink.isPending} onClick={() => { setCaptureAnchor(null); formLink.mutate(); }}>
              {t('osPlan.formLink')}
            </MenuItem>
            {isManager ? (
              <MenuItem disabled={writesBlocked || formReplace.isPending} onClick={() => { setCaptureAnchor(null); setReplaceFormOpen(true); }}>
                {t('osPlan.formLinkReplace')}
              </MenuItem>
            ) : null}
            {isOwner ? (
              <MenuItem onClick={() => { setCaptureAnchor(null); setWhatsappOpen(true); }}>
                {t('osPlan.whatsappSettings')}
              </MenuItem>
            ) : null}
            {isOwner ? (
              <MenuItem disabled={writesBlocked || whatsappLink.isPending} onClick={() => { setCaptureAnchor(null); whatsappLink.mutate(); }}>
                {t('osPlan.whatsappLink')}
              </MenuItem>
            ) : null}
            {isOwner ? (
              <MenuItem disabled={writesBlocked || whatsappReplace.isPending} onClick={() => { setCaptureAnchor(null); whatsappReplace.mutate(); }}>
                {t('osPlan.whatsappLinkReplace')}
              </MenuItem>
            ) : null}
            <MenuItem disabled={writesBlocked} onClick={() => { setCaptureAnchor(null); fileRef.current?.click(); }}>
              {t('osPlan.importCsv')}
            </MenuItem>
            <Typography variant="caption" color="text.secondary" sx={{ px: 2, pb: 1, display: 'block', maxWidth: 280 }}>
              {t('growth.csvHint')}
            </Typography>
          </Menu>
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
      {importResult ? (
        <Stack spacing={0.5}>
          <Typography variant="body2">
            {t('osPlan.importResultFull', {
              created: String(importResult.created),
              total: String(importResult.total ?? importResult.created),
              pending: String(importResult.pendingReview ?? 0),
              failed: String(importResult.errorCount ?? importResult.errors.length),
            })}
          </Typography>
          {importResult.errors.slice(0, 10).map((err) => (
            <Typography key={`${err.row}-${err.detail}`} variant="body2" color="error">
              {t('osPlan.importRowError', { row: String(err.row), detail: err.detail })}
            </Typography>
          ))}
          {importResult.errors.length > 0 ? (
            <Stack direction="row" spacing={1} alignItems="center">
              <Typography variant="caption">
                {t('osPlan.importErrorsShown', {
                  shown: String(importResult.errors.length),
                  failed: String(importResult.errorCount ?? importResult.errors.length),
                })}
              </Typography>
              <Button size="small" onClick={() => downloadImportErrors(importResult)}>{t('osPlan.importDownloadErrors')}</Button>
            </Stack>
          ) : null}
        </Stack>
      ) : null}
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
        <TextField
          label={t('osPlan.searchLeads')}
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          sx={{ minWidth: 220 }}
        />
        <TextField select label={t('common.status')} value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }} sx={{ minWidth: 150 }}>
          <MenuItem value="">{t('common.all')}</MenuItem>
          {LEAD_STATUSES.map((value) => <MenuItem key={value} value={value}>{t(statusLabelKey(value))}</MenuItem>)}
        </TextField>
        <TextField select label={t('osPlan.assignee')} value={assigneeFilter} onChange={(e) => { setAssigneeFilter(e.target.value); setPage(1); }} sx={{ minWidth: 180 }}>
          <MenuItem value="">{t('common.all')}</MenuItem>
          {(members.data ?? []).map((member) => (
            <MenuItem key={member.id} value={String(member.id)}>{member.fullName || member.email}</MenuItem>
          ))}
        </TextField>
      </Stack>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
        <TextField select label={t('osPlan.source')} value={sourceFilter} onChange={(e) => { setSourceFilter(e.target.value); setPage(1); }} sx={{ minWidth: 160 }}>
          <MenuItem value="">{t('common.all')}</MenuItem>
          {LEAD_SOURCES.map((source) => <MenuItem key={source} value={source}>{enumLabel('leadSource', source)}</MenuItem>)}
        </TextField>
        <TextField select label={t('nav.campaigns')} value={campaignFilter} onChange={(e) => { setCampaignFilter(e.target.value); setPage(1); }} sx={{ minWidth: 180 }}>
          <MenuItem value="">{t('common.all')}</MenuItem>
          {(campaigns.data?.results ?? []).map((campaign) => <MenuItem key={campaign.id} value={String(campaign.id)}>{campaign.name}</MenuItem>)}
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
        <Paper tabIndex={0} role="region" aria-label={t('common.scrollableTable')} sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('common.name')}</TableCell>
                <TableCell>{t('common.phone')}</TableCell>
                <TableCell>{t('common.email')}</TableCell>
                <TableCell>{t('nav.customers')}</TableCell>
                <TableCell>{t('osPlan.source')}</TableCell>
                <TableCell>{t('nav.campaigns')}</TableCell>
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
                    {lead.customer ? lead.customerName ?? customerMap.get(lead.customer) ?? `#${lead.customer}` : '—'}
                  </TableCell>
                  <TableCell>{lead.source ? enumLabel('leadSource', lead.source) : '—'}</TableCell>
                  <TableCell>{lead.campaign ? lead.campaignName ?? campaignMap.get(lead.campaign) ?? `#${lead.campaign}` : '—'}</TableCell>
                  <TableCell>
                    <TextField
                      select
                      size="small"
                      SelectProps={{ SelectDisplayProps: { 'aria-label': t('osPlan.assignLead', { name: lead.name }) } as HTMLAttributes<HTMLDivElement> }}
                      value={lead.assignedTo ?? ''}
                      onChange={(e) => {
                        const value = e.target.value;
                        void assignLead(lead.id, value ? Number(value) : null).then(() => {
                          void qc.invalidateQueries({ queryKey: ['leads'] });
                        }).catch((err) => setError(getErrorMessage(err)));
                      }}
                      sx={{ minWidth: 160, '& .MuiInputBase-root': { minHeight: 44 } }}
                    >
                      <MenuItem value="">{t('osPlan.unassigned')}</MenuItem>
                      {(members.data ?? []).map((member) => (
                        <MenuItem key={member.id} value={member.id}>{member.fullName || member.email}</MenuItem>
                      ))}
                    </TextField>
                    {lead.dedupeReview === 'PENDING_REVIEW' ? (
                      <>
                        <Typography variant="caption" display="block">{t('osPlan.pendingReview')}</Typography>
                        <Button size="small" disabled={writesBlocked} onClick={() => { setError(null); setReviewLead(lead); }}>
                          {t('osPlan.reviewDuplicate')}
                        </Button>
                      </>
                    ) : null}
                  </TableCell>
                  <TableCell>
                    <StatusChip
                      tone={documentStatusTone(lead.status ?? 'NEW')}
                      labelKey={statusLabelKey(lead.status ?? 'NEW')}
                    />
                    {lead.status === 'LOST' && lead.lostReason ? (
                      <Typography variant="caption" display="block">{t(`growth.lostReason${lead.lostReason}`)}</Typography>
                    ) : null}
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
                      disabled={writesBlocked || convertMutation.isPending || lead.dedupeReview === 'PENDING_REVIEW' || lead.status === 'LOST'}
                      onClick={() => {
                        setError(null);
                        setConvertLeadRow(lead);
                        setConvertAmount('0');
                        setConvertWon(false);
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
                <MenuItem key={source} value={source}>{enumLabel('leadSource', source)}</MenuItem>
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
            {form.status === 'LOST' && editing?.status !== 'LOST' ? (
              <>
                <TextField
                  select
                  required
                  label={t('growth.lostReason')}
                  value={form.lostReason}
                  onChange={(e) => setForm((f) => ({ ...f, lostReason: e.target.value }))}
                >
                  {LOST_REASONS.map((reason) => (
                    <MenuItem key={reason} value={reason}>{t(`growth.lostReason${reason}`)}</MenuItem>
                  ))}
                </TextField>
                {form.lostReason === 'OTHER' ? (
                  <TextField
                    required
                    label={t('growth.lostReasonNote')}
                    value={form.lostReasonNote}
                    inputProps={{ maxLength: 200 }}
                    onChange={(e) => setForm((f) => ({ ...f, lostReasonNote: e.target.value }))}
                  />
                ) : null}
              </>
            ) : null}
            <TextField
              select
              label={t('nav.campaigns')}
              value={form.campaign}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  campaign: e.target.value ? Number(e.target.value) : '',
                }))
              }
            >
              <MenuItem value="">{t('growth.none')}</MenuItem>
              {(campaigns.data?.results ?? []).map((campaign) => (
                <MenuItem key={campaign.id} value={campaign.id}>{campaign.name}</MenuItem>
              ))}
            </TextField>
            {isReferralsEnabled() && !editing ? (
              <TextField
                label={t('growth.referralCode')}
                value={form.referralCode}
                onChange={(e) => setForm((f) => ({ ...f, referralCode: e.target.value }))}
              />
            ) : null}
            <CustomerField
              value={customerPick}
              onChange={(customer) => {
                setCustomerPick(customer);
                setForm((f) => ({ ...f, customer: customer?.id ?? '' }));
              }}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => { setError(null); setOpen(false); }}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={
              !form.name || writesBlocked || saveMutation.isPending
              || (form.status === 'LOST' && editing?.status !== 'LOST'
                && (!form.lostReason || (form.lostReason === 'OTHER' && !form.lostReasonNote.trim())))
            }
            onClick={() => saveMutation.mutate(undefined)}
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
                  {activityKindLabel(activity.kind)} · {formatDateTime(activity.createdAt)}
                  {activity.createdByName ? ` · ${t('osPlan.activityBy', { name: activity.createdByName })}` : ''}
                  {activity.dueAt
                    ? ` · ${isPastIso(activity.dueAt) ? t('osPlan.overdue') : t('osPlan.activityDue')} ${formatDateTime(activity.dueAt)}`
                    : ''}
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
            <TextField
              type="datetime-local"
              label={t('osPlan.activityDue')}
              value={activityDue}
              onChange={(e) => setActivityDue(e.target.value)}
              InputLabelProps={{ shrink: true }}
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
            {convertWon ? (
              <Typography variant="body2" color={Number(convertAmount) > 0 ? 'text.secondary' : 'error'}>
                {Number(convertAmount) > 0 ? t('growth.convertWonWarning') : t('growth.wonNeedsAmount')}
              </Typography>
            ) : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => { setError(null); setConvertLeadRow(null); }}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={writesBlocked || convertMutation.isPending || !convertLeadRow || (convertWon && !(Number(convertAmount) > 0))}
            onClick={() => {
              if (!convertLeadRow) return;
              convertMutation.mutate({
                lead: convertLeadRow,
                amount: Number(convertAmount) || 0,
                won: convertWon,
              });
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
            {dedupe ? <CandidateList details={dedupe} /> : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDedupe(null)}>{t('common.cancel')}</Button>
          <Button onClick={() => saveMutation.mutate('review')}>{t('osPlan.dedupeReview')}</Button>
          <Button variant="contained" onClick={() => saveMutation.mutate('create')}>{t('osPlan.dedupeCreate')}</Button>
        </DialogActions>
      </Dialog>
      <DedupeReviewDialog
        lead={reviewLead}
        onClose={() => setReviewLead(null)}
        onResolved={() => {
          setReviewLead(null);
          setNotice(t('osPlan.dedupeResolved'));
          void qc.invalidateQueries({ queryKey: ['leads'] });
        }}
      />
      <WhatsappSettingsDialog open={whatsappOpen} onClose={() => setWhatsappOpen(false)} />
      <ConfirmDialog
        open={replaceFormOpen}
        title={t('osPlan.formLinkReplaceTitle')}
        body={t('osPlan.formLinkReplaceBody')}
        confirmColor="warning"
        confirming={formReplace.isPending}
        onClose={() => setReplaceFormOpen(false)}
        onConfirm={() => formReplace.mutate()}
      />
    </Stack>
  );
}

/** Rows that could not be imported, as a file the person can fix and upload again. */
function downloadImportErrors(result: ImportResult) {
  const quote = (value: string | number | undefined) => `"${String(value ?? '').replace(/"/g, '""')}"`;
  const lines = [
    ['row', 'name', 'phone', 'email', 'problem'].join(','),
    ...result.errors.map((e) => [e.row, quote(e.name), quote(e.phone), quote(e.email), quote(e.detail)].join(',')),
  ];
  const url = URL.createObjectURL(new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'lead-import-problems.csv';
  link.click();
  URL.revokeObjectURL(url);
}
