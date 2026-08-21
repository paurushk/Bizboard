import { useMemo, useState } from 'react';
import Alert from '@mui/material/Alert';
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
  createOpportunity,
  listLeadsPage,
  listOpportunitiesPage,
  updateOpportunity,
  type Opportunity,
} from '@/api/crm';
import { listCustomersPage } from '@/api/resources';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { StatusChip } from '@/components/StatusChip';
import { t } from '@/i18n';
import { ModuleGate, MvpModuleBanner } from '@/pages/erp/erpShared';
import { formatMoney } from '@/utils/money';
import { documentStatusTone, statusLabelKey } from '@/utils/status';

const PAGE_SIZE = 50;
const STAGES = ['OPEN', 'WON', 'LOST'] as const;

const emptyForm = {
  title: '',
  amount: '',
  stage: 'OPEN',
  lead: '' as number | '',
  customer: '' as number | '',
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
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Opportunity | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ['opportunities', page],
    queryFn: () => listOpportunitiesPage({ page, pageSize: PAGE_SIZE }),
  });
  const leadsQuery = useQuery({
    queryKey: ['leads', 'all'],
    queryFn: () => listLeadsPage({ page: 1, pageSize: 200 }),
  });
  const customersQuery = useQuery({
    queryKey: ['customers', 'crm'],
    queryFn: () => listCustomersPage({ page: 1, pageSize: 200 }),
  });

  const leadMap = useMemo(() => {
    const map = new Map<number, string>();
    for (const l of leadsQuery.data?.results ?? []) map.set(l.id, l.name);
    return map;
  }, [leadsQuery.data]);

  const customerMap = useMemo(() => {
    const map = new Map<number, string>();
    for (const c of customersQuery.data?.results ?? []) map.set(c.id, c.name);
    return map;
  }, [customersQuery.data]);

  const rows = query.data?.results ?? [];

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        title: form.title,
        amount: form.amount || '0',
        stage: form.stage,
        lead: form.lead ? Number(form.lead) : null,
        customer: form.customer ? Number(form.customer) : null,
      };
      if (editing) return updateOpportunity(editing.id, payload);
      return createOpportunity(payload);
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
    setEditing(null);
    setForm(emptyForm);
    setOpen(true);
  };

  const openEdit = (opp: Opportunity) => {
    setEditing(opp);
    setForm({
      title: opp.title,
      amount: opp.amount,
      stage: opp.stage,
      lead: opp.lead ?? '',
      customer: opp.customer ?? '',
    });
    setOpen(true);
  };

  return (
    <Stack spacing={2}>
      <MvpModuleBanner module="crm" />
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="h4">{t('nav.opportunities')}</Typography>
        <Button variant="contained" onClick={openCreate}>
          {t('common.add')}
        </Button>
      </Stack>
      {error ? <Alert severity="error">{error}</Alert> : null}
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} onRetry={() => void query.refetch()} />
      ) : null}
      {rows.length === 0 && !query.isLoading && !query.isError ? (
        <EmptyState description={t('empty.opportunities')} />
      ) : null}
      {rows.length > 0 ? (
        <Paper sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('erp.title')}</TableCell>
                <TableCell>{t('nav.leads')}</TableCell>
                <TableCell>{t('nav.customers')}</TableCell>
                <TableCell align="right">{t('common.amount')}</TableCell>
                <TableCell>{t('erp.stage')}</TableCell>
                <TableCell align="right">{t('common.actions')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((opp) => (
                <TableRow key={opp.id}>
                  <TableCell>{opp.title}</TableCell>
                  <TableCell>{opp.lead ? leadMap.get(opp.lead) ?? opp.lead : '—'}</TableCell>
                  <TableCell>
                    {opp.customer ? customerMap.get(opp.customer) ?? opp.customer : '—'}
                  </TableCell>
                  <TableCell align="right">{formatMoney(opp.amount)}</TableCell>
                  <TableCell>
                    <StatusChip
                      tone={documentStatusTone(opp.stage)}
                      labelKey={statusLabelKey(opp.stage)}
                    />
                  </TableCell>
                  <TableCell align="right">
                    <Button size="small" onClick={() => openEdit(opp)}>
                      {t('common.edit')}
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
        <DialogTitle>{editing ? t('common.edit') : t('common.create')} opportunity</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label={t('erp.title')}
              required
              value={form.title}
              onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
            />
            <TextField
              label={t('common.amount')}
              type="number"
              value={form.amount}
              onChange={(e) => setForm((f) => ({ ...f, amount: e.target.value }))}
            />
            <TextField
              select
              label={t('erp.stage')}
              value={form.stage}
              onChange={(e) => setForm((f) => ({ ...f, stage: e.target.value }))}
            >
              {STAGES.map((s) => (
                <MenuItem key={s} value={s}>
                  {t(statusLabelKey(s))}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label={t('nav.leads')}
              value={form.lead}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  lead: e.target.value ? Number(e.target.value) : '',
                }))
              }
            >
              <MenuItem value="">—</MenuItem>
              {(leadsQuery.data?.results ?? []).map((l) => (
                <MenuItem key={l.id} value={l.id}>
                  {l.name}
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
            disabled={!form.title || saveMutation.isPending}
            onClick={() => saveMutation.mutate()}
          >
            {t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
