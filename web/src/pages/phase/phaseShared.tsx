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
import Typography from '@mui/material/Typography';
import { EmptyState } from '@/components/PageState';
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
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Fade in>
      <Stack spacing={2}>
        <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ sm: 'center' }} gap={1}>
          <Box>
            <Typography variant="h4">{title}</Typography>
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

export function DataTable({
  columns,
  rows,
  empty,
  actions,
}: {
  columns: Array<{ key: string; label: string; money?: boolean; status?: boolean; bool?: boolean }>;
  rows: Row[];
  empty: string;
  actions?: (row: Row) => ReactNode;
}) {
  if (!rows.length) return <EmptyState description={empty} />;
  return (
    <Paper variant="outlined" sx={{ overflow: 'auto' }}>
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
          {rows.map((row, idx) => (
            <TableRow hover key={String(row.id ?? idx)}>
              {columns.map((c) => {
                const raw = row[c.key];
                let cell: ReactNode = raw == null || raw === '' ? '—' : String(raw);
                if (c.money) cell = formatMoney(toNumber(raw as string | number));
                if (c.status) cell = <StatusChip value={raw} />;
                if (c.bool) cell = <BoolChip value={raw} />;
                return <TableCell key={c.key}>{cell}</TableCell>;
              })}
              {actions ? <TableCell align="right">{actions(row)}</TableCell> : null}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Paper>
  );
}
