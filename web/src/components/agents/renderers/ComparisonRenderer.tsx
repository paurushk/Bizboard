import Alert from '@mui/material/Alert';
import Chip from '@mui/material/Chip';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import { t } from '@/i18n';
import { MessageRenderer } from './MessageRenderer';
import type { RendererProps } from './types';

type Row = { field: string; left: unknown; right: unknown; mismatch?: boolean };

/** Two documents side by side with differences marked. Read-only; reused by later matching agents. */
export function ComparisonRenderer(props: RendererProps) {
  const { value } = props;
  const rows: Row[] = Array.isArray(value.rows) ? (value.rows as Row[]) : [];
  const notes: string[] = Array.isArray(value.internalNotes) ? (value.internalNotes as string[]) : [];
  return (
    <Stack spacing={2}>
    <Table size="small" aria-label={t('agents.drawer.title')}>
      <TableHead>
        <TableRow>
          <TableCell>{t('agents.comparison.field')}</TableCell>
          <TableCell>{t('agents.comparison.left')}</TableCell>
          <TableCell>{t('agents.comparison.right')}</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {rows.map((row, i) => (
          <TableRow key={`${i}:${row.field}`} selected={Boolean(row.mismatch)}>
            <TableCell>{row.field}</TableCell>
            <TableCell>{String(row.left ?? '')}</TableCell>
            <TableCell>
              {String(row.right ?? '')}
              {row.mismatch ? <Chip size="small" color="warning" label={t('agents.comparison.mismatch')} sx={{ ml: 1 }} /> : null}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
    {notes.map((n) => (
      <Alert key={n} severity="info">{n}</Alert>
    ))}
    {typeof value.text === 'string' ? <MessageRenderer {...props} /> : null}
    </Stack>
  );
}
