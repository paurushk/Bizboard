import { useState } from 'react';
import Box from '@mui/material/Box';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { careKpis } from '@/api/care';
import { EmptyState, ErrorState, ListSkeleton } from '@/components/PageState';
import { t } from '@/i18n';
import { formatSpan } from '@/care/format';
import { CareHeader, Field } from '@/care/kit';
import { formatMoney } from '@/utils/money';

type Section = Record<string, unknown>;
const DAYS = [30, 90, 180, 365] as const;

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Paper variant="outlined" sx={{ p: 2, flex: '1 1 320px', minWidth: 0 }} component="section" aria-label={title}>
      <Typography variant="subtitle1" component="h2" gutterBottom>{title}</Typography>
      <Stack direction="row" spacing={3} flexWrap="wrap" useFlexGap>{children}</Stack>
    </Paper>
  );
}

const num = (value: unknown) => (value == null ? '—' : String(value));

/** How the service side of the business is doing: tickets, complaints, workshop, projects and contracts (XLK-06). */
export function ServiceQualityPage() {
  const [days, setDays] = useState<number>(90);
  const kpis = useQuery({ queryKey: ['care-kpis', days], queryFn: () => careKpis(days) });
  const data = kpis.data as Record<string, Section> | undefined;
  const sections = data ? ['tickets', 'complaints', 'workshop', 'projects', 'contracts'].filter((key) => data[key]) : [];
  return (
    <Stack spacing={2}>
      <CareHeader
        title={t('nav.serviceQuality')}
        subtitle={t('care.quality.subtitle')}
        actions={
          <TextField select size="small" label={t('care.quality.period')} value={days} onChange={(e) => setDays(Number(e.target.value))} sx={{ minWidth: 180 }}>
            {DAYS.map((value) => <MenuItem key={value} value={value}>{t('care.quality.lastDays', { days: value })}</MenuItem>)}
          </TextField>
        }
      />
      {kpis.isLoading ? <ListSkeleton rows={4} /> : null}
      {kpis.isError ? <ErrorState message={getErrorMessage(kpis.error)} error={kpis.error} onRetry={() => void kpis.refetch()} /> : null}
      {data && sections.length === 0 ? <EmptyState description={t('care.quality.none')} /> : null}
      <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
        {data?.tickets ? (
          <Card title={t('nav.tickets')}>
            <Field label={t('care.quality.opened')}>{num(data.tickets.opened)}</Field>
            <Field label={t('care.quality.resolved')}>{num(data.tickets.resolved)}</Field>
            <Field label={t('care.quality.slaMet')}>{data.tickets.slaMetPercent == null ? '—' : `${data.tickets.slaMetPercent}%`}</Field>
            <Field label={t('care.quality.avgResolve')}>{formatSpan(data.tickets.averageResolutionSeconds as number | null) || '—'}</Field>
            <Field label={t('care.quality.openNow')}>{num(data.tickets.openNow)}</Field>
          </Card>
        ) : null}
        {data?.complaints ? (
          <Card title={t('nav.complaints')}>
            <Field label={t('care.quality.logged')}>{num(data.complaints.customerTotal)}</Field>
            <Field label={t('care.quality.resolved')}>{num(data.complaints.customerResolved)}</Field>
            <Field label={t('care.quality.rejected')}>{num(data.complaints.customerRejected)}</Field>
            <Field label={t('nav.supplierComplaints')}>{num(data.complaints.supplierTotal)}</Field>
            {((data.complaints.repeatProducts as { product: number; name: string; complaints: number }[]) ?? []).length ? (
              <Box sx={{ width: '100%' }}>
                <Typography variant="caption" color="text.secondary">{t('care.quality.repeatProducts')}</Typography>
                {(data.complaints.repeatProducts as { product: number; name: string; complaints: number }[]).map((row) => (
                  <Typography key={row.product} variant="body2">{row.name}: {row.complaints}</Typography>
                ))}
              </Box>
            ) : null}
            {((data.complaints.bySupplier as { supplier: number; supplierName: string; count: number }[]) ?? []).length ? (
              <Box sx={{ width: '100%' }}>
                <Typography variant="caption" color="text.secondary">{t('care.quality.bySupplier')}</Typography>
                {(data.complaints.bySupplier as { supplier: number; supplierName: string; count: number }[]).map((row) => (
                  <Typography key={row.supplier} variant="body2">{row.supplierName}: {row.count}</Typography>
                ))}
              </Box>
            ) : null}
          </Card>
        ) : null}
        {data?.workshop ? (
          <Card title={t('nav.jobCards')}>
            <Field label={t('care.quality.jobs')}>{num(data.workshop.jobs)}</Field>
            <Field label={t('care.quality.invoicedJobs')}>{num(data.workshop.invoiced)}</Field>
            <Field label={t('care.quality.underContract')}>{num(data.workshop.withContract)}</Field>
            <Field label={t('care.quality.freeLines')}>{num(data.workshop.freeLines)}</Field>
            <Field label={t('care.quality.paidLines')}>{num(data.workshop.paidLines)}</Field>
            <Field label={t('care.quality.warrantyCost')}>{formatMoney(String(data.workshop.warrantyCostAtListPrice ?? '0'))}</Field>
          </Card>
        ) : null}
        {data?.projects ? (
          <Card title={t('nav.projects')}>
            <Field label={t('care.quality.openProjects')}>{num(data.projects.openProjects)}</Field>
            <Field label={t('care.projects.planned')}>{formatMoney(String(data.projects.plannedTotal ?? '0'))}</Field>
            <Field label={t('care.projects.invoiced')}>{formatMoney(String(data.projects.invoicedTotal ?? '0'))}</Field>
            <Field label={t('care.quality.overdueMilestones')}>{num(data.projects.overdueMilestones)}</Field>
          </Card>
        ) : null}
        {data?.contracts ? (
          <Card title={t('nav.contracts')}>
            <Field label={t('care.quality.liveContracts')}>{num(data.contracts.live)}</Field>
            <Field label={t('care.quality.endingSoon')}>{num(data.contracts.expiring)}</Field>
            <Field label={t('care.quality.endedContracts')}>{num(data.contracts.expired)}</Field>
          </Card>
        ) : null}
      </Box>
    </Stack>
  );
}
