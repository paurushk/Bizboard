import { useEffect, useRef } from 'react';
import { completeTransfer, postStockCount, updateStockCount } from '@/api/resources';
import { t } from '@/i18n';
import { flushOutbox, listDrafts, removeDraft, type OutboxDraft } from '@/offline/invoiceDraftCache';
import { parseStockCountConflicts, type QtyConflict } from '@/pages/inventory/godownConflict';

/** CR-143: StockCountPage listens for offline flush 409s. */
export const STOCK_COUNT_CONFLICT_EVENT = 'bizboard:stock-count-conflict';

export type StockCountConflictDetail = {
  conflicts: QtyConflict[];
  sessionId: number;
  idempotencyKey: string;
  companyId: number;
  userId: number;
};

/** Retry a conflicted offline stock-count draft with KEEP_SERVER / KEEP_LOCAL. */
export async function resolveOfflineStockCountConflict(opts: {
  sessionId: number;
  resolve: 'KEEP_SERVER' | 'KEEP_LOCAL';
  idempotencyKey: string;
  companyId: number;
  userId: number;
}): Promise<void> {
  await postStockCount(
    opts.sessionId,
    { resolveConflicts: opts.resolve },
    { idempotencyKey: opts.idempotencyKey },
  );
  await removeDraft(opts.companyId, opts.userId, opts.idempotencyKey);
}

/** Flush one queued stock count or transfer — shared with OfflineOutboxPage. */
export async function flushStockDraft(
  draft: OutboxDraft,
  context?: { companyId?: number; userId?: number },
): Promise<void> {
  if (draft.kind === 'stock_count') {
    const sessionId = Number(draft.payload.sessionId);
    const lines = draft.payload.lines as Record<string, string> | undefined;
    if (lines && Object.keys(lines).length) {
      await updateStockCount(sessionId, {
        lines: Object.entries(lines).map(([id, countedQty]) => ({ id: Number(id), countedQty })),
      });
    }
    const resolve = String(draft.payload.resolveConflicts || '');
    try {
      await postStockCount(
        sessionId,
        resolve ? { resolveConflicts: resolve } : {},
        { idempotencyKey: draft.idempotencyKey },
      );
      return;
    } catch (err) {
      const conflicts = parseStockCountConflicts(err);
      if (conflicts?.length && context?.companyId != null && context?.userId != null) {
        const detail: StockCountConflictDetail = {
          conflicts,
          sessionId,
          idempotencyKey: draft.idempotencyKey,
          companyId: context.companyId,
          userId: context.userId,
        };
        window.dispatchEvent(
          new CustomEvent(STOCK_COUNT_CONFLICT_EVENT, { detail }),
        );
      }
      throw err;
    }
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
  const bannerRef = useRef(setOutboxBanner);
  bannerRef.current = setOutboxBanner;
  const flushGuard = useRef(false);

  useEffect(() => {
    if (!companyId || !userId) return;
    const setBanner = (msg: string | null) => bannerRef.current?.(msg);
    const flush = async () => {
      if (flushGuard.current || (typeof navigator !== 'undefined' && !navigator.onLine)) return;
      flushGuard.current = true;
      try {
        const pending = (await listDrafts(companyId, userId)).filter(
          (d) => d.kind === 'stock_count' || d.kind === 'stock_transfer',
        );
        if (pending.length) setBanner(t('billing.offlineOutboxPending'));

        // CR-143: flush stock_count one-by-one so 409 can surface the conflict modal.
        for (const draft of pending.filter((d) => d.kind === 'stock_count')) {
          try {
            await flushStockDraft(draft, { companyId, userId });
            await removeDraft(companyId, userId, draft.idempotencyKey);
          } catch (err) {
            const conflicts = parseStockCountConflicts(err);
            if (conflicts?.length) {
              setBanner(t('inventory.conflictTitle'));
              return;
            }
            setBanner(
              t('offlineOutbox.syncFailed', {
                failed: '1',
                errors: err instanceof Error ? err.message : String(err),
              }),
            );
            return;
          }
        }

        const result = await flushOutbox(
          companyId,
          userId,
          async (draft) => {
            await flushStockDraft(draft);
          },
          (draft) => draft.kind === 'stock_transfer',
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
        setBanner(
          t('offlineOutbox.syncFailed', {
            failed: '?',
            errors: err instanceof Error ? err.message : String(err),
          }),
        );
      } finally {
        flushGuard.current = false;
      }
    };
    const onOnline = () => void flush();
    window.addEventListener('online', onOnline);
    void flush();
    return () => window.removeEventListener('online', onOnline);
  }, [companyId, userId]);
}
