/* eslint-disable react-refresh/only-export-components -- this is a deliberate shared module of helpers + presentational components for the phase pages */
import { type ReactNode } from 'react';
import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import Fade from '@mui/material/Fade';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { PageTitle } from '@/contextHelp';
import { EmptyState } from '@/components/PageState';
import { VirtualizedTable } from '@/components/VirtualizedTable';
import { t } from '@/i18n';
import { formatMoney, toNumber } from '@/utils/money';

export type Row = Record<string, unknown>;

export function asRows(data: unknown): Row[] {
  return (data as unknown as Row[]) || [];
}

export function StatusChip({ value }: { value: unknown }) {
  const v = String(value || '—');
  const color =
    v === 'PAID' || v === 'COMPLETED' || v === 'MATCHED' || v === 'POSTED' || v === 'COMMITTED'
      ? 'success'
      : v === 'CANCELLED' || v === 'FAILED' || v === 'EXPIRED'
        ? 'error'
        : v === 'DRAFT' || v === 'PREVIEW' || v === 'CREATED'
          ? 'default'
          : 'warning';
  return <Chip size="small" label={v} color={color as 'success' | 'error' | 'default' | 'warning'} variant="outlined" />;
}

export function PageShell({
  title,
  subtitle,
  actions,
  children,
  helpPage,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
  helpPage?: string;
}) {
  return (
    <Fade in>
      <Stack spacing={2} sx={{ maxWidth: '100%', overflowX: 'hidden' }}>
        <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ sm: 'center' }} gap={1}>
          <Box>
            <PageTitle
              page={helpPage}
              sx={{ fontSize: { xs: '1.5rem', sm: '2.125rem' }, fontWeight: 700 }}
            >
              {title}
            </PageTitle>
            {subtitle ? (
              <Typography variant="body2" color="text.secondary">
                {subtitle}
              </Typography>
            ) : null}
          </Box>
          {actions}
        </Stack>
        {children}
      </Stack>
    </Fade>
  );
}

export function BoolChip({ value }: { value: unknown }) {
  return (
    <Chip
      size="small"
      label={value ? 'Yes' : 'No'}
      color={value ? 'success' : 'default'}
      variant={value ? 'filled' : 'outlined'}
    />
  );
}

function dataTableCell(row: Row, c: { key: string; money?: boolean; status?: boolean; bool?: boolean; render?: (row: Row) => ReactNode }): ReactNode {
  if (c.render) return c.render(row);
  const raw = row[c.key];
  let cell: ReactNode = raw == null || raw === '' ? '—' : String(raw);
  if (c.money) cell = formatMoney(toNumber(raw as string | number));
  if (c.status) cell = <StatusChip value={raw} />;
  if (c.bool) cell = <BoolChip value={raw} />;
  return cell;
}

export function DataTable({
  columns,
  rows,
  empty,
  emptyAction,
  actions,
  // F3-016: opt-in windowing for phase pages whose row count isn't bounded
  // by pagination (e.g. a whole ledger/journal/stock-count pulled by date
  // range) — off by default so naturally small tables (a handful of GL
  // accounts, a page of masters) don't pay for a virtualizer.
  virtualized = false,
  maxHeight = 560,
  rowHeight = 52,
}: {
  columns: Array<{ key: string; label: string; money?: boolean; status?: boolean; bool?: boolean; render?: (row: Row) => ReactNode }>;
  rows: Row[];
  empty: string;
  emptyAction?: ReactNode;
  actions?: (row: Row) => ReactNode;
  virtualized?: boolean;
  maxHeight?: number;
  rowHeight?: number;
}) {
  if (!rows.length) return <EmptyState description={empty} action={emptyAction} />;

  if (virtualized) {
    return (
      <Paper variant="outlined" sx={{ overflow: 'hidden' }}>
        <VirtualizedTable rowCount={rows.length} maxHeight={maxHeight} rowHeight={rowHeight}>
          {({ rows: virtualRows, totalSize, measureElement }) => (
            // No stickyHeader: the Actions <th> was intercepting Post/Reverse
            // on the first body row (accounting-golden-path). Same class of
            // bug as SalesHistoryPage.
            <Table size="small">
              <TableHead>
                <TableRow>
                  {columns.map((c) => (
                    <TableCell key={c.key}>{c.label}</TableCell>
                  ))}
                  {actions ? <TableCell align="right">Actions</TableCell> : null}
                </TableRow>
              </TableHead>
              <TableBody>
                {virtualRows.length ? (
                  <TableRow style={{ height: virtualRows[0].start, padding: 0, border: 0 }} aria-hidden>
                    <TableCell style={{ padding: 0, border: 0 }} colSpan={columns.length + (actions ? 1 : 0)} />
                  </TableRow>
                ) : null}
                {virtualRows.map((vRow) => {
                  const row = rows[vRow.index];
                  return (
                    <TableRow hover key={String(row.id ?? vRow.index)} data-index={vRow.index} ref={measureElement}>
                      {columns.map((c) => (
                        <TableCell key={c.key}>{dataTableCell(row, c)}</TableCell>
                      ))}
                      {actions ? <TableCell align="right">{actions(row)}</TableCell> : null}
                    </TableRow>
                  );
                })}
                {virtualRows.length ? (
                  <TableRow
                    style={{
                      height: totalSize - virtualRows[virtualRows.length - 1].end,
                      padding: 0,
                      border: 0,
                    }}
                    aria-hidden
                  >
                    <TableCell style={{ padding: 0, border: 0 }} colSpan={columns.length + (actions ? 1 : 0)} />
                  </TableRow>
                ) : null}
              </TableBody>
            </Table>
          )}
        </VirtualizedTable>
      </Paper>
    );
  }

  return (
    <Paper
      variant="outlined"
      sx={{
        overflow: 'auto',
        maxWidth: '100%',
        width: '100%',
        WebkitOverflowScrolling: 'touch',
        scrollbarWidth: 'thin',
        borderRadius: 1,
      }}
    >
      <Table size="small" sx={{ minWidth: { xs: 480, sm: 'auto' } }}>
        <TableHead>
          <TableRow>
            {columns.map((c) => (
              <TableCell key={c.key}>{c.label}</TableCell>
            ))}
            {actions ? <TableCell align="right">Actions</TableCell> : null}
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row, idx) => (
            <TableRow hover key={String(row.id ?? idx)}>
              {columns.map((c) => (
                <TableCell key={c.key}>{dataTableCell(row, c)}</TableCell>
              ))}
              {actions ? <TableCell align="right">{actions(row)}</TableCell> : null}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Paper>
  );
}

/** The from/to date-filter pair repeated across report pages (discount,
 * invoice-profit, invoice-profit-rollup, and others) -- one place to change
 * the label/format instead of N near-identical TextField pairs. */
export function DateRangeFields({
  from,
  to,
  onFromChange,
  onToChange,
}: {
  from: string;
  to: string;
  onFromChange: (value: string) => void;
  onToChange: (value: string) => void;
}) {
  return (
    <>
      <TextField
        type="date"
        size="small"
        label={t('common.dateFrom')}
        InputLabelProps={{ shrink: true }}
        value={from}
        onChange={(e) => onFromChange(e.target.value)}
      />
      <TextField
        type="date"
        size="small"
        label={t('common.dateTo')}
        InputLabelProps={{ shrink: true }}
        value={to}
        onChange={(e) => onToChange(e.target.value)}
      />
    </>
  );
}
