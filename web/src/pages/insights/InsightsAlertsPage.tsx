import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { listBusinessAlerts, snoozeBusinessAlert } from '@/api/resources';
import { AlertInboxRow, DisclaimerBanner, PageHeader } from '@/components/insights';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';

export function InsightsAlertsPage() {
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ['insights-alerts'], queryFn: () => listBusinessAlerts() });
  const snooze = useMutation({
    mutationFn: (id: number) => snoozeBusinessAlert(id, 7),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['insights-alerts'] }),
  });

  return (
    <Stack spacing={2}>
      <PageHeader title={t('nav.insightsAlerts')} />
      <DisclaimerBanner>{t('insights.disclaimer')}</DisclaimerBanner>
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {!query.isLoading && (query.data?.length ?? 0) === 0 ? (
        <EmptyState description={t('insights.noAlerts')} />
      ) : null}
      {(query.data?.length ?? 0) > 0 ? (
        <Paper variant="outlined" sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('reports.severity')}</TableCell>
                <TableCell>{t('reports.code')}</TableCell>
                <TableCell>{t('reports.message')}</TableCell>
                <TableCell>{t('reports.document')}</TableCell>
                <TableCell align="right">{t('common.actions')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {query.data!.map((alert) => (
                <AlertInboxRow
                  key={alert.id}
                  alert={{ ...alert, ctaPath: alert.ctaPath }}
                  showSnooze
                  snoozeLabel={t('insights.snooze')}
                  onSnooze={() => snooze.mutate(alert.id)}
                />
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}
      {snooze.isError ? (
        <ErrorState message={getErrorMessage(snooze.error)} error={snooze.error} />
      ) : null}
      {snooze.isPending ? <Button disabled>…</Button> : null}
    </Stack>
  );
}
