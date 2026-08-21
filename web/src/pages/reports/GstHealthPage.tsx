import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import { useQuery } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { getGstHealth } from '@/api/resources';
import { AlertInboxRow, PageHeader, SeverityChip } from '@/components/insights';
import { ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';

function currentPeriod(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  return `${now.getFullYear()}-${month}`;
}

export function GstHealthPage() {
  const [period, setPeriod] = useState(currentPeriod());
  const query = useQuery({
    queryKey: ['gst-health', period],
    queryFn: () => getGstHealth({ period }),
  });

  const summary = query.data?.summary;
  const alerts = query.data?.alerts ?? [];

  return (
    <Stack spacing={2}>
      <PageHeader
        title={t('nav.gstHealth')}
        controls={
          <TextField
            type="month"
            size="small"
            label={t('reports.period')}
            InputLabelProps={{ shrink: true }}
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
          />
        }
      />

      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} onRetry={() => void query.refetch()} />
      ) : null}

      {summary ? (
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          <SeverityChip severity="critical" label={`${t('reports.critical')}: ${summary.critical ?? 0}`} />
          <SeverityChip severity="warning" label={`${t('reports.warning')}: ${summary.warning ?? 0}`} />
          <SeverityChip severity="info" label={`${t('reports.info')}: ${summary.info ?? 0}`} />
        </Stack>
      ) : null}

      {query.data && alerts.length === 0 ? (
        <Alert severity="success">{t('reports.gstHealthClean')}</Alert>
      ) : null}

      {alerts.length > 0 ? (
        <Paper variant="outlined" sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('reports.severity')}</TableCell>
                <TableCell>{t('reports.code')}</TableCell>
                <TableCell>{t('reports.message')}</TableCell>
                <TableCell>{t('reports.document')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {alerts.map((alert, idx) => (
                <AlertInboxRow key={`${alert.code}-${idx}`} alert={alert} />
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}
    </Stack>
  );
}
