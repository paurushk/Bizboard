import type { ReactNode } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { StatusChip } from '@/components/StatusChip';
import { t } from '@/i18n';
import { formatMoney } from '@/utils/money';
import { documentStatusTone, statusLabelKey } from '@/utils/status';

export interface DocumentListRow {
  id: number;
  number?: string | null;
  date: string;
  partyName?: string;
  status: string;
  grandTotal: string | number;
}

interface Props {
  titleKey: string;
  newPath: string;
  /** i18n key for the create button label. Defaults to the generic 'common.create'. */
  createLabelKey?: string;
  detailPath: (id: number) => string;
  partyLabelKey: string;
  rows?: DocumentListRow[];
  loading: boolean;
  error: unknown;
  onRetry: () => void;
  /** Optional per-row actions (Complete / Cancel / Print). */
  rowActions?: (row: DocumentListRow) => ReactNode;
  extraColumn?: (row: DocumentListRow) => ReactNode;
  /** Hide the Create button (e.g. VIEWER role). Defaults to true. */
  showCreate?: boolean;
  page?: number;
  pageSize?: number;
  count?: number;
  hasNext?: boolean;
  hasPrevious?: boolean;
  onPageChange?: (page: number) => void;
}

export function DocumentListPage({
  titleKey,
  newPath,
  createLabelKey,
  detailPath,
  partyLabelKey,
  rows,
  loading,
  error,
  onRetry,
  rowActions,
  extraColumn,
  showCreate = true,
  page = 1,
  pageSize = 50,
  count,
  hasNext,
  hasPrevious,
  onPageChange,
}: Props) {
  const showActions = Boolean(rowActions || extraColumn);
  const showPager = Boolean(onPageChange) && (hasNext || hasPrevious || (typeof count === 'number' && count > pageSize));
  const totalPages =
    typeof count === 'number' && pageSize > 0 ? Math.max(1, Math.ceil(count / pageSize)) : null;

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="h4">{t(titleKey)}</Typography>
        {showCreate ? (
          <Button variant="contained" component={RouterLink} to={newPath}>
            {t(createLabelKey ?? 'common.create')}
          </Button>
        ) : null}
      </Stack>
      {loading ? <LoadingState /> : null}
      {error ? <ErrorState message={String(error)} error={error} onRetry={onRetry} /> : null}
      {!loading && !error && rows?.length === 0 ? <EmptyState /> : null}
      {rows && rows.length > 0 ? (
        <Paper sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('common.number')}</TableCell>
                <TableCell>{t('common.date')}</TableCell>
                <TableCell>{t(partyLabelKey)}</TableCell>
                <TableCell>{t('common.status')}</TableCell>
                <TableCell align="right">{t('common.total')}</TableCell>
                {showActions ? <TableCell align="right">{t('common.actions')}</TableCell> : null}
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.id} hover>
                  <TableCell>
                    <Button component={RouterLink} to={detailPath(r.id)} size="small">
                      {r.number ?? r.id}
                    </Button>
                  </TableCell>
                  <TableCell>{r.date}</TableCell>
                  <TableCell>{r.partyName ?? '—'}</TableCell>
                  <TableCell>
                    <StatusChip tone={documentStatusTone(r.status)} labelKey={statusLabelKey(r.status)} />
                  </TableCell>
                  <TableCell align="right">{formatMoney(r.grandTotal)}</TableCell>
                  {showActions ? (
                    <TableCell align="right">
                      <Stack direction="row" spacing={0.5} justifyContent="flex-end" flexWrap="wrap" useFlexGap>
                        {rowActions?.(r)}
                        {extraColumn?.(r)}
                      </Stack>
                    </TableCell>
                  ) : null}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}
      {showPager && onPageChange ? (
        <Stack direction="row" spacing={1} alignItems="center" justifyContent="flex-end">
          {totalPages != null ? (
            <Typography variant="body2" color="text.secondary">
              {t('common.page')} {page} / {totalPages}
            </Typography>
          ) : null}
          <Button
            variant="outlined"
            size="small"
            disabled={!hasPrevious && page <= 1}
            onClick={() => onPageChange(Math.max(1, page - 1))}
          >
            {t('common.previous')}
          </Button>
          <Button
            variant="outlined"
            size="small"
            disabled={hasNext === false || (totalPages != null && page >= totalPages)}
            onClick={() => onPageChange(page + 1)}
          >
            {t('common.next')}
          </Button>
        </Stack>
      ) : null}
    </Stack>
  );
}
