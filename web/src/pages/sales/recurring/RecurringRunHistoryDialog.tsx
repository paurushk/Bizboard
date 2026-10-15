import { useState } from 'react';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Link from '@mui/material/Link';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import type { RecurringSchedule } from '@/api/legacy/sales';
import * as api from '@/api/resources';
import { ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';
import { formatWhen, runDocumentRoute, statusText } from './recurringHelpers';

const PAGE_SIZE = 20;

export function RecurringRunHistoryDialog({
  schedule,
  onClose,
}: {
  schedule: RecurringSchedule | null;
  onClose: () => void;
}) {
  return (
    <Dialog open={schedule != null} onClose={onClose} fullWidth maxWidth="md" aria-labelledby="recurring-history-title">
      {/* Mounted per schedule, so paging starts at the first page each time. */}
      {schedule ? <HistoryBody key={schedule.id} schedule={schedule} onClose={onClose} /> : null}
    </Dialog>
  );
}

function HistoryBody({ schedule, onClose }: { schedule: RecurringSchedule; onClose: () => void }) {
  const [page, setPage] = useState(1);
  const runs = useQuery({
    queryKey: ['recurring-runs', schedule.id, page],
    queryFn: () => api.listRecurringRunsPage(schedule.id, { page, pageSize: PAGE_SIZE }),
  });
  const totalPages = Math.max(1, Math.ceil((runs.data?.count ?? 0) / PAGE_SIZE));
  return (
    <>
      <DialogTitle id="recurring-history-title">
        {t('recurring.historyTitle')}
        {` · ${schedule.customerName}`}
      </DialogTitle>
      <DialogContent>
        {runs.isLoading ? (
          <LoadingState />
        ) : runs.isError ? (
          <ErrorState message={getErrorMessage(runs.error)} error={runs.error} onRetry={() => void runs.refetch()} />
        ) : !runs.data?.results.length ? (
          <Typography variant="body2" color="text.secondary">{t('recurring.historyEmpty')}</Typography>
        ) : (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('recurring.colPeriod')}</TableCell>
                <TableCell>{t('recurring.colDocument')}</TableCell>
                <TableCell>{t('recurring.colStatus')}</TableCell>
                <TableCell>{t('recurring.colCreated')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {runs.data.results.map((run) => {
                const to = runDocumentRoute(run);
                const label = run.documentNumber || (run.documentId ? `#${run.documentId}` : t('recurring.deleted'));
                return (
                  <TableRow key={run.id}>
                    <TableCell>{run.periodKey}</TableCell>
                    <TableCell>
                      {to ? (
                        <Link component={RouterLink} to={to} onClick={onClose}>{label}</Link>
                      ) : (
                        label
                      )}
                    </TableCell>
                    <TableCell>
                      <Stack spacing={0.5} alignItems="flex-start">
                        <Chip size="small" label={run.status === 'DELETED' ? t('recurring.deleted') : statusText(run.status)} />
                        {run.einvoiceStatus ? (
                          <Chip
                            size="small"
                            variant="outlined"
                            color={run.einvoiceStatus === 'FAILED' ? 'error' : 'default'}
                            label={t('recurring.einvoiceState', { status: statusText(run.einvoiceStatus) })}
                          />
                        ) : null}
                        {run.completionError ? (
                          <Typography variant="caption" color="warning.main">
                            {t('recurring.completionError', { message: run.completionError })}
                          </Typography>
                        ) : null}
                      </Stack>
                    </TableCell>
                    <TableCell>
                      {formatWhen(run.createdAt)}
                      {' · '}
                      {run.isManual ? t('recurring.runManual') : t('recurring.runScheduled')}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </DialogContent>
      <DialogActions>
        {totalPages > 1 ? (
          <>
            <Button disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>{t('common.back')}</Button>
            <Typography variant="body2">{page} / {totalPages}</Typography>
            <Button disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>{t('common.next')}</Button>
          </>
        ) : null}
        <Button onClick={onClose}>{t('common.close')}</Button>
      </DialogActions>
    </>
  );
}
