import { useCallback, useEffect, useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import { useAuth } from '@/auth/AuthContext';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { EmptyState } from '@/components/PageState';
import { t } from '@/i18n';
import {
  flushOutbox,
  isFlushableDraft,
  listDrafts,
  PURCHASE_AUTOSAVE_KEY,
  removeDraft,
  type OutboxDraft,
} from '@/offline/invoiceDraftCache';
import { flushPosDraft } from '@/offline/flushPosCheckout';
import { flushInvoiceDraft } from '@/pages/sales/invoice/useInvoiceOffline';
import { flushPurchaseDraft } from '@/pages/purchases/usePurchaseOffline';
import { flushStockDraft } from '@/pages/inventory/useStockOffline';
import { getErrorMessage } from '@/api/client';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';

function kindLabel(kind: OutboxDraft['kind']): string {
  if (kind === 'invoice') return t('offlineOutbox.invoiceDrafts');
  if (kind === 'purchase') return t('offlineOutbox.purchaseDrafts');
  if (kind === 'stock_count') return t('offlineOutbox.stockCountDrafts');
  if (kind === 'stock_transfer') return t('offlineOutbox.stockTransferDrafts');
  return t('offlineOutbox.posDrafts');
}

export function OfflineOutboxPage() {
  const { user } = useAuth();
  const [drafts, setDrafts] = useState<OutboxDraft[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<OutboxDraft | null>(null);
  // F2-055: re-enable "Sync now" as soon as connectivity returns.
  const [online, setOnline] = useState(
    typeof navigator === 'undefined' ? true : navigator.onLine,
  );
  useEffect(() => {
    const set = () => setOnline(navigator.onLine);
    window.addEventListener('online', set);
    window.addEventListener('offline', set);
    return () => {
      window.removeEventListener('online', set);
      window.removeEventListener('offline', set);
    };
  }, []);

  const companyId = user?.companyId;
  const userId = user?.id;

  const reload = useCallback(async () => {
    if (!companyId || !userId) {
      setDrafts([]);
      return;
    }
    const rows = await listDrafts(companyId, userId);
    setDrafts(rows);
  }, [companyId, userId]);

  useEffect(() => {
    void reload().catch(() => setDrafts([]));
  }, [reload]);

  const syncNow = async () => {
    if (!companyId || !userId) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const result = await flushOutbox(companyId, userId, async (draft) => {
        if (draft.kind === 'purchase') {
          await flushPurchaseDraft(draft);
          return;
        }
        if (draft.kind === 'pos') {
          await flushPosDraft(draft);
          return;
        }
        if (draft.kind === 'invoice') {
          await flushInvoiceDraft(draft);
          return;
        }
        if (draft.kind === 'stock_count' || draft.kind === 'stock_transfer') {
          await flushStockDraft(draft);
          return;
        }
        throw new Error(t('pos.syncFailed'));
      });
      if (result.failed > 0) {
        setError(
          t('offlineOutbox.syncFailed', {
            failed: String(result.failed),
            errors: result.errors.slice(0, 3).join(' · '),
          }),
        );
      } else if (result.flushed > 0) {
        setMessage(t('offlineOutbox.synced', { count: String(result.flushed) }));
      }
      await reload();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const deleteOne = async (draft: OutboxDraft) => {
    if (!companyId || !userId) return;
    try {
      await removeDraft(companyId, userId, draft.idempotencyKey);
      await reload();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="h4">{t('offlineOutbox.title')}</Typography>
        <Button
          variant="contained"
          disabled={busy || !online}
          aria-busy={busy}
          onClick={() => void syncNow()}
        >
          {t('offlineOutbox.syncNow')}
        </Button>
      </Stack>
      <Alert severity="warning">{t('offlineOutbox.subtitle')}</Alert>
      {error ? <HelpErrorAlert message={error} /> : null}
      {message ? <Alert severity="success">{message}</Alert> : null}
      {drafts.length === 0 ? (
        <EmptyState description={t('offlineOutbox.empty')} />
      ) : (
        <Paper sx={{ overflow: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('offlineOutbox.kind')}</TableCell>
                <TableCell>{t('common.date')}</TableCell>
                <TableCell>{t('offlineOutbox.draftId')}</TableCell>
                <TableCell>{t('common.status')}</TableCell>
                <TableCell align="right">{t('common.actions')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {drafts.map((row) => {
                const localOnly = row.idempotencyKey === PURCHASE_AUTOSAVE_KEY || !isFlushableDraft(row);
                return (
                  <TableRow key={row.id}>
                    <TableCell>{kindLabel(row.kind)}</TableCell>
                    <TableCell>{row.savedAt ? new Date(row.savedAt).toLocaleString() : '—'}</TableCell>
                    <TableCell>{row.id}</TableCell>
                    <TableCell>
                      {localOnly ? t('offlineOutbox.localAutosave') : t('offlineOutbox.queued')}
                    </TableCell>
                    <TableCell align="right">
                      <Button
                        size="small"
                        color="warning"
                        onClick={() => (localOnly ? void deleteOne(row) : setConfirmDelete(row))}
                      >
                        {t('common.delete')}
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </Paper>
      )}
      <ConfirmDialog
        open={confirmDelete !== null}
        title={t('offlineOutbox.deleteTitle')}
        body={t('offlineOutbox.deleteBody')}
        confirmLabel={t('common.delete')}
        confirmColor="error"
        onClose={() => setConfirmDelete(null)}
        onConfirm={() => {
          const row = confirmDelete;
          setConfirmDelete(null);
          if (row) void deleteOne(row);
        }}
      />
    </Stack>
  );
}
