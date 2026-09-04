import { useRef, useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
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
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import {
  actImsRow,
  bulkAcceptExact,
  exportImsOffline,
  fetchImsScorecard,
  fetchImsSummary,
  fetchSupplierMessage,
  importImsOffline,
  listGstr2bPage,
  matchGstr2b,
  money,
  patchGstr2bEligibility,
  rowDeadline,
  type ImsAction,
  type ItcEligibility,
} from '@/api/gstr2b';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { DisclaimerBanner, KpiStat, PageHeader } from '@/components/insights';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { VirtualizedTable } from '@/components/VirtualizedTable';
import { t } from '@/i18n';
import { formatMoney } from '@/utils/money';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';

function currentPeriod(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

const COLS = 8;

export function Gstr2bPage() {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [period, setPeriod] = useState(currentPeriod());
  const [page, setPage] = useState(1);
  const [imsFilter, setImsFilter] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [actRow, setActRow] = useState<{ id: number; action: ImsAction } | null>(null);
  const [remark, setRemark] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  const [confirmBulk, setConfirmBulk] = useState(false);

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ['gstr2b'] });
    void qc.invalidateQueries({ queryKey: ['ims-summary'] });
    void qc.invalidateQueries({ queryKey: ['ims-scorecard'] });
  };

  const query = useQuery({
    queryKey: ['gstr2b', period, page, imsFilter],
    queryFn: () =>
      listGstr2bPage({
        period,
        page,
        pageSize: 50,
        imsAction: imsFilter || undefined,
      }),
  });

  const summary = useQuery({
    queryKey: ['ims-summary', period],
    queryFn: () => fetchImsSummary(period),
  });

  const scorecard = useQuery({
    queryKey: ['ims-scorecard', period],
    queryFn: () => fetchImsScorecard(period),
  });

  const matchMutation = useMutation({
    mutationFn: () => matchGstr2b(period),
    onSuccess: () => invalidate(),
    onError: (err) => setError(getErrorMessage(err)),
  });

  const bulkMutation = useMutation({
    mutationFn: () => bulkAcceptExact(period),
    onSuccess: () => invalidate(),
    onError: (err) => setError(getErrorMessage(err)),
  });

  const patchMutation = useMutation({
    mutationFn: ({ id, itcEligibility }: { id: number; itcEligibility: ItcEligibility }) =>
      patchGstr2bEligibility(id, itcEligibility),
    onSuccess: () => invalidate(),
    onError: (err) => setError(getErrorMessage(err)),
  });

  const actMutation = useMutation({
    mutationFn: ({ id, action, remark }: { id: number; action: ImsAction; remark: string }) =>
      actImsRow(id, action, remark),
    onSuccess: () => {
      setActRow(null);
      setRemark('');
      invalidate();
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const exportMutation = useMutation({
    mutationFn: () => exportImsOffline(period),
    onSuccess: (payload) => {
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `ims-offline-${period}.json`;
      a.click();
      URL.revokeObjectURL(url);
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const importMutation = useMutation({
    mutationFn: (payload: unknown) => importImsOffline(payload, true),
    onSuccess: () => invalidate(),
    onError: (err) => setError(getErrorMessage(err)),
  });

  const messageMutation = useMutation({
    mutationFn: (id: number) => fetchSupplierMessage(id),
    onSuccess: (body) => setMessage(body.text),
    onError: (err) => setError(getErrorMessage(err)),
  });

  const rows = query.data?.results ?? [];
  const suppliers = scorecard.data?.suppliers ?? [];
  const atRisk = money(summary.data, 'itcAtRisk', 'itc_at_risk');

  const requestAct = (id: number, action: ImsAction) => {
    if (action === 'ACCEPT') {
      actMutation.mutate({ id, action, remark: t('ims.acceptRemark') });
      return;
    }
    setActRow({ id, action });
    setRemark('');
  };

  const onPickFile = async (file: File | undefined) => {
    if (!file) return;
    try {
      const text = await file.text();
      importMutation.mutate(JSON.parse(text));
    } catch {
      setError(t('ims.badOfflineFile'));
    }
  };

  return (
    <Stack spacing={2}>
      <PageHeader title={t('nav.gstr2b')} subtitle={t('ims.subtitle')} />
      <DisclaimerBanner>{t('ims.disclaimer')}</DisclaimerBanner>
      {error ? <HelpErrorAlert message={error} /> : null}

      <Stack direction="row" spacing={2} useFlexGap flexWrap="wrap">
        <Box sx={{ minWidth: 140 }}>
          <KpiStat label={t('ims.totalItc')} value={money(summary.data, 'totalItc', 'total_itc')} money dense />
        </Box>
        <Box sx={{ minWidth: 140 }}>
          <KpiStat label={t('ims.matchedItc')} value={money(summary.data, 'matchedItc', 'matched_itc')} money dense />
        </Box>
        <Box sx={{ minWidth: 140 }}>
          <KpiStat
            label={t('ims.unresolvedItc')}
            value={money(summary.data, 'unresolvedItc', 'unresolved_itc')}
            money
            dense
          />
        </Box>
        <Box sx={{ minWidth: 160 }}>
          <KpiStat label={t('ims.creditAtRisk')} value={atRisk} money dense />
        </Box>
        <Box sx={{ minWidth: 160 }}>
          <KpiStat
            label={t('ims.expiringItc')}
            value={money(summary.data, 'expiringItc', 'expiring_itc')}
            money
            dense
            deltaLabel={
              summary.data
                ? t('ims.expiringCount', {
                    count: String(summary.data.expiringCount ?? summary.data.expiring_count ?? 0),
                  })
                : undefined
            }
          />
        </Box>
      </Stack>

      <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" useFlexGap>
        <TextField
          type="month"
          label={t('reports.period')}
          value={period}
          onChange={(e) => {
            setPeriod(e.target.value);
            setPage(1);
          }}
          size="small"
          InputLabelProps={{ shrink: true }}
          sx={{ width: 160 }}
        />
        <TextField
          select
          size="small"
          label={t('ims.action')}
          value={imsFilter}
          onChange={(e) => {
            setImsFilter(e.target.value);
            setPage(1);
          }}
          sx={{ minWidth: 160 }}
        >
          <MenuItem value="">{t('ims.allActions')}</MenuItem>
          <MenuItem value="NO_ACTION">NO_ACTION</MenuItem>
          <MenuItem value="ACCEPT">ACCEPT</MenuItem>
          <MenuItem value="REJECT">REJECT</MenuItem>
          <MenuItem value="PENDING">PENDING</MenuItem>
        </TextField>
        <Button variant="outlined" onClick={() => matchMutation.mutate()} disabled={matchMutation.isPending}>
          {t('ims.matchPurchases')}
        </Button>
        <Button variant="contained" onClick={() => setConfirmBulk(true)} disabled={bulkMutation.isPending}>
          {t('ims.bulkAcceptExact')}
        </Button>
        <Button variant="outlined" onClick={() => fileRef.current?.click()} disabled={importMutation.isPending}>
          {t('ims.importOffline')}
        </Button>
        <input
          ref={fileRef}
          type="file"
          accept="application/json,.json"
          hidden
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = '';
            void onPickFile(file);
          }}
        />
        <Button variant="outlined" onClick={() => exportMutation.mutate()} disabled={exportMutation.isPending}>
          {t('ims.exportOffline')}
        </Button>
      </Stack>

      <Alert severity="info">{t('ims.noAutoAccept')}</Alert>

      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {!query.isLoading && rows.length === 0 ? <EmptyState /> : null}
      {rows.length > 0 ? (
        <Paper sx={{ overflow: 'auto' }}>
          <VirtualizedTable rowCount={rows.length} rowHeight={64}>
            {({ rows: virtualRows, totalSize, measureElement }) => (
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>{t('ims.supplierGstin')}</TableCell>
                    <TableCell>{t('ims.invoice')}</TableCell>
                    <TableCell align="right">{t('ims.tax')}</TableCell>
                    <TableCell>{t('ims.matchClass')}</TableCell>
                    <TableCell>{t('ims.action')}</TableCell>
                    <TableCell>{t('ims.deadline')}</TableCell>
                    <TableCell>{t('billing.itcEligibility')}</TableCell>
                    <TableCell align="right">{t('common.actions')}</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {virtualRows.length > 0 ? (
                    <TableRow style={{ height: virtualRows[0].start, padding: 0, border: 0 }} aria-hidden>
                      <TableCell style={{ padding: 0, border: 0 }} colSpan={COLS} />
                    </TableRow>
                  ) : null}
                  {virtualRows.map((vRow) => {
                    const row = rows[vRow.index];
                    if (!row) return null;
                    const tax =
                      Number(row.igst || 0) + Number(row.cgst || 0) + Number(row.sgst || 0) + Number(row.cess || 0);
                    return (
                      <TableRow
                        key={row.id}
                        data-index={vRow.index}
                        ref={measureElement}
                        style={{ height: vRow.size }}
                      >
                        <TableCell>{row.supplierGstin}</TableCell>
                        <TableCell>
                          {row.invoiceNumber}
                          <Typography variant="caption" display="block" color="text.secondary">
                            {row.invoiceDate || '—'}
                          </Typography>
                        </TableCell>
                        <TableCell align="right">{formatMoney(tax)}</TableCell>
                        <TableCell>{row.matchClass || row.matchStatus}</TableCell>
                        <TableCell>{row.imsAction || 'NO_ACTION'}</TableCell>
                        <TableCell>{rowDeadline(row)}</TableCell>
                        <TableCell>
                          <TextField
                            select
                            size="small"
                            value={row.itcEligibility}
                            onChange={(e) =>
                              patchMutation.mutate({
                                id: row.id,
                                itcEligibility: e.target.value as ItcEligibility,
                              })
                            }
                            sx={{ minWidth: 130 }}
                          >
                            <MenuItem value="UNREVIEWED">{t('ims.unreviewed')}</MenuItem>
                            <MenuItem value="CLAIMABLE" disabled={row.matchStatus !== 'MATCHED'}>
                              {t('ims.claimable')}
                            </MenuItem>
                            <MenuItem value="INELIGIBLE">{t('ims.ineligible')}</MenuItem>
                            <MenuItem value="REVERSED">{t('ims.reversed')}</MenuItem>
                          </TextField>
                        </TableCell>
                        <TableCell align="right">
                          <Stack direction="row" spacing={0.5} justifyContent="flex-end" flexWrap="wrap" useFlexGap>
                            <Button
                              size="small"
                              disabled={row.imsAction === 'ACCEPT'}
                              onClick={() => requestAct(row.id, 'ACCEPT')}
                            >
                              {t('ims.accept')}
                            </Button>
                            <Button size="small" color="error" onClick={() => requestAct(row.id, 'REJECT')}>
                              {t('ims.reject')}
                            </Button>
                            <Button size="small" onClick={() => requestAct(row.id, 'PENDING')}>
                              {t('ims.pending')}
                            </Button>
                            <Button size="small" onClick={() => messageMutation.mutate(row.id)}>
                              {t('ims.supplierMsg')}
                            </Button>
                          </Stack>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                  {virtualRows.length > 0 ? (
                    <TableRow
                      style={{
                        height: Math.max(0, totalSize - virtualRows[virtualRows.length - 1].end),
                        padding: 0,
                        border: 0,
                      }}
                      aria-hidden
                    >
                      <TableCell style={{ padding: 0, border: 0 }} colSpan={COLS} />
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

      <Typography variant="h6">{t('ims.scorecard')}</Typography>
      {suppliers.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          {t('ims.scorecardEmpty')}
        </Typography>
      ) : (
        <Paper sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('ims.supplier')}</TableCell>
                <TableCell align="right">{t('ims.purchaseValue')}</TableCell>
                <TableCell align="right">{t('ims.mismatches')}</TableCell>
                <TableCell align="right">{t('ims.rejections')}</TableCell>
                <TableCell align="right">{t('ims.itcAffected')}</TableCell>
                <TableCell align="right">{t('ims.avgCorrectionDays')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {suppliers.map((s) => (
                <TableRow key={s.supplierGstin || s.supplier_gstin}>
                  <TableCell>
                    {s.supplierName || s.supplier_name || s.supplierGstin || s.supplier_gstin}
                  </TableCell>
                  <TableCell align="right">{formatMoney(s.purchaseValue ?? s.purchase_value)}</TableCell>
                  <TableCell align="right">{s.mismatchCount ?? s.mismatch_count ?? 0}</TableCell>
                  <TableCell align="right">{s.rejections ?? 0}</TableCell>
                  <TableCell align="right">{formatMoney(s.itcAffected ?? s.itc_affected)}</TableCell>
                  <TableCell align="right">{s.averageCorrectionDays ?? 0}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      )}

      <Dialog open={Boolean(actRow)} onClose={() => setActRow(null)} fullWidth maxWidth="sm">
        <DialogTitle>{actRow?.action === 'REJECT' ? t('ims.rejectTitle') : t('ims.pendingTitle')}</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            fullWidth
            required={actRow?.action === 'REJECT'}
            label={t('ims.remark')}
            value={remark}
            onChange={(e) => setRemark(e.target.value)}
            sx={{ mt: 1 }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setActRow(null)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={actRow?.action === 'REJECT' && !remark.trim()}
            onClick={() => {
              if (!actRow) return;
              actMutation.mutate({ id: actRow.id, action: actRow.action, remark });
            }}
          >
            {t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={Boolean(message)} onClose={() => setMessage(null)} fullWidth maxWidth="sm">
        <DialogTitle>{t('ims.supplierMsg')}</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
            {message}
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => {
              if (message) void navigator.clipboard?.writeText(message);
            }}
          >
            {t('ims.copy')}
          </Button>
          <Button
            onClick={() => {
              if (message) window.open(`https://wa.me/?text=${encodeURIComponent(message)}`, '_blank', 'noopener');
            }}
          >
            {t('reports.shareOnWhatsapp')}
          </Button>
          <Button onClick={() => setMessage(null)}>{t('common.close')}</Button>
        </DialogActions>
      </Dialog>
      <ConfirmDialog
        open={confirmBulk}
        title={t('ims.bulkAcceptExact')}
        body={`This accepts every exact-match GSTR-2B row for ${period} and claims its ITC. Review individual rows if unsure.`}
        confirmLabel={t('ims.bulkAcceptExact')}
        confirming={bulkMutation.isPending}
        onClose={() => setConfirmBulk(false)}
        onConfirm={() => {
          setConfirmBulk(false);
          bulkMutation.mutate();
        }}
      />
    </Stack>
  );
}
