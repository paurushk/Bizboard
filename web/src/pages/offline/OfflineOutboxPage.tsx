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
import { createPurchase, createSalesInvoice, updatePurchase, updateSalesInvoice, postStockCount, updateStockCount, completeTransfer } from '@/api/resources';
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
          if (draft.invoiceId) {
            await updatePurchase(draft.invoiceId, draft.payload as never);
          } else {
            await createPurchase(draft.payload as never, { idempotencyKey: draft.idempotencyKey });
          }
          return;
        }
        if (draft.kind === 'invoice') {
          if (draft.invoiceId) {
            await updateSalesInvoice(draft.invoiceId, draft.payload as never);
          } else {
            await createSalesInvoice(draft.payload as never, { idempotencyKey: draft.idempotencyKey });
          }
          return;
        }
        if (draft.kind === 'stock_count') {
          const sessionId = Number(draft.payload.sessionId);
          const lines = draft.payload.lines as Record<string, string> | undefined;
          if (lines && Object.keys(lines).length) {
            await updateStockCount(sessionId, {
              lines: Object.entries(lines).map(([id, countedQty]) => ({ id: Number(id), countedQty })),
            });
          }
          const resolve = String(draft.payload.resolveConflicts || '');
          await postStockCount(
            sessionId,
            resolve ? { resolveConflicts: resolve } : {},
            { idempotencyKey: draft.idempotencyKey },
          );
          return;
        }
        if (draft.kind === 'stock_transfer') {
          await completeTransfer(Number(draft.payload.transferId));
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
    await removeDraft(companyId, userId, draft.idempotencyKey);
    await reload();
  };

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="h4">{t('offlineOutbox.title')}</Typography>
        <Button variant="contained" disabled={busy || !navigator.onLine} onClick={() => void syncNow()}>
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
                      <Button size="small" color="warning" onClick={() => void deleteOne(row)}>
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
    </Stack>
  );
}
