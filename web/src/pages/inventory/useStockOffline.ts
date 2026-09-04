import { useEffect, useRef } from 'react';
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
  // F3-041: read the (often unmemoised) setter through a ref so the effect
  // below only re-runs on companyId/userId — not on every parent render, which
  // used to churn the `online` listener and re-fire flush() each time.
  const bannerRef = useRef(setOutboxBanner);
  bannerRef.current = setOutboxBanner;

  useEffect(() => {
    if (!companyId || !userId) return;
    const setBanner = (msg: string | null) => bannerRef.current?.(msg);
    const flush = async () => {
      try {
        const pending = (await listDrafts(companyId, userId)).filter(
          (d) => d.kind === 'stock_count' || d.kind === 'stock_transfer',
        );
        if (pending.length) setBanner(t('billing.offlineOutboxPending'));
        const result = await flushOutbox(
          companyId,
          userId,
          async (draft) => {
            await flushStockDraft(draft);
          },
          (draft) => draft.kind === 'stock_count' || draft.kind === 'stock_transfer',
        );
        if (result.failed > 0) {
          setBanner(
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
        setBanner(left.length ? t('billing.offlineOutboxPending') : null);
      } catch (err) {
        // F3-041: a rejected listDrafts/flush must not silently kill sync.
        setBanner(
          t('offlineOutbox.syncFailed', {
            failed: '?',
            errors: err instanceof Error ? err.message : String(err),
          }),
        );
      }
    };
    const onOnline = () => void flush();
    window.addEventListener('online', onOnline);
    void flush();
    return () => window.removeEventListener('online', onOnline);
  }, [companyId, userId]);
}
