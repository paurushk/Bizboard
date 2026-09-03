import { useMemo, useState } from 'react';
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
  cancelWorkOrder,
  completeWorkOrder,
  createWorkOrder,
  listBomsPage,
  listWorkOrdersPage,
  releaseWorkOrder,
  updateWorkOrder,
  type WorkOrder,
} from '@/api/manufacturing';
import { listWarehouses } from '@/api/resources';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { StatusChip } from '@/components/StatusChip';
import { t } from '@/i18n';
import { ModuleGate, MvpModuleBanner } from '@/pages/erp/erpShared';
import { documentStatusTone, statusLabelKey } from '@/utils/status';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';

const PAGE_SIZE = 50;

type WoForm = {
  bom: number | '';
  qty: string;
  warehouse: number | '';
  batchNo: string;
  expDate: string;
  mfgDate: string;
};

const emptyForm = (): WoForm => ({ bom: '', qty: '1', warehouse: '', batchNo: '', expDate: '', mfgDate: '' });

function parseSerials(text: string): string[] {
  return text
    .split(/[\n,]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function parseComponentSerials(text: string): Record<string, string[]> | undefined {
  const trimmed = text.trim();
  if (!trimmed) return undefined;
  if (trimmed.startsWith('{')) {
    try {
      const parsed = JSON.parse(trimmed) as unknown;
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        return parsed as Record<string, string[]>;
      }
    } catch {
      return undefined;
    }
  }
  const map: Record<string, string[]> = {};
  for (const line of trimmed.split('\n')) {
    const idx = line.indexOf(':');
    if (idx < 0) continue;
    const id = line.slice(0, idx).trim();
    const rest = line.slice(idx + 1);
    if (!id) continue;
    map[id] = parseSerials(rest);
  }
  return Object.keys(map).length ? map : undefined;
}

export function WorkOrdersPage() {
  return (
    <ModuleGate module="manufacturing" title={t('nav.workOrders')}>
      <WorkOrdersPageInner />
    </ModuleGate>
  );
}

function WorkOrdersPageInner() {
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<WorkOrder | null>(null);
  const [form, setForm] = useState<WoForm>(emptyForm);
  const [error, setError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<{ action: 'release' | 'complete' | 'cancel'; id: number } | null>(
    null,
  );
  const [serialText, setSerialText] = useState('');
  const [componentSerialsText, setComponentSerialsText] = useState('');

  const query = useQuery({
    queryKey: ['work-orders', page],
    queryFn: () => listWorkOrdersPage({ page, pageSize: PAGE_SIZE }),
  });
  const bomsQuery = useQuery({
    queryKey: ['boms', 'all'],
    queryFn: () => listBomsPage({ page: 1, pageSize: 200 }),
  });
  const warehousesQuery = useQuery({ queryKey: ['warehouses'], queryFn: listWarehouses });

  const bomMap = useMemo(() => {
    const map = new Map<number, string>();
    for (const b of bomsQuery.data?.results ?? []) map.set(b.id, b.name);
    return map;
  }, [bomsQuery.data]);

  const warehouseMap = useMemo(() => {
    const map = new Map<number, string>();
    for (const w of warehousesQuery.data ?? []) map.set(w.id, w.name);
    return map;
  }, [warehousesQuery.data]);

  const rows = query.data?.results ?? [];

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        bom: Number(form.bom),
        qty: form.qty,
        warehouse: form.warehouse ? Number(form.warehouse) : null,
        batchNo: form.batchNo || undefined,
        expDate: form.expDate || null,
        mfgDate: form.mfgDate || null,
      };
      if (editing) return updateWorkOrder(editing.id, payload);
      return createWorkOrder(payload);
    },
    onSuccess: () => {
      setOpen(false);
      setEditing(null);
      setForm(emptyForm());
      void qc.invalidateQueries({ queryKey: ['work-orders'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const releaseMutation = useMutation({
    mutationFn: ({ id, componentSerials }: { id: number; componentSerials?: Record<string, string[]> }) =>
      releaseWorkOrder(id, { componentSerials }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['work-orders'] }),
    onError: (err) => setError(getErrorMessage(err)),
  });

  const completeMutation = useMutation({
    mutationFn: ({
      id,
      serialNumbers,
      batchNo,
      expDate,
      mfgDate,
    }: {
      id: number;
      serialNumbers?: string[];
      batchNo?: string;
      expDate?: string | null;
      mfgDate?: string | null;
    }) => completeWorkOrder(id, { serialNumbers, batchNo, expDate, mfgDate }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['work-orders'] }),
    onError: (err) => setError(getErrorMessage(err)),
  });

  const cancelMutation = useMutation({
    mutationFn: (id: number) => cancelWorkOrder(id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['work-orders'] }),
    onError: (err) => setError(getErrorMessage(err)),
  });

  const openCreate = () => {
    setEditing(null);
    setForm(emptyForm());
    setOpen(true);
  };

  const openEdit = (wo: WorkOrder) => {
    if (wo.status !== 'DRAFT') return;
    setEditing(wo);
    setForm({
      bom: wo.bom,
      qty: wo.qty,
      warehouse: wo.warehouse ?? '',
      batchNo: wo.batchNo ?? '',
      expDate: wo.expDate ?? '',
      mfgDate: wo.mfgDate ?? '',
    });
    setOpen(true);
  };

  return (
    <Stack spacing={2}>
      <MvpModuleBanner module="manufacturing" />
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="h4">{t('nav.workOrders')}</Typography>
        <Button variant="contained" onClick={openCreate}>
          {t('common.add')}
        </Button>
      </Stack>
      {error ? <HelpErrorAlert message={error} /> : null}
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {rows.length === 0 && !query.isLoading && !query.isError ? (
        <EmptyState description={t('empty.workOrders')} />
      ) : null}
      {rows.length > 0 ? (
        <Paper sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>ID</TableCell>
                <TableCell>{t('nav.boms')}</TableCell>
                <TableCell>{t('erp.qty')}</TableCell>
                <TableCell>{t('nav.warehouses')}</TableCell>
                <TableCell>{t('common.status')}</TableCell>
                <TableCell align="right">{t('common.actions')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((wo) => (
                <TableRow key={wo.id}>
                  <TableCell>{wo.id}</TableCell>
                  <TableCell>{bomMap.get(wo.bom) ?? wo.bom}</TableCell>
                  <TableCell>{wo.qty}</TableCell>
                  <TableCell>
                    {wo.warehouse ? warehouseMap.get(wo.warehouse) ?? wo.warehouse : '—'}
                  </TableCell>
                  <TableCell>
                    <StatusChip
                      tone={documentStatusTone(wo.status)}
                      labelKey={statusLabelKey(wo.status)}
                    />
                  </TableCell>
                  <TableCell align="right">
                    {wo.status === 'DRAFT' ? (
                      <>
                        <Button size="small" onClick={() => openEdit(wo)}>
                          {t('common.edit')}
                        </Button>
                        <Button
                          size="small"
                          disabled={releaseMutation.isPending}
                          onClick={() => {
                            setSerialText('');
                            setComponentSerialsText('');
                            setConfirm({ action: 'release', id: wo.id });
                          }}
                        >
                          {t('erp.release')}
                        </Button>
                      </>
                    ) : null}
                    {wo.status === 'RELEASED' ? (
                      <>
                        <Button
                          size="small"
                          disabled={completeMutation.isPending}
                          onClick={() => {
                            setSerialText('');
                            setConfirm({ action: 'complete', id: wo.id });
                          }}
                        >
                          {t('common.complete')}
                        </Button>
                        <Button
                          size="small"
                          color="warning"
                          disabled={cancelMutation.isPending}
                          onClick={() => setConfirm({ action: 'cancel', id: wo.id })}
                        >
                          {t('common.cancel')}
                        </Button>
                      </>
                    ) : null}
                    {wo.status === 'COMPLETED' ? (
                      <Button
                        size="small"
                        color="warning"
                        disabled={cancelMutation.isPending}
                        onClick={() => setConfirm({ action: 'cancel', id: wo.id })}
                      >
                        {t('common.cancel')}
                      </Button>
                    ) : null}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}
      {query.data && (query.data.next || page > 1) ? (
        <Stack direction="row" spacing={1} justifyContent="flex-end" alignItems="center">
          <Typography variant="body2" color="text.secondary">
            {t('common.page')} {page}
          </Typography>
          <Button variant="outlined" size="small" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            {t('common.previous')}
          </Button>
          <Button
            variant="outlined"
            size="small"
            disabled={!query.data.next}
            onClick={() => setPage((p) => p + 1)}
          >
            {t('common.next')}
          </Button>
        </Stack>
      ) : null}

      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm" aria-labelledby="wo-dialog-title">
        <DialogTitle id="wo-dialog-title">{editing ? t('common.edit') : t('common.create')} {t('erp.workOrder')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              select
              label={t('nav.boms')}
              required
              value={form.bom}
              onChange={(e) => setForm((f) => ({ ...f, bom: Number(e.target.value) }))}
            >
              <MenuItem value="">—</MenuItem>
              {(bomsQuery.data?.results ?? []).map((b) => (
                <MenuItem key={b.id} value={b.id}>
                  {b.name}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label={t('erp.qty')}
              type="number"
              required
              value={form.qty}
              onChange={(e) => setForm((f) => ({ ...f, qty: e.target.value }))}
            />
            <TextField
              select
              label={t('nav.warehouses')}
              value={form.warehouse}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  warehouse: e.target.value ? Number(e.target.value) : '',
                }))
              }
            >
              <MenuItem value="">—</MenuItem>
              {(warehousesQuery.data ?? []).map((w) => (
                <MenuItem key={w.id} value={w.id}>
                  {w.name}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label={t('erp.batchNo')}
              value={form.batchNo}
              onChange={(e) => setForm((f) => ({ ...f, batchNo: e.target.value }))}
            />
            <TextField
              type="date"
              label={t('erp.expDate')}
              value={form.expDate}
              onChange={(e) => setForm((f) => ({ ...f, expDate: e.target.value }))}
              InputLabelProps={{ shrink: true }}
            />
            <TextField
              type="date"
              label={t('erp.mfgDate')}
              value={form.mfgDate}
              onChange={(e) => setForm((f) => ({ ...f, mfgDate: e.target.value }))}
              InputLabelProps={{ shrink: true }}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={!form.bom || !form.qty || saveMutation.isPending}
            onClick={() => saveMutation.mutate()}
          >
            {t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog
        open={confirm?.action === 'release' || confirm?.action === 'complete'}
        onClose={() => setConfirm(null)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>
          {confirm?.action === 'release' ? t('erp.release') : t('common.complete')}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Typography variant="body2">
              {confirm?.action === 'release' ? t('erp.confirmReleaseWo') : t('erp.confirmCompleteWo')}
            </Typography>
            {confirm?.action === 'release' ? (
              <TextField
                label={t('erp.componentSerials')}
                helperText={t('erp.componentSerialsHint')}
                multiline
                minRows={3}
                value={componentSerialsText}
                onChange={(e) => setComponentSerialsText(e.target.value)}
              />
            ) : (
              <TextField
                label={t('erp.serialNumbers')}
                helperText={t('erp.serialNumbersHint')}
                multiline
                minRows={3}
                value={serialText}
                onChange={(e) => setSerialText(e.target.value)}
              />
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirm(null)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={releaseMutation.isPending || completeMutation.isPending}
            onClick={() => {
              if (!confirm) return;
              if (confirm.action === 'release') {
                releaseMutation.mutate({
                  id: confirm.id,
                  componentSerials: parseComponentSerials(componentSerialsText),
                });
              } else if (confirm.action === 'complete') {
                const wo = rows.find((r) => r.id === confirm.id);
                completeMutation.mutate({
                  id: confirm.id,
                  serialNumbers: parseSerials(serialText),
                  batchNo: wo?.batchNo || form.batchNo || undefined,
                  expDate: wo?.expDate || form.expDate || null,
                  mfgDate: wo?.mfgDate || form.mfgDate || null,
                });
              }
              setConfirm(null);
            }}
          >
            {t('common.confirm')}
          </Button>
        </DialogActions>
      </Dialog>
      <ConfirmDialog
        open={confirm?.action === 'cancel'}
        title={t('common.cancel')}
        body={t('erp.confirmCancelWo')}
        confirmColor="warning"
        confirming={cancelMutation.isPending}
        onClose={() => setConfirm(null)}
        onConfirm={() => {
          if (!confirm) return;
          cancelMutation.mutate(confirm.id);
          setConfirm(null);
        }}
      />
    </Stack>
  );
}
