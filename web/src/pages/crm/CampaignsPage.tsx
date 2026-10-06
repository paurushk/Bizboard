import { useState } from 'react';
import Button from '@mui/material/Button';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import {
  createCampaign,
  deleteCampaign,
  getCampaignFunnel,
  listCampaignsPage,
  updateCampaign,
  type Campaign,
  type Funnel,
} from '@/api/growth';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { CreateDialog } from '@/components/CreateDialog';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { PageTitle } from '@/contextHelp';
import { enumLabel } from '@/utils/enumLabels';
import { formatMoney } from '@/utils/money';
import { t } from '@/i18n';
import { ModuleGate } from '@/pages/erp/erpShared';

const TYPES = ['DIGITAL', 'REFERRAL', 'EVENT', 'MARKET_VISIT'] as const;
const STATUSES = ['DRAFT', 'ACTIVE', 'PAUSED', 'COMPLETED'] as const;

const emptyDraft = {
  name: '',
  campaignType: 'DIGITAL',
  status: 'DRAFT',
  parent: '',
  budget: '0',
  targetRevenue: '',
  expectedOutcome: '',
  startDate: '',
  endDate: '',
};

export function CampaignsPage() {
  return (
    <ModuleGate module="crm" title={t('nav.campaigns')}>
      <CampaignsInner />
    </ModuleGate>
  );
}

function CampaignsInner() {
  const qc = useQueryClient();
  const [draft, setDraft] = useState(emptyDraft);
  const [editing, setEditing] = useState<number | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState('');
  const [pendingDelete, setPendingDelete] = useState<Campaign | null>(null);
  const [more, setMore] = useState(false);
  const [funnel, setFunnel] = useState<Funnel | null>(null);
  const [error, setError] = useState('');
  const term = useDebouncedValue(q, 300).trim();
  const list = useQuery({
    queryKey: ['campaigns', page, term],
    queryFn: () => listCampaignsPage({ page, pageSize: 20, q: term || undefined }),
  });
  const rows = list.data?.results ?? [];
  // The parent choice must not depend on the page or the search text on screen.
  const parentChoices = useQuery({
    queryKey: ['campaigns-parent-choices'],
    queryFn: () => listCampaignsPage({ page: 1, pageSize: 100 }),
  });

  const save = useMutation({
    mutationFn: () => {
      const payload = {
        name: draft.name,
        campaign_type: draft.campaignType,
        status: draft.status,
        parent: draft.parent ? Number(draft.parent) : null,
        budget: draft.budget || '0',
        target_revenue: draft.targetRevenue || null,
        expected_outcome: draft.expectedOutcome,
        start_date: draft.startDate || null,
        end_date: draft.endDate || null,
      };
      return editing ? updateCampaign(editing, payload) : createCampaign(payload);
    },
    onSuccess: () => {
      setDraft(emptyDraft);
      setEditing(null);
      setCreateOpen(false);
      setMore(false);
      setFunnel(null);
      setError('');
      void qc.invalidateQueries({ queryKey: ['campaigns'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const remove = useMutation({
    mutationFn: (id: number) => deleteCampaign(id),
    onSuccess: () => {
      setEditing(null);
      setFunnel(null);
      void qc.invalidateQueries({ queryKey: ['campaigns'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const load = (row: Campaign) => {
    setEditing(row.id);
    setDraft({
      name: row.name,
      campaignType: row.campaignType,
      status: row.status,
      parent: row.parent ? String(row.parent) : '',
      budget: row.budget,
      targetRevenue: row.targetRevenue ?? '',
      expectedOutcome: row.expectedOutcome ?? '',
      startDate: row.startDate ?? '',
      endDate: row.endDate ?? '',
    });
    setError('');
    void getCampaignFunnel(row.id).then(setFunnel).catch((err) => setError(getErrorMessage(err)));
  };

  return (
    <Stack spacing={2}>
      <PageTitle>{t('nav.campaigns')}</PageTitle>
      <Typography variant="body2" color="text.secondary">{t('growth.campaignHonesty')}</Typography>
      <TextField size="small" label={t('cog.searchGrowth')} value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
      <Button sx={{ alignSelf: 'flex-start' }} variant="contained" onClick={() => { setEditing(null); setDraft(emptyDraft); setMore(false); setCreateOpen(true); }}>{t('growth.newCampaign')}</Button>
      <CreateDialog
        open={createOpen}
        onClose={() => { setCreateOpen(false); setEditing(null); setDraft(emptyDraft); setMore(false); }}
        title={editing ? t('growth.detail') : t('growth.newCampaign')}
        submitLabel={t('growth.save')}
        submitDisabled={!draft.name.trim() || save.isPending}
        dirty={draft.name.trim() !== '' || draft.budget !== '0' || draft.expectedOutcome !== ''}
        onSubmit={() => save.mutate()}
      >
        <TextField size="small" label={t('growth.name')} value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
        <TextField select size="small" label={t('growth.type')} value={draft.campaignType} onChange={(e) => setDraft({ ...draft, campaignType: e.target.value })}>
          {TYPES.map((value) => <MenuItem key={value} value={value}>{enumLabel('campaignType', value)}</MenuItem>)}
        </TextField>
        <TextField size="small" type="date" label={t('growth.startDate')} value={draft.startDate} onChange={(e) => setDraft({ ...draft, startDate: e.target.value })} InputLabelProps={{ shrink: true }} />
        <TextField size="small" label={t('growth.budget')} value={draft.budget} onChange={(e) => setDraft({ ...draft, budget: e.target.value })} />
        <Button size="small" onClick={() => setMore((open) => !open)}>{t('growth.more')}</Button>
        {more ? (
          <>
            <TextField select size="small" label={t('growth.status')} value={draft.status} onChange={(e) => setDraft({ ...draft, status: e.target.value })}>
              {STATUSES.map((value) => <MenuItem key={value} value={value}>{enumLabel('campaignStatus', value)}</MenuItem>)}
            </TextField>
            <TextField select size="small" label={t('growth.parent')} value={draft.parent} onChange={(e) => setDraft({ ...draft, parent: e.target.value })}>
              <MenuItem value="">{t('growth.none')}</MenuItem>
              {[...(parentChoices.data?.results ?? [])].filter((row) => row.id !== editing).map((row) => <MenuItem key={row.id} value={String(row.id)}>{row.name}</MenuItem>)}
            </TextField>
            <TextField size="small" label={t('growth.target')} value={draft.targetRevenue} onChange={(e) => setDraft({ ...draft, targetRevenue: e.target.value })} />
            <TextField size="small" type="date" label={t('growth.endDate')} value={draft.endDate} onChange={(e) => setDraft({ ...draft, endDate: e.target.value })} InputLabelProps={{ shrink: true }} />
            <TextField size="small" label={t('growth.expectedOutcome')} value={draft.expectedOutcome} onChange={(e) => setDraft({ ...draft, expectedOutcome: e.target.value })} />
          </>
        ) : null}
        {error ? <Typography color="error">{error}</Typography> : null}
      </CreateDialog>
      {list.isLoading ? <LoadingState /> : null}
      {list.isError ? <ErrorState message={getErrorMessage(list.error)} error={list.error} onRetry={() => void list.refetch()} /> : null}
      {!list.isLoading && !list.isError && rows.length === 0 ? (
        <EmptyState description={t('cog.emptyCampaigns')} action={<Button variant="contained" onClick={() => setCreateOpen(true)}>{t('growth.newCampaign')}</Button>} />
      ) : null}
      {rows.map((row) => (
        <Paper key={row.id} variant="outlined" sx={{ p: 1.5 }}>
          <Stack direction="row" justifyContent="space-between" alignItems="center">
            <Typography>{row.name} · {enumLabel('campaignType', row.campaignType)} · {enumLabel('campaignStatus', row.status)}</Typography>
            <Button size="small" onClick={() => { load(row); setCreateOpen(true); }}>{t('common.edit')}</Button>
            <Button size="small" onClick={() => {
              setError('');
              void getCampaignFunnel(row.id).then(setFunnel).catch((err) => setError(getErrorMessage(err)));
            }}>{t('growth.funnel')}</Button>
            <Button size="small" color="warning" onClick={() => setPendingDelete(row)}>{t('growth.remove')}</Button>
          </Stack>
        </Paper>
      ))}
      <Stack direction="row" spacing={1}>
        <Button size="small" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>{t('common.previous')}</Button>
        <Button size="small" disabled={!list.data?.next} onClick={() => setPage((p) => p + 1)}>{t('common.next')}</Button>
      </Stack>
      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title={t('cog.deleteCampaign', { name: pendingDelete?.name ?? '' })}
        body={pendingDelete?.name ?? ''}
        requireTyped={pendingDelete?.name}
        confirmColor="error"
        onClose={() => setPendingDelete(null)}
        onConfirm={() => {
          if (pendingDelete) remove.mutate(pendingDelete.id);
          setPendingDelete(null);
        }}
      />
      {funnel ? <FunnelBlock title={t('growth.funnel')} funnel={funnel} /> : null}
      {funnel?.rollup ? <FunnelBlock title={t('growth.rollup')} funnel={funnel.rollup} /> : null}
    </Stack>
  );
}

function FunnelBlock({ title, funnel }: { title: string; funnel: Funnel }) {
  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Typography variant="subtitle2">{title}</Typography>
      <Typography variant="body2">
        {t('growth.leads')}: {funnel.leads} · {t('growth.opportunities')}: {funnel.opportunities} · {t('growth.won')}: {funnel.wonOpportunities}
      </Typography>
      <Typography variant="body2">
        {t('growth.revenue')}: {formatMoney(funnel.revenue)} · {t('growth.budget')}: {formatMoney(funnel.budget)} · {t('growth.variance')}: {formatMoney(funnel.variance)}
        {funnel.roiRatio != null ? ` · ${t('growth.roi')} ${funnel.roiRatio}` : ''}
        {funnel.targetRevenue != null ? ` · ${t('growth.target')} ${funnel.targetRevenue}` : ''}
      </Typography>
      {(funnel.rows ?? []).map((row) => (
        <Typography key={`${row.opportunity}-${row.revenueSource}`} variant="caption" display="block">
          #{row.opportunity} · {row.revenueSource === 'quotation_total'
            ? t('growth.quotationTotal')
            : row.revenueSource === 'completed_invoice_taxable_net'
              ? t('growth.completedInvoiceNet')
              : row.revenueSource === 'no_completed_invoice'
                ? t('growth.noCompletedInvoice')
                : t('growth.opportunityAmount')} · {row.revenue}
        </Typography>
      ))}
    </Paper>
  );
}
