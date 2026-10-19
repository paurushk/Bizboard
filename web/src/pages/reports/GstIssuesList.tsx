import { useMemo, useState } from 'react';
import Alert from '@mui/material/Alert';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TablePagination from '@mui/material/TablePagination';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import { AlertInboxRow, type AlertInboxItem } from '@/components/insights/AlertInboxRow';
import type { AlertSeverity } from '@/components/insights/SeverityChip';
import { t } from '@/i18n';

export interface GstIssue {
  code?: string;
  message?: string;
  number?: string;
  severity?: string;
  documentType?: string;
  document_type?: string;
  documentId?: number | null;
  document_id?: number | null;
}

const RANK: Record<string, number> = { critical: 0, warning: 1, info: 2 };
const PAGE_SIZE = 10;

function normalize(issue: GstIssue, index: number): AlertInboxItem {
  const severity = (issue.severity && issue.severity in RANK ? issue.severity : 'warning') as AlertSeverity;
  return {
    id: index,
    code: issue.code ?? '',
    severity,
    message: issue.message ?? issue.code ?? '',
    number: issue.number,
    documentType: issue.documentType ?? issue.document_type,
    documentId: (issue.documentId ?? issue.document_id) ?? undefined,
  };
}

/** Every validation issue, worst first, with a link to the document so it can be fixed. */
export function GstIssuesList({ issues }: { issues: GstIssue[] }) {
  const [code, setCode] = useState('');
  const [page, setPage] = useState(0);
  const items = useMemo(
    () =>
      issues
        .map(normalize)
        .sort((a, b) => (RANK[a.severity] ?? 3) - (RANK[b.severity] ?? 3) || a.code.localeCompare(b.code)),
    [issues],
  );
  const codes = useMemo(() => Array.from(new Set(items.map((i) => i.code))).sort(), [items]);
  const shown = code ? items.filter((i) => i.code === code) : items;
  const pageCount = Math.max(0, Math.ceil(shown.length / PAGE_SIZE) - 1);
  const safePage = Math.min(page, pageCount);
  const rows = shown.slice(safePage * PAGE_SIZE, safePage * PAGE_SIZE + PAGE_SIZE);

  if (issues.length === 0) return null;
  return (
    <Alert severity={items.some((i) => i.severity === 'critical') ? 'error' : 'warning'} icon={false}>
      <Stack spacing={1}>
        <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" useFlexGap>
          <strong>{t('reports.issuesStrip')}: {issues.length}</strong>
          {codes.length > 1 ? (
            <TextField
              select
              size="small"
              label={t('gstIssues.filterByCode')}
              value={code}
              onChange={(e) => { setCode(e.target.value); setPage(0); }}
              sx={{ minWidth: 220 }}
            >
              <MenuItem value="">{t('gstIssues.allCodes')}</MenuItem>
              {codes.map((c) => <MenuItem key={c} value={c}>{c}</MenuItem>)}
            </TextField>
          ) : null}
        </Stack>
        <Paper variant="outlined" sx={{ overflowX: 'auto' }}>
          <Table size="small" aria-label={t('reports.issuesStrip')}>
            <TableHead>
              <TableRow>
                <TableCell>{t('reports.severity')}</TableCell>
                <TableCell>{t('reports.code')}</TableCell>
                <TableCell>{t('reports.message')}</TableCell>
                <TableCell>{t('reports.document')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((item) => <AlertInboxRow key={item.id} alert={item} />)}
            </TableBody>
          </Table>
          {shown.length > PAGE_SIZE ? (
            <TablePagination
              component="div"
              count={shown.length}
              page={safePage}
              onPageChange={(_e, p) => setPage(p)}
              rowsPerPage={PAGE_SIZE}
              rowsPerPageOptions={[PAGE_SIZE]}
            />
          ) : null}
        </Paper>
      </Stack>
    </Alert>
  );
}
