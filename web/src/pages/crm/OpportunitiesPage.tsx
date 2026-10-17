import { useState } from 'react';
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
import { useNavigate } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { LOST_REASONS, reopenOpportunity } from '@/api/growth';
import { useAuth } from '@/auth/AuthContext';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import {
  createOpportunity,
  draftOpportunityInvoice,
  createQuotationFromOpportunity,
  listOpportunitiesPage,
  updateOpportunity,
  type Opportunity,
} from '@/api/crm';
import { CustomerField, LeadField } from '@/pages/growth/widgets';
import type { Customer } from '@/types/domain';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { StatusChip } from '@/components/StatusChip';
import { PageTitle } from '@/contextHelp';
import { t } from '@/i18n';
import { ModuleGate, MvpModuleBanner } from '@/pages/erp/erpShared';
import { formatMoney } from '@/utils/money';
import { documentStatusTone, statusLabelKey } from '@/utils/status';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';

const PAGE_SIZE = 50;
const STAGES = ['OPEN', 'QUALIFIED', 'NEGOTIATION', 'WON', 'LOST'] as const;
type Stage = (typeof STAGES)[number];

const emptyForm = {
  title: '',
  amount: '',
  stage: 'OPEN' as Stage,
  lead: '' as number | '',
  customer: '' as number | '',
  competitor: '',
  lostReason: '',
  lostReasonNote: '',
};

export function OpportunitiesPage() {
  return (
    <ModuleGate module="crm" title={t('nav.opportunities')}>
      <OpportunitiesPageInner />
    </ModuleGate>
  );
}

function OpportunitiesPageInner() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Opportunity | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState<string | null>(null);
  const [confirmClose, setConfirmClose] = useState(false);
  const [confirmReopen, setConfirmReopen] = useState(false);
  const { writesBlocked } = useSubscriptionGate();
  const { user } = useAuth();
  const canReopen = user?.role === 'OWNER' || user?.role === 'MANAGER';
  const isClosed = Boolean(editing && (editing.stage === 'WON' || editing.stage === 'LOST'));

  const query = useQuery({
    queryKey: ['opportunities', page],
    queryFn: () => listOpportunitiesPage({ page, pageSize: PAGE_SIZE }),
  });
  const [leadPick, setLeadPick] = useState<{ id: number; name: string } | null>(null);
  const [customerPick, setCustomerPick] = useState<Customer | null>(null);

  const rows = query.data?.results ?? [];

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (form.stage === 'WON' && !form.customer) {
        throw new Error(t('growth.wonNeedsCustomer'));
      }
      const closing = form.stage === 'LOST' && (!editing || editing.stage !== 'LOST');
      if (closing) {
        if (!form.lostReason) throw new Error(t('growth.lostReason'));
        if (form.lostReason === 'OTHER' && !form.lostReasonNote.trim()) throw new Error(t('growth.lostReasonNeedsNote'));
      }
      const payload: Record<string, unknown> = {
        title: form.title,
        amount: form.amount || '0',
        stage: form.stage,
        lead: form.lead ? Number(form.lead) : null,
        customer: form.customer ? Number(form.customer) : null,
        competitor: form.competitor.trim(),
      };
      if (closing) {
        payload.lost_reason = form.lostReason;
        payload.lost_reason_note = form.lostReasonNote.trim();
      }
      if (editing) {
        // Send only what changed: a deal with lines has a derived amount, and a closed deal is locked.
        const before: Record<string, unknown> = {
          title: editing.title,
          amount: editing.amount ?? '0',
          stage: editing.stage ?? 'OPEN',
          lead: editing.lead ?? null,
          customer: editing.customer ?? null,
          competitor: editing.competitor ?? '',
        };
        const changed: Record<string, unknown> = {};
        for (const [key, value] of Object.entries(payload)) {
          if (key in before && String(before[key] ?? '') === String(value ?? '')) continue;
          changed[key] = value;
        }
        return updateOpportunity(editing.id, changed as Partial<Opportunity>);
      }
      return createOpportunity(payload as Partial<Opportunity>);
    },
    onSuccess: () => {
      setOpen(false);
      setEditing(null);
      setForm(emptyForm);
      void qc.invalidateQueries({ queryKey: ['opportunities'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const openCreate = () => {
    setError(null);
    setEditing(null);
    setForm(emptyForm);
    setLeadPick(null);
    setCustomerPick(null);
    setOpen(true);
  };

  const reopen = useMutation({
    mutationFn: (id: number) => reopenOpportunity(id),
    onSuccess: () => {
      setConfirmReopen(false);
      setOpen(false);
      setEditing(null);
      void qc.invalidateQueries({ queryKey: ['opportunities'] });
    },
    onError: (err) => {
      setConfirmReopen(false);
      setError(getErrorMessage(err));
    },
  });

  // Moving a deal to Won or Lost is terminal, so it asks first, like the Pipeline board does.
  const requestSave = () => {
    const closing = (form.stage === 'WON' || form.stage === 'LOST') && (!editing || editing.stage !== form.stage);
    if (closing) setConfirmClose(true);
    else saveMutation.mutate();
  };

  const openEdit = (opp: Opportunity) => {
    setError(null);
    setEditing(opp);
    setForm({
      title: opp.title,
      amount: opp.amount ?? '',
      stage: opp.stage ?? 'OPEN',
      lead: opp.lead ?? '',
      customer: opp.customer ?? '',
      competitor: opp.competitor ?? '',
      lostReason: opp.lostReason ?? '',
      lostReasonNote: opp.lostReasonNote ?? '',
    });
    setLeadPick(opp.lead ? { id: opp.lead, name: opp.leadName ?? `#${opp.lead}` } : null);
    setCustomerPick(opp.customer ? ({ id: opp.customer, name: opp.customerName ?? `#${opp.customer}` } as Customer) : null);
    setOpen(true);
  };

  return (
    <Stack spacing={2}>
      <MvpModuleBanner module="crm" />
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <PageTitle>{t('nav.opportunities')}</PageTitle>
        <Button variant="contained" onClick={openCreate} disabled={writesBlocked}>
          {t('common.add')}
        </Button>
      </Stack>
      {error ? <HelpErrorAlert message={error} /> : null}
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {rows.length === 0 && !query.isLoading && !query.isError ? (
        <EmptyState description={t('empty.opportunities')} />
      ) : null}
      {rows.length > 0 ? (
        <Paper tabIndex={0} role="region" aria-label={t('common.scrollableTable')} sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('erp.title')}</TableCell>
                <TableCell>{t('nav.leads')}</TableCell>
                <TableCell>{t('nav.customers')}</TableCell>
                <TableCell align="right">{t('common.amount')}</TableCell>
                <TableCell>{t('growth.competitor')}</TableCell>
                <TableCell>{t('erp.stage')}</TableCell>
                <TableCell align="right">{t('common.actions')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((opp) => (
                <TableRow key={opp.id}>
                  <TableCell>{opp.title}</TableCell>
                  <TableCell>{opp.lead ? opp.leadName ?? `#${opp.lead}` : '—'}</TableCell>
                  <TableCell>
                    {opp.customer ? opp.customerName ?? `#${opp.customer}` : '—'}
                  </TableCell>
                  <TableCell align="right">{formatMoney(opp.amount)}</TableCell>
                  <TableCell>{opp.competitor || '—'}</TableCell>
                  <TableCell>
                    <StatusChip
                      tone={documentStatusTone(opp.stage ?? 'OPEN')}
                      labelKey={statusLabelKey(opp.stage ?? 'OPEN')}
                    />
                  </TableCell>
                  <TableCell align="right">
                    <Button size="small" onClick={() => openEdit(opp)} disabled={writesBlocked}>
                      {t('common.edit')}
                    </Button>
                    {opp.stage === 'WON' ? (
                      <>
                        <Button
                          size="small"
                          onClick={() => {
                            void createQuotationFromOpportunity(opp.id)
                              .then((quotation) => navigate(`/sales/quotations/${quotation.id}`))
                              .catch((err) => setError(getErrorMessage(err)));
                          }}
                        >
                          {t('osPlan.createQuotation')}
                        </Button>
                        <Button
                          size="small"
                          onClick={() => {
                            void draftOpportunityInvoice(opp.id)
                              .then((invoice) => navigate(`/sales/history/${invoice.id}`))
                              .catch((err) => setError(getErrorMessage(err)));
                          }}
                        >
                          {t('growth.createDraftInvoice')}
                        </Button>
                      </>
                    ) : null}
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
        <DialogTitle>{editing ? t('common.edit') : t('common.create')} opportunity</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {error ? <HelpErrorAlert message={error} /> : null}
            {isClosed ? <Typography variant="body2" color="text.secondary">{t('growth.closedDealNote')}</Typography> : null}
            <TextField
              label={t('erp.title')}
              required
              disabled={isClosed}
              value={form.title}
              onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
            />
            <TextField
              label={t('common.amount')}
              type="number"
              disabled={isClosed}
              inputProps={{ min: 0, step: '0.01' }}
              value={form.amount}
              onChange={(e) => setForm((f) => ({ ...f, amount: e.target.value }))}
            />
            <TextField
              select
              label={t('erp.stage')}
              disabled={isClosed}
              value={form.stage}
              onChange={(e) => setForm((f) => ({ ...f, stage: e.target.value as Stage }))}
            >
              {STAGES.map((s) => (
                <MenuItem key={s} value={s}>
                  {t(statusLabelKey(s))}
                </MenuItem>
              ))}
            </TextField>
            <LeadField
              value={leadPick}
              disabled={isClosed}
              onChange={(lead) => {
                setLeadPick(lead);
                setForm((f) => ({ ...f, lead: lead?.id ?? '' }));
              }}
            />
            <CustomerField
              value={customerPick}
              disabled={isClosed}
              onChange={(customer) => {
                setCustomerPick(customer);
                setForm((f) => ({ ...f, customer: customer?.id ?? '' }));
              }}
            />
            <TextField
              label={t('growth.competitor')}
              value={form.competitor}
              onChange={(e) => setForm((f) => ({ ...f, competitor: e.target.value }))}
              inputProps={{ maxLength: 120 }}
            />
            {form.stage === 'LOST' && !isClosed ? (
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
                    label={t('growth.lostReasonNote')}
                    value={form.lostReasonNote}
                    onChange={(e) => setForm((f) => ({ ...f, lostReasonNote: e.target.value }))}
                    inputProps={{ maxLength: 200 }}
                  />
                ) : null}
              </>
            ) : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          {isClosed && canReopen && editing ? (
            <Button color="warning" disabled={writesBlocked || reopen.isPending} onClick={() => setConfirmReopen(true)}>
              {t('growth.reopenDeal')}
            </Button>
          ) : null}
          <Button onClick={() => setOpen(false)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={!form.title || saveMutation.isPending || writesBlocked}
            onClick={requestSave}
          >
            {t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>
      <ConfirmDialog
        open={confirmClose}
        title={form.stage === 'LOST'
          ? t('cog.confirmLost', { name: form.title })
          : t('cog.confirmWon', { name: form.title })}
        body={t('growth.convertWonWarning')}
        onClose={() => setConfirmClose(false)}
        onConfirm={() => {
          setConfirmClose(false);
          saveMutation.mutate();
        }}
      />
      <ConfirmDialog
        open={confirmReopen}
        title={t('growth.reopenConfirmTitle', { name: editing?.title ?? '' })}
        body={t('growth.reopenConfirmBody')}
        confirming={reopen.isPending}
        onClose={() => setConfirmReopen(false)}
        onConfirm={() => {
          if (editing) reopen.mutate(editing.id);
        }}
      />
    </Stack>
  );
}
