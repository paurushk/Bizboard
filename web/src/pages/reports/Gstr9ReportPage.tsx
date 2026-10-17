import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { downloadGstr9, getGstr9, getGstr9FilingDate, setGstr9FilingDate } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { GstHonestyHeader } from '@/components/GstHonestyHeader';
import { ErrorState, LoadingState } from '@/components/PageState';
import { PageTitle } from '@/contextHelp';
import { t } from '@/i18n';
import { formatMoney } from '@/utils/money';
import { canExport } from '@/utils/permissions';

function defaultFy(): string {
  const now = new Date();
  const year = now.getMonth() + 1 >= 4 ? now.getFullYear() : now.getFullYear() - 1;
  const end = String((year + 1) % 100).padStart(2, '0');
  return `${year}-${end}`;
}

function isCompositionUnavailableError(message: string): boolean {
  const m = message.toLowerCase();
  return (
    m.includes('composition') ||
    m.includes('cmp-08') ||
    m.includes('not available')
  );
}

export function Gstr9ReportPage() {
  const { user } = useAuth();
  const [fy, setFy] = useState(defaultFy());
  const query = useQuery({
    queryKey: ['gstr9', fy],
    queryFn: () => getGstr9({ fy }),
  });
  const queryClient = useQueryClient();
  const filing = useQuery({
    queryKey: ['gstr9-filing-date', fy],
    queryFn: () => getGstr9FilingDate(fy),
    enabled: /^\d{4}-\d{2}$/.test(fy),
    retry: false,
  });
  const [draft, setDraft] = useState<{ fy: string; value: string } | null>(null);
  const filedOn = draft && draft.fy === fy ? draft.value : (filing.data?.filedOn ?? '');
  const setFiledOn = (value: string) => setDraft({ fy, value });
  const filingMutation = useMutation({
    mutationFn: () => setGstr9FilingDate(fy, filedOn || null),
    onSuccess: () => {
      setDraft(null);
      void queryClient.invalidateQueries({ queryKey: ['gstr9-filing-date'] });
    },
  });
  const exportMutation = useMutation({
    mutationFn: () => downloadGstr9({ fy, format: 'xlsx' }),
    onSuccess: (result) => {
      const a = document.createElement('a');
      a.href = result.url;
      a.download = `gstr9-${fy}.xlsx`;
      a.click();
      URL.revokeObjectURL(result.url);
    },
    onError: () => undefined, // surfaced by the isError alert (F3-031)
  });

  const annual = (query.data?.annual ?? {}) as Record<string, string>;
  const tables = (query.data?.tables ?? {}) as Record<string, Record<string, string>>;
  const queryErrorMessage = query.isError ? getErrorMessage(query.error) : '';
  const compositionBlocked = query.isError && isCompositionUnavailableError(queryErrorMessage);

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1}>
        <PageTitle>{t('nav.gstr9')}</PageTitle>
        <Stack direction="row" spacing={1}>
          <TextField
            size="small"
            label={t('reports.fy')}
            value={fy}
            onChange={(e) => setFy(e.target.value)}
            helperText={t('sweep.fyExample')}
          />
          {canExport(user) ? (
            <Button
              variant="outlined"
              disabled={exportMutation.isPending}
              onClick={() => exportMutation.mutate()}
            >
              {t('common.export')}
            </Button>
          ) : null}
        </Stack>
      </Stack>
      <GstHonestyHeader />
      <Alert severity="info">{t('reports.gstr9Disclaimer')}</Alert>
      <Alert severity="warning">{t('reports.gstr9Tables67Worksheet')}</Alert>
      {filing.data ? (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} alignItems={{ sm: 'flex-start' }}>
            <TextField
              size="small"
              type="date"
              label={t('reports.gstr9FiledOn')}
              value={filedOn}
              onChange={(e) => setFiledOn(e.target.value)}
              InputLabelProps={{ shrink: true }}
              helperText={t('reports.gstr9FiledOnHelp', { date: filing.data.noteDeadline })}
              sx={{ minWidth: 220 }}
            />
            <Button
              variant="outlined"
              disabled={filingMutation.isPending || filedOn === (filing.data.filedOn ?? '')}
              onClick={() => filingMutation.mutate()}
              sx={{ minHeight: 44 }}
            >
              {t('common.save')}
            </Button>
          </Stack>
          {filingMutation.isError ? (
            <Alert severity="error" sx={{ mt: 1 }}>{getErrorMessage(filingMutation.error)}</Alert>
          ) : null}
        </Paper>
      ) : null}
      {exportMutation.isError ? (
        <Alert severity="error">{getErrorMessage(exportMutation.error)}</Alert>
      ) : null}
      {compositionBlocked ? (
        <Alert
          severity="warning"
          action={
            <Stack direction="row" spacing={1}>
              <Button color="inherit" size="small" component={RouterLink} to="/reports/cmp08">
                {t('gstHonesty.openCmp08')}
              </Button>
              <Button color="inherit" size="small" component={RouterLink} to="/reports/gstr4">
                {t('gstHonesty.openGstr4')}
              </Button>
            </Stack>
          }
        >
          {t('gstHonesty.compositionUseAids')}
        </Alert>
      ) : null}
      {query.isLoading ? <LoadingState /> : null}
      {query.isError && !compositionBlocked ? (
        <ErrorState message={queryErrorMessage} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {query.data ? (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Typography fontWeight={600} gutterBottom>
            {t('reports.annualSummary')}
          </Typography>
          <Typography>
            {t('reports.outwardTaxable')}: {formatMoney(annual.outward_taxable ?? annual.outwardTaxable ?? '0')}
          </Typography>
          <Typography>
            {t('reports.outwardTax')}: {formatMoney(annual.outward_tax ?? annual.outwardTax ?? '0')}
          </Typography>
          <Typography>
            {t('reports.inwardTaxable')}: {formatMoney(annual.inward_taxable ?? annual.inwardTaxable ?? '0')}
          </Typography>
          <Typography>
            {t('reports.inwardTax')}: {formatMoney(annual.inward_tax ?? annual.inwardTax ?? '0')}
          </Typography>
          <Typography sx={{ mt: 1 }}>
            Table 6 ITC (claimable books):{' '}
            {formatMoney(tables['6']?.tax ?? '0')}
          </Typography>
          <Typography>
            Table 7 ITC reversal (purchase CN):{' '}
            {formatMoney(tables['7']?.tax ?? '0')}
          </Typography>
          <Typography>
            Table 8 ITC as per 2B: {formatMoney(tables['8']?.itc_as_per_2b ?? tables['8']?.itcAsPer2b ?? '0')}
          </Typography>
          <Typography>
            Table 8 ITC as per books: {formatMoney(tables['8']?.itc_as_per_books ?? tables['8']?.itcAsPerBooks ?? '0')}
          </Typography>
          <Typography>
            Table 8 imports IGST: {formatMoney(tables['8']?.imports_igst ?? tables['8']?.importsIgst ?? '0')}
          </Typography>
        </Paper>
      ) : null}
    </Stack>
  );
}
