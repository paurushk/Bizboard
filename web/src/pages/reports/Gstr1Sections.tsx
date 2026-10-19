import Accordion from '@mui/material/Accordion';
import AccordionDetails from '@mui/material/AccordionDetails';
import AccordionSummary from '@mui/material/AccordionSummary';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { t } from '@/i18n';
import { DataTable } from '@/pages/phase/phaseShared';
import { formatColumnHeader, isMoneyColumn } from '@/utils/reportFormat';

import Link from '@mui/material/Link';
import { Link as RouterLink } from 'react-router-dom';
import { documentIdsOf, gstr1RowPath, sectionRows, type Row } from '@/pages/reports/gstr1Rows';

const SECTIONS: Array<{ keys: string[]; labelKey: string }> = [
  { keys: ['b2b'], labelKey: 'gstr1.b2b' },
  { keys: ['b2cl'], labelKey: 'gstr1.b2cl' },
  { keys: ['exp'], labelKey: 'gstr1.exports' },
  { keys: ['sez'], labelKey: 'gstr1.sez' },
  { keys: ['cdnr'], labelKey: 'gstr1.cdnr' },
  { keys: ['cdnur'], labelKey: 'gstr1.cdnur' },
  { keys: ['hsn'], labelKey: 'gstr1.hsn' },
  { keys: ['doc', 'docs'], labelKey: 'gstr1.docs' },
  { keys: ['at'], labelKey: 'gstr1.advances' },
  { keys: ['atadj'], labelKey: 'gstr1.advanceAdjustments' },
  { keys: ['txpd'], labelKey: 'gstr1.taxPaidOnAdvances' },
  { keys: ['amendments'], labelKey: 'gstr1.amendments' },
];

function columnsFor(rows: Row[], ids: ReturnType<typeof documentIdsOf>) {
  const first = rows[0] ?? {};
  return Object.keys(first)
    .filter((k) => first[k] === null || ['string', 'number', 'boolean'].includes(typeof first[k]))
    .slice(0, 9)
    .map((key) => {
      const base = { key, label: formatColumnHeader(key), money: isMoneyColumn(key) };
      // RPT-07: the invoice or note number opens the document it came from.
      if (key !== 'invoice_number' && key !== 'note_number') return base;
      return {
        ...base,
        render: (row: Row) => {
          const to = gstr1RowPath(row, ids);
          const text = String(row[key] ?? '');
          return to ? <Link component={RouterLink} to={to}>{text}</Link> : text;
        },
      };
    });
}

/** The remaining GSTR-1 tables, one collapsed block each; only the ones this month actually has. */
export function Gstr1Sections({ data }: { data: Row }) {
  const ids = documentIdsOf(data);
  const present = SECTIONS.map((s) => {
    const rows = s.keys.map((k) => sectionRows(data[k])).find((r) => r.length > 0) ?? [];
    return { ...s, rows };
  }).filter((s) => s.rows.length > 0);
  if (present.length === 0) return null;
  return (
    <Stack spacing={1}>
      <Typography variant="h6">{t('gstr1.moreTables')}</Typography>
      {present.map((s) => (
        <Accordion key={s.labelKey} disableGutters variant="outlined">
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Typography fontWeight={600}>{t(s.labelKey)} · {s.rows.length}</Typography>
          </AccordionSummary>
          <AccordionDetails>
            <DataTable
              rows={s.rows.map((r, i) => ({ id: i, ...r }))}
              columns={columnsFor(s.rows, ids)}
              empty={t('empty.reports')}
            />
          </AccordionDetails>
        </Accordion>
      ))}
    </Stack>
  );
}
