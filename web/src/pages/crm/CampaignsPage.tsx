import { useState } from 'react';
import Button from '@mui/material/Button';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import {
  createCampaign,
  deleteCampaign,
  getCampaignFunnel,
  listCampaignsPage,
  updateCampaign,
  type Campaign,
  type Funnel,
} from '@/api/growth';
import { PageTitle } from '@/contextHelp';
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
  const [funnel, setFunnel] = useState<Funnel | null>(null);
  const [error, setError] = useState('');
  const list = useQuery({ queryKey: ['campaigns'], queryFn: () => listCampaignsPage({ pageSize: 100 }) });
  const rows = list.data?.results ?? [];

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
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={1.5}>
          <Typography variant="subtitle2">{editing ? t('growth.detail') : t('growth.create')}</Typography>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} useFlexGap flexWrap="wrap">
            <TextField size="small" label={t('growth.name')} value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
            <TextField select size="small" label={t('growth.type')} value={draft.campaignType} onChange={(e) => setDraft({ ...draft, campaignType: e.target.value })} sx={{ minWidth: 160 }}>
              {TYPES.map((value) => <MenuItem key={value} value={value}>{value}</MenuItem>)}
            </TextField>
            <TextField select size="small" label={t('growth.status')} value={draft.status} onChange={(e) => setDraft({ ...draft, status: e.target.value })} sx={{ minWidth: 140 }}>
              {STATUSES.map((value) => <MenuItem key={value} value={value}>{value}</MenuItem>)}
            </TextField>
            <TextField select size="small" label={t('growth.parent')} value={draft.parent} onChange={(e) => setDraft({ ...draft, parent: e.target.value })} sx={{ minWidth: 180 }}>
              <MenuItem value="">{t('growth.none')}</MenuItem>
              {rows.filter((row) => row.id !== editing).map((row) => <MenuItem key={row.id} value={String(row.id)}>{row.name}</MenuItem>)}
            </TextField>
            <TextField size="small" label={t('growth.budget')} value={draft.budget} onChange={(e) => setDraft({ ...draft, budget: e.target.value })} />
            <TextField size="small" label={t('growth.target')} value={draft.targetRevenue} onChange={(e) => setDraft({ ...draft, targetRevenue: e.target.value })} />
            <TextField size="small" type="date" label={t('growth.startDate')} value={draft.startDate} onChange={(e) => setDraft({ ...draft, startDate: e.target.value })} InputLabelProps={{ shrink: true }} />
            <TextField size="small" type="date" label={t('growth.endDate')} value={draft.endDate} onChange={(e) => setDraft({ ...draft, endDate: e.target.value })} InputLabelProps={{ shrink: true }} />
          </Stack>
          <TextField size="small" label={t('growth.expectedOutcome')} value={draft.expectedOutcome} onChange={(e) => setDraft({ ...draft, expectedOutcome: e.target.value })} />
          <Stack direction="row" spacing={1}>
            <Button variant="contained" disabled={!draft.name.trim() || save.isPending} onClick={() => save.mutate()}>{t('growth.save')}</Button>
            {editing ? <Button onClick={() => { setEditing(null); setDraft(emptyDraft); setFunnel(null); }}>{t('growth.close')}</Button> : null}
            {editing ? <Button color="warning" onClick={() => remove.mutate(editing)}>{t('growth.remove')}</Button> : null}
          </Stack>
          {error ? <Typography color="error">{error}</Typography> : null}
        </Stack>
      </Paper>
      {rows.map((row) => (
        <Paper key={row.id} variant="outlined" sx={{ p: 1.5 }}>
          <Stack direction="row" justifyContent="space-between" alignItems="center">
            <Typography>{row.name} · {row.campaignType} · {row.status}</Typography>
            <Button size="small" onClick={() => load(row)}>{t('growth.funnel')}</Button>
          </Stack>
        </Paper>
      ))}
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
        {t('growth.revenue')}: {funnel.revenue} · {t('growth.budget')}: {funnel.budget} · {t('growth.variance')}: {funnel.variance}
        {funnel.roiRatio != null ? ` · ${t('growth.roi')} ${funnel.roiRatio}` : ''}
        {funnel.targetRevenue != null ? ` · ${t('growth.target')} ${funnel.targetRevenue}` : ''}
      </Typography>
      {(funnel.rows ?? []).map((row) => (
        <Typography key={`${row.opportunity}-${row.revenueSource}`} variant="caption" display="block">
          #{row.opportunity} · {row.revenueSource === 'quotation_total' ? t('growth.quotationTotal') : t('growth.opportunityAmount')} · {row.revenue}
        </Typography>
      ))}
    </Paper>
  );
}
