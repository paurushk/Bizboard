import { useState } from 'react';
import Button from '@mui/material/Button';
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
import { useQuery } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { listStatutoryEventsPage } from '@/api/statutory';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { VirtualizedTable } from '@/components/VirtualizedTable';
import { t } from '@/i18n';

const PAGE_SIZE = 50;

function payloadSummary(payload: Record<string, unknown> | undefined): string {
  if (!payload || typeof payload !== 'object') return '—';
  const keys = Object.keys(payload).slice(0, 4);
  if (!keys.length) return '—';
  return keys
    .map((key) => {
      const value = payload[key];
      if (value == null) return `${key}=`;
      if (typeof value === 'object') return `${key}={…}`;
      return `${key}=${String(value)}`;
    })
    .join(', ');
}

export function StatutoryEventsPage() {
  const [entityType, setEntityType] = useState('');
  const [eventType, setEventType] = useState('');
  const [page, setPage] = useState(1);

  const query = useQuery({
    queryKey: ['statutory-events', entityType, eventType, page],
    queryFn: () =>
      listStatutoryEventsPage({
        entityType: entityType || undefined,
        eventType: eventType || undefined,
        page,
        pageSize: PAGE_SIZE,
      }),
  });

  const rows = query.data?.results ?? [];

  return (
    <Stack spacing={2}>
      <Typography variant="h4">{t('nav.statutoryEvents')}</Typography>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
        <TextField
          label={t('reports.entityType')}
          value={entityType}
          onChange={(e) => {
            setEntityType(e.target.value);
            setPage(1);
          }}
          size="small"
          sx={{ minWidth: 180 }}
        />
        <TextField
          select
          label={t('reports.eventType')}
          value={eventType}
          onChange={(e) => {
            setEventType(e.target.value);
            setPage(1);
          }}
          size="small"
          sx={{ minWidth: 160 }}
        >
          <MenuItem value="">{t('common.all')}</MenuItem>
          <MenuItem value="COMPLETE">COMPLETE</MenuItem>
          <MenuItem value="AMEND">AMEND</MenuItem>
          <MenuItem value="CANCEL">CANCEL</MenuItem>
          <MenuItem value="IRN">IRN</MenuItem>
          <MenuItem value="EWAY">EWAY</MenuItem>
        </TextField>
      </Stack>
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {!query.isLoading && rows.length === 0 ? <EmptyState /> : null}
      {rows.length > 0 ? (
        <Paper sx={{ overflow: 'auto' }}>
          <VirtualizedTable rowCount={rows.length} rowHeight={48}>
            {(virtualRows) => (
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>{t('common.date')}</TableCell>
                    <TableCell>{t('reports.eventType')}</TableCell>
                    <TableCell>{t('reports.entityType')}</TableCell>
                    <TableCell>{t('reports.entityId')}</TableCell>
                    <TableCell>{t('reports.payloadSummary')}</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {/* Companion fix to UXW2B-007 — see SalesHistoryPage for the full
                      explanation: without these spacer rows, scrolling past the first
                      screenful showed blank space instead of the (correctly computed)
                      later rows. */}
                  {virtualRows.length > 0 ? (
                    <TableRow style={{ height: virtualRows[0].start, padding: 0, border: 0 }} aria-hidden>
                      <TableCell style={{ padding: 0, border: 0 }} colSpan={5} />
                    </TableRow>
                  ) : null}
                  {virtualRows.map((vRow) => {
                    const row = rows[vRow.index];
                    if (!row) return null;
                    return (
                      <TableRow key={row.id} hover style={{ height: vRow.size }}>
                        <TableCell>{row.createdAt ?? '—'}</TableCell>
                        <TableCell>{row.eventType}</TableCell>
                        <TableCell>{row.entityType}</TableCell>
                        <TableCell>{row.entityId}</TableCell>
                        <TableCell>{payloadSummary(row.payload)}</TableCell>
                      </TableRow>
                    );
                  })}
                  {virtualRows.length > 0 ? (
                    <TableRow
                      style={{
                        height: Math.max(0, rows.length * 48 - virtualRows[virtualRows.length - 1].end),
                        padding: 0,
                        border: 0,
                      }}
                      aria-hidden
                    >
                      <TableCell style={{ padding: 0, border: 0 }} colSpan={5} />
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>
            )}
          </VirtualizedTable>
        </Paper>
      ) : null}
      {query.data && (query.data.next || page > 1) ? (
        <Stack direction="row" spacing={1} justifyContent="flex-end" alignItems="center">
          <Button
            size="small"
            disabled={page <= 1 || query.isFetching}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            {t('common.previous')}
          </Button>
          <Typography variant="body2" color="text.secondary">
            {t('common.page')} {page}
          </Typography>
          <Button
            size="small"
            disabled={!query.data.next || query.isFetching}
            onClick={() => setPage((p) => p + 1)}
          >
            {t('common.next')}
          </Button>
        </Stack>
      ) : null}
    </Stack>
  );
}
