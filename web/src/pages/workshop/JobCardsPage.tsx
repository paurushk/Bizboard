import { useState } from 'react';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { convertJobCard, createJobCard, listJobCards } from '@/api/roadmap';
import { isWorkshopEnabled } from '@/config/features';
import { PageTitle } from '@/contextHelp';
import { t } from '@/i18n';
import { CustomerField } from '@/pages/growth/widgets';
import { PageShell } from '@/pages/phase/phaseShared';
import type { Customer } from '@/types/domain';

function rowsOf(data: unknown): Record<string, unknown>[] {
  if (Array.isArray(data)) return data as Record<string, unknown>[];
  const results = (data as { results?: Record<string, unknown>[] } | null)?.results;
  return results ?? [];
}

export function JobCardsPage() {
  if (!isWorkshopEnabled()) {
    return <PageShell title={t('nav.jobCards')}><Typography>{t('erp.moduleDisabled')}</Typography></PageShell>;
  }
  return <JobCardsInner />;
}

function JobCardsInner() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [complaint, setComplaint] = useState('');
  const [error, setError] = useState('');
  const list = useQuery({ queryKey: ['job-cards'], queryFn: listJobCards });
  const create = useMutation({
    mutationFn: () => createJobCard({ customer: customer!.id, complaint }),
    onSuccess: () => {
      setComplaint('');
      void qc.invalidateQueries({ queryKey: ['job-cards'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const convert = useMutation({
    mutationFn: (id: number) => convertJobCard(id),
    onSuccess: (row) => {
      const invoiceId = Number(row.salesInvoice);
      if (invoiceId) navigate(`/sales/invoices/${invoiceId}`);
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  return (
    <Stack spacing={2}>
      <PageTitle>{t('nav.jobCards')}</PageTitle>
      <Typography variant="body2" color="text.secondary">{t('growth.jobCard')}</Typography>
      {error ? <Typography color="error">{error}</Typography> : null}
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1}>
        <CustomerField value={customer} onChange={setCustomer} />
        <TextField size="small" label="Complaint" value={complaint} onChange={(e) => setComplaint(e.target.value)} />
        <Button variant="contained" disabled={!customer || create.isPending} onClick={() => create.mutate()}>{t('growth.create')}</Button>
      </Stack>
      {rowsOf(list.data).map((row) => (
        <Stack key={String(row.id)} direction="row" spacing={1} alignItems="center">
          <Typography>{String(row.number)} · {String(row.status)}</Typography>
          {Array.isArray(row.serialHistory) && (row.serialHistory as Array<{ serialId?: number; capped?: boolean; jobs?: Array<{ id: number; number: string; status?: string; date?: string }> }>).map((group) => (
            <Typography key={String(group.serialId)} variant="caption">
              {t('growth.serialHistory')}
              {group.capped ? ` · ${t('growth.serialHistoryCapped')}` : ''}
              {(group.jobs ?? []).map((job) => (
                <span key={job.id}>{` ${job.number} · ${t('common.status')}: ${job.status} · ${t('common.date')}: ${job.date}`}</span>
              ))}
            </Typography>
          ))}
          {row.status !== 'INVOICED' && row.status !== 'CANCELLED' ? (
            <Button size="small" onClick={() => convert.mutate(Number(row.id))}>Invoice</Button>
          ) : null}
        </Stack>
      ))}
    </Stack>
  );
}
