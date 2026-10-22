import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import { t } from '@/i18n';
import type { RendererProps } from './types';

type Line = Record<string, unknown>;

const DEFAULT_COLUMNS = ['item', 'qty', 'unit', 'note'];
const EDITABLE = new Set(['qty', 'note']);

/** An editable line table. Columns come from the payload, so a new kind needs no new component. */
export function LinesRenderer({ value, onChange, disabled }: RendererProps) {
  const lines: Line[] = Array.isArray(value.lines) ? (value.lines as Line[]) : [];
  const columns: string[] = Array.isArray(value.columns) ? (value.columns as string[]) : DEFAULT_COLUMNS;

  function setCell(index: number, column: string, cell: string) {
    const next = lines.map((line, i) => (i === index ? { ...line, [column]: cell } : line));
    onChange({ ...value, lines: next });
  }

  return (
    <Table size="small" aria-label={t('agents.drawer.title')}>
      <TableHead>
        <TableRow>
          {columns.map((c) => (
            <TableCell key={c}>{t(`agents.lines.${c}`)}</TableCell>
          ))}
        </TableRow>
      </TableHead>
      <TableBody>
        {lines.map((line, i) => (
          <TableRow key={`${i}:${String(line.item ?? '')}`}>
            {columns.map((c) => (
              <TableCell key={c}>
                {EDITABLE.has(c) && !disabled ? (
                  <TextField
                    size="small"
                    variant="standard"
                    value={String(line[c] ?? '')}
                    onChange={(e) => setCell(i, c, e.target.value)}
                    inputProps={{ 'aria-label': `${t(`agents.lines.${c}`)} ${i + 1}` }}
                  />
                ) : (
                  String(line[c] ?? '')
                )}
              </TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
