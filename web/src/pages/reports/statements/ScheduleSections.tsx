import Paper from '@mui/material/Paper';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import { t } from '@/i18n';
import { formatMoney, toNumber } from '@/utils/money';
import { visibleLines, type ScheduleSection } from './statementHelpers';

export function ScheduleSections({
  sections,
  trusted,
  totalLabel,
  totalValue,
  labelOf,
}: {
  sections: ScheduleSection[];
  trusted: boolean;
  /** Optional closing row for the whole block, e.g. "Total assets". */
  totalLabel?: string;
  totalValue?: number;
  labelOf?: (section: ScheduleSection) => string;
}) {
  const money = (v: string | number) => (trusted ? formatMoney(toNumber(v)) : '—');
  return (
    <Paper variant="outlined" sx={{ overflowX: 'auto' }}>
      <Table size="small" aria-label={totalLabel}>
        <TableBody>
          {sections.map((section) => (
            <SectionRows key={section.key} section={section} money={money} label={labelOf?.(section) ?? section.label} />
          ))}
          {totalLabel !== undefined && totalValue !== undefined ? (
            <TableRow>
              <TableCell sx={{ fontWeight: 800 }}>{totalLabel}</TableCell>
              <TableCell align="right" sx={{ fontWeight: 800 }}>{money(totalValue)}</TableCell>
            </TableRow>
          ) : null}
        </TableBody>
      </Table>
    </Paper>
  );
}

function SectionRows({
  section,
  money,
  label,
}: {
  section: ScheduleSection;
  money: (v: string | number) => string;
  label: string;
}) {
  const lines = visibleLines(section);
  return (
    <>
      <TableRow>
        <TableCell colSpan={2} sx={{ bgcolor: 'action.hover', fontWeight: 700 }}>{label}</TableCell>
      </TableRow>
      {lines.map((line) => (
        <TableRow key={line.key}>
          <TableCell sx={{ pl: 3 }}>
            {line.label}
            {(line.accounts ?? []).map((a) => (
              <Typography key={a.code} variant="caption" color="text.secondary" display="block" sx={{ pl: 1 }}>
                {a.code} · {a.name}
              </Typography>
            ))}
          </TableCell>
          <TableCell align="right">{money(line.amount)}</TableCell>
        </TableRow>
      ))}
      <TableRow>
        <TableCell sx={{ fontWeight: 700 }}>{t('statements.total')}</TableCell>
        <TableCell align="right" sx={{ fontWeight: 700 }}>{money(section.amount)}</TableCell>
      </TableRow>
    </>
  );
}
