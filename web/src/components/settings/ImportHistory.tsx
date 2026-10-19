import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import FormControlLabel from '@mui/material/FormControlLabel';
import MenuItem from '@mui/material/MenuItem';
import Switch from '@mui/material/Switch';
import TextField from '@mui/material/TextField';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { downloadImportErrorsCsv, downloadTallyErrorsCsv, listImportHistory, listTallyRuns, voidImport } from '@/api/resources';
import type { TallyRunRow } from '@/api/legacy/misc';
import { AsyncSection } from '@/components/settings/AsyncSection';
import { t } from '@/i18n';
import type { ImportJob } from '@/types/domain';
import { confirmAction } from '@/utils/confirmBridge';
import { settingsErrorText } from '@/utils/settingsErrors';

const PAGE_SIZE = 20;
const KINDS = ['CUSTOMERS', 'SUPPLIERS', 'PRODUCTS', 'OPENING_STOCK', 'PURCHASE_BILL', 'SALES_BILL'];
const STATUSES = ['COMMITTED', 'PREVIEWED', 'FAILED', 'VOIDED', 'CANCELLED'];

function when(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? String(iso) : d.toLocaleString();
}

/**
 * SET-09: what was imported before, by whom, and how it ended. The list comes from the server, so
 * it survives a refresh and is the same for every owner. Undo is offered only where the server says
 * the import can be undone.
 */
export function ImportHistory({ canUndo }: { canUndo: boolean }) {
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [kind, setKind] = useState('');
  const [status, setStatus] = useState('');
  const [mine, setMine] = useState(false);
  const query = useQuery({
    queryKey: ['import-history', page, kind, status, mine],
    queryFn: () => listImportHistory({ page, pageSize: PAGE_SIZE, kind, status, mine }),
  });
  const change = (apply: () => void) => {
    apply();
    setPage(1);
  };
  const [error, setError] = useState('');
  const undo = useMutation({
    mutationFn: (id: number) => voidImport(id),
    onSuccess: () => {
      setError('');
      void qc.invalidateQueries({ queryKey: ['import-history'] });
    },
    onError: (e) => setError(settingsErrorText(e)),
  });
  const askUndo = async (job: ImportJob) => {
    if (await confirmAction(`${t('importHistory.undoTitle')}\n\n${t('importHistory.undoBody')}`)) undo.mutate(job.id);
  };

  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Stack spacing={1.5}>
        <Typography variant="h6">{t('importHistory.title')}</Typography>
        <Typography variant="body2" color="text.secondary">
          {t('importHistory.help')}
        </Typography>
        {error ? <Alert severity="error" onClose={() => setError('')}>{error}</Alert> : null}
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems={{ sm: 'center' }}>
          <TextField
            select
            size="small"
            label={t('importHistory.filterKind')}
            value={kind}
            onChange={(e) => change(() => setKind(e.target.value))}
            sx={{ minWidth: 160 }}
          >
            <MenuItem value="">{t('importHistory.filterAll')}</MenuItem>
            {KINDS.map((k) => (
              <MenuItem key={k} value={k}>
                {t(`importHistory.kind.${k}`)}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            select
            size="small"
            label={t('importHistory.filterStatus')}
            value={status}
            onChange={(e) => change(() => setStatus(e.target.value))}
            sx={{ minWidth: 160 }}
          >
            <MenuItem value="">{t('importHistory.filterAll')}</MenuItem>
            {STATUSES.map((s) => (
              <MenuItem key={s} value={s}>
                {t(`importHistory.status.${s}`)}
              </MenuItem>
            ))}
          </TextField>
          <FormControlLabel
            control={<Switch checked={mine} onChange={(_, on) => change(() => setMine(on))} />}
            label={t('importHistory.filterMine')}
          />
        </Stack>
        <AsyncSection
          query={query}
          isEmpty={(result) => result.rows.length === 0}
          empty={{ description: kind || status || mine ? t('importHistory.emptyFiltered') : t('importHistory.empty') }}
        >
          {({ rows, count, hasNext, hasPrevious }) => (
            <>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>{t('importHistory.colWhen')}</TableCell>
                  <TableCell>{t('importHistory.colKind')}</TableCell>
                  <TableCell>{t('importHistory.colFile')}</TableCell>
                  <TableCell>{t('importHistory.colBy')}</TableCell>
                  <TableCell>{t('importHistory.colRows')}</TableCell>
                  <TableCell>{t('importHistory.colStatus')}</TableCell>
                  <TableCell />
                </TableRow>
              </TableHead>
              <TableBody>
                {rows.map((job) => (
                  <TableRow key={job.id}>
                    <TableCell>{when(job.committedAt ?? job.createdAt)}</TableCell>
                    <TableCell>{t(`importHistory.kind.${job.kind}`)}</TableCell>
                    <TableCell>{job.fileName || '—'}</TableCell>
                    <TableCell>{job.createdByName || '—'}</TableCell>
                    <TableCell>
                      {t('importHistory.rows', {
                        total: String(job.totalRows),
                        valid: String(job.validRows),
                        errors: String(job.errorRows),
                      })}
                    </TableCell>
                    <TableCell>
                      <Chip
                        size="small"
                        color={job.status === 'COMMITTED' ? 'success' : job.status === 'FAILED' ? 'error' : 'default'}
                        variant="outlined"
                        label={t(`importHistory.status.${job.status}`)}
                      />
                    </TableCell>
                    <TableCell align="right">
                      {job.errorRows > 0 ? (
                        <Button size="small" onClick={() => void downloadImportErrorsCsv(job.id, job.kind)}>
                          {t('importHistory.errors')}
                        </Button>
                      ) : null}
                      {canUndo && job.canUndo ? (
                        <Button size="small" color="warning" disabled={undo.isPending} onClick={() => void askUndo(job)}>
                          {t('importHistory.undo')}
                        </Button>
                      ) : job.status === 'COMMITTED' && !job.canUndo ? (
                        <Typography variant="caption" color="text.secondary">
                          {t('importHistory.cannotUndo')}
                        </Typography>
                      ) : null}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {hasNext || hasPrevious ? (
              <Stack direction="row" spacing={1} alignItems="center" justifyContent="flex-end">
                <Typography variant="caption" color="text.secondary">
                  {t('importHistory.pageOf', { page: String(page), pages: String(Math.max(1, Math.ceil(count / PAGE_SIZE))) })}
                </Typography>
                <Button size="small" disabled={!hasPrevious} onClick={() => setPage((p) => Math.max(1, p - 1))}>
                  {t('importHistory.newer')}
                </Button>
                <Button size="small" disabled={!hasNext} onClick={() => setPage((p) => p + 1)}>
                  {t('importHistory.older')}
                </Button>
              </Stack>
            ) : null}
            </>
          )}
        </AsyncSection>
      </Stack>
    </Paper>
  );
}

/** The company's recent Tally imports. A 404 means Tally is not switched on for it. */
export function TallyRunsHistory() {
  const query = useQuery({ queryKey: ['tally-runs'], queryFn: listTallyRuns, retry: false });
  const off = (query.error as { response?: { status?: number } } | null)?.response?.status === 404;
  if (off) return <Alert severity="info">{t('importHistory.tallyOff')}</Alert>;
  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Stack spacing={1.5}>
        <Typography variant="h6">{t('importHistory.tallyTitle')}</Typography>
        <AsyncSection query={query} isEmpty={(rows) => rows.length === 0} empty={{ description: t('importHistory.empty') }}>
          {(rows: TallyRunRow[]) => (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>{t('importHistory.colWhen')}</TableCell>
                  <TableCell>{t('importHistory.colFile')}</TableCell>
                  <TableCell>{t('importHistory.colBy')}</TableCell>
                  <TableCell>{t('importHistory.colRows')}</TableCell>
                  <TableCell>{t('importHistory.colStatus')}</TableCell>
                  <TableCell />
                </TableRow>
              </TableHead>
              <TableBody>
                {rows.map((run) => (
                  <TableRow key={run.id}>
                    <TableCell>{when(run.createdAt)}</TableCell>
                    <TableCell>{run.fileName || '—'}</TableCell>
                    <TableCell>{run.by || '—'}</TableCell>
                    <TableCell>
                      {t('importHistory.tallyRows', {
                        customers: String(run.customers),
                        suppliers: String(run.suppliers),
                        products: String(run.products),
                      })}
                    </TableCell>
                    <TableCell>
                      <Chip
                        size="small"
                        variant="outlined"
                        color={run.status === 'COMMITTED' ? 'success' : run.status === 'FAILED' ? 'error' : 'default'}
                        label={t(`importHistory.status.${run.status}`)}
                      />
                      {run.failureReason ? (
                        <Typography variant="caption" display="block" color="error">
                          {run.failureReason}
                        </Typography>
                      ) : null}
                    </TableCell>
                    <TableCell align="right">
                      {run.errorCount > 0 ? (
                        <Button size="small" onClick={() => void downloadTallyErrorsCsv(run.id)}>
                          {t('importHistory.tallyErrors', { count: String(run.errorCount) })}
                        </Button>
                      ) : null}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </AsyncSection>
      </Stack>
    </Paper>
  );
}
