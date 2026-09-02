import { useEffect } from 'react';
import { completeTransfer, postStockCount, updateStockCount } from '@/api/resources';
import { t } from '@/i18n';
import { flushOutbox, listDrafts, type OutboxDraft } from '@/offline/invoiceDraftCache';

/** Flush one queued stock count or transfer — shared with OfflineOutboxPage. */
export async function flushStockDraft(draft: OutboxDraft): Promise<void> {
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
    await completeTransfer(Number(draft.payload.transferId), {
      idempotencyKey: draft.idempotencyKey,
    });
    return;
  }
  throw new Error(t('pos.syncFailed'));
}

/** Flush queued stock counts/transfers when the browser is online. */
export function useStockOffline(
  companyId: number,
  userId: number,
  setOutboxBanner?: (msg: string | null) => void,
): void {
  useEffect(() => {
    if (!companyId || !userId) return;
    const flush = async () => {
      const pending = (await listDrafts(companyId, userId)).filter(
        (d) => d.kind === 'stock_count' || d.kind === 'stock_transfer',
      );
      if (pending.length && setOutboxBanner) setOutboxBanner(t('billing.offlineOutboxPending'));
      const result = await flushOutbox(
        companyId,
        userId,
        async (draft) => {
          await flushStockDraft(draft);
        },
        (draft) => draft.kind === 'stock_count' || draft.kind === 'stock_transfer',
      );
      if (!setOutboxBanner) return;
      if (result.failed > 0) {
        setOutboxBanner(
          t('offlineOutbox.syncFailed', {
            failed: String(result.failed),
            errors: result.errors.slice(0, 3).join(' · '),
          }),
        );
        return;
      }
      const left = (await listDrafts(companyId, userId)).filter(
        (d) => d.kind === 'stock_count' || d.kind === 'stock_transfer',
      );
      setOutboxBanner(left.length ? t('billing.offlineOutboxPending') : null);
    };
    const onOnline = () => void flush();
    window.addEventListener('online', onOnline);
    void flush();
    return () => window.removeEventListener('online', onOnline);
  }, [companyId, userId, setOutboxBanner]);
}
