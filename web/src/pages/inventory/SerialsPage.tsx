import { useEffect, useRef, useState } from 'react';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Typography from '@mui/material/Typography';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { useAuth } from '@/auth/AuthContext';
import { AttemptKeys } from '@/pages/inventory/attemptKeys';
import * as api from '@/api/resources';
import { ErrorState, LoadingState } from '@/components/PageState';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { enumLabel } from '@/utils/enumLabels';
import { t } from '@/i18n';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import Alert from '@mui/material/Alert';
import { serialActionsFor } from '@/pages/inventory/serialActions';
import { asRows, DataTable, PageShell } from '@/pages/phase/phaseShared';
import { useConfirmPrompt } from '@/hooks/useConfirmPrompt';

const STATUSES = ['AVAILABLE', 'SOLD', 'RETURNED', 'SCRAPPED'];

export function SerialsPage() {
  const { writesBlocked } = useSubscriptionGate();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { ask, dialog } = useConfirmPrompt();
  const [statusFilter, setStatusFilter] = useState('');
  const [search, setSearch] = useState('');
  const [debounced, setDebounced] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const { user } = useAuth();
  const isOwner = user?.role === 'OWNER';
  // One key per attempt: kept while the outcome is unknown, dropped once the server answered.
  const attemptKeys = useRef(new AttemptKeys());
  const [manualReturn, setManualReturn] = useState<{ id: number; serial: string } | null>(null);
  const [manualReason, setManualReason] = useState('');

  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(search.trim()), 300);
    return () => window.clearTimeout(id);
  }, [search]);

  const query = useQuery({
    queryKey: ['serials', statusFilter, debounced],
    queryFn: () =>
      api.listSerials({
        ...(statusFilter ? { status: statusFilter } : {}),
        ...(debounced ? { q: debounced } : {}),
      }),
  });
  const transition = useMutation({
    mutationFn: ({ id, status, extra }: { id: number; status: string; extra?: Record<string, unknown> }) =>
      api.transitionSerial(id, { status, ...extra }, { idempotencyKey: attemptKeys.current.get(`serial-${id}-${status}`) }),
    onSuccess: (result, { id, status }) => {
      attemptKeys.current.settle(`serial-${id}-${status}`);
      setManualReturn(null);
      setManualReason('');
      setError('');
      // 202: the owner has to approve the scrap; the serial and the stock are unchanged until then.
      setNotice((result as { status?: string } | null)?.status === 'PENDING' ? t('inventory.stockPendingApproval') : '');
      void qc.invalidateQueries({ queryKey: ['serials'] });
      // A serial moving in or out of stock changes the balance everywhere it is shown.
      void qc.invalidateQueries({ queryKey: ['stock'] });
      void qc.invalidateQueries({ queryKey: ['low-stock'] });
    },
    onError: (e, { id, status }) => {
      attemptKeys.current.settle(`serial-${id}-${status}`, e);
      setError(getErrorMessage(e));
    },
  });
  // UXW2B-017: show the resolved names the API now joins instead of raw FK ids.
  const rows = asRows(query.data).map((r) => ({
    ...r,
    product: r.productName ?? r.product,
    warehouse: r.warehouseName ?? r.warehouse ?? '—',
  }));
  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />;
  return (
    <PageShell
      title={t('phase.serials')}
      subtitle={`${t('phase.serialsSubtitle')} ${t('inventory.serialSubtitleHint')}`}
      actions={
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
          <TextField
            size="small"
            label={t('inventory.serialSearch')}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            sx={{ minWidth: 220 }}
          />
          <TextField
            select
            size="small"
            label={t('sweep.status')}
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            sx={{ minWidth: 160 }}
          >
            <MenuItem value="">{t('sweep2.all')}</MenuItem>
            {STATUSES.map((s) => (
              <MenuItem key={s} value={s}>
                {enumLabel('serialStatus', s)}
              </MenuItem>
            ))}
          </TextField>
        </Stack>
      }
    >
      {error ? <HelpErrorAlert message={error} /> : null}
      {notice ? <Alert severity="info" onClose={() => setNotice('')}>{notice}</Alert> : null}
      <DataTable
        rows={rows}
        empty={t('inventory.serialEmpty')}
        // F3-016: listSerials() walks every serial number tracked —
        // window the DOM rows instead of rendering them all at once.
        virtualized
        columns={[
          { key: 'serialNumber', label: t('inventory.serialColSerial') },
          { key: 'product', label: t('common.product') },
          { key: 'warehouse', label: t('items.godown') },
          { key: 'status', label: t('sweep.status'), status: true, statusLabel: (raw) => enumLabel('serialStatus', raw) },
        ]}
        actions={(row) => (
          <Stack direction="row" spacing={1} alignItems="center" justifyContent="flex-end">
            {String(row.status) === 'SOLD' ? (
              <Button
                size="small"
                onClick={() => {
                  setError('');
                  api
                    .getSerialDocument(Number(row.id))
                    .then((doc) => {
                      if (doc) navigate(doc.path);
                      else setError(t('inventory.serialNoDocument'));
                    })
                    .catch((e) => setError(getErrorMessage(e)));
                }}
              >
                {t('inventory.serialViewSale')}
              </Button>
            ) : null}
            {String(row.status) === 'SOLD' ? (
              <Button
                size="small"
                variant="outlined"
                onClick={() => {
                  setError('');
                  api
                    .getSerialDocument(Number(row.id))
                    .then((doc) => {
                      if (!doc) setError(t('inventory.serialNoDocument'));
                      // An invoice opens the sales return form for that invoice; a challan opens the challan.
                      else navigate(doc.type === 'invoice' ? `/sales/returns?invoice=${doc.id}` : doc.path);
                    })
                    .catch((e) => setError(getErrorMessage(e)));
                }}
              >
                {t('inventory.serialCreateReturn')}
              </Button>
            ) : null}
            {String(row.status) === 'SOLD' && isOwner ? (
              <Button
                size="small"
                color="warning"
                disabled={writesBlocked || transition.isPending}
                onClick={() => setManualReturn({ id: Number(row.id), serial: String(row.serialNumber) })}
              >
                {t('inventory.serialManualReturn')}
              </Button>
            ) : null}
            {serialActionsFor(String(row.status)).map((action) => (
              <Button
                key={action.target}
                size="small"
                color={action.tone}
                disabled={writesBlocked || transition.isPending}
                onClick={async () => {
                  const message = t(action.confirmKey, {
                    serial: String(row.serialNumber),
                    godown: String(row.warehouse),
                  });
                  if (!(await ask([message]))) return;
                  transition.mutate({ id: Number(row.id), status: action.target });
                }}
              >
                {t(action.labelKey)}
              </Button>
            ))}
          </Stack>
        )}
      />
      {dialog}
      <Dialog open={Boolean(manualReturn)} onClose={() => setManualReturn(null)} fullWidth maxWidth="xs">
        <DialogTitle>{t('inventory.serialManualReturnTitle', { serial: manualReturn?.serial ?? '' })}</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 2 }}>{t('inventory.serialManualReturnHelp')}</Typography>
          <TextField
            autoFocus
            fullWidth
            required
            multiline
            minRows={2}
            label={t('inventory.serialManualReturnReason')}
            value={manualReason}
            onChange={(e) => setManualReason(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setManualReturn(null)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            color="warning"
            disabled={writesBlocked || transition.isPending || !manualReason.trim()}
            onClick={() =>
              manualReturn &&
              transition.mutate({
                id: manualReturn.id,
                status: 'AVAILABLE',
                extra: { reason: manualReason.trim(), confirmNoDocument: true },
              })
            }
          >
            {t('inventory.serialManualReturnConfirm')}
          </Button>
        </DialogActions>
      </Dialog>
    </PageShell>
  );
}
