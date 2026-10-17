import { useEffect, useLayoutEffect, useRef } from 'react';
import { completeTransfer, postStockCount, updateStockCount } from '@/api/resources';
import { t } from '@/i18n';
import { flushOutbox, listDrafts, removeDraft, type OutboxDraft } from '@/offline/invoiceDraftCache';
import { parseStockCountConflicts, type QtyConflict } from '@/pages/inventory/godownConflict';

/** CR-143: StockCountPage listens for offline flush 409s. */
export const STOCK_COUNT_CONFLICT_EVENT = 'bizboard:stock-count-conflict';

/** The app shell owns the flush; a page asks for another pass (e.g. after it starts listening for conflicts). */
export const STOCK_FLUSH_REQUEST_EVENT = 'bizboard:stock-outbox-flush';
/** Fired after queued stock work reached the server, so open lists can refetch. */
export const STOCK_FLUSHED_EVENT = 'bizboard:stock-outbox-flushed';

export function requestStockFlush(): void {
  window.dispatchEvent(new Event(STOCK_FLUSH_REQUEST_EVENT));
}

export type StockCountConflictDetail = {
  conflicts: QtyConflict[];
  sessionId: number;
  idempotencyKey: string;
  companyId: number;
  userId: number;
};

/** Retry a conflicted offline stock-count draft with an answer for each drifted line. */
export async function resolveOfflineStockCountConflict(opts: {
  sessionId: number;
  resolutions: Record<number, 'ADJUST_FOR_MOVEMENTS' | 'KEEP_SERVER' | 'KEEP_LOCAL'>;
  recheckedLineIds?: number[];
  idempotencyKey: string;
  companyId: number;
  userId: number;
}): Promise<void> {
  await postStockCount(
    opts.sessionId,
    {
      resolutions: opts.resolutions,
      ...(opts.recheckedLineIds?.length ? { recheckedLineIds: opts.recheckedLineIds } : {}),
    },
    { idempotencyKey: opts.idempotencyKey },
  );
  await removeDraft(opts.companyId, opts.userId, opts.idempotencyKey);
}

/** Flush one queued stock count or transfer — shared with OfflineOutboxPage.
 *  Resolves with ``heldForApproval`` when the server took a count but is waiting for the owner. */
export async function flushStockDraft(
  draft: OutboxDraft,
  context?: { companyId?: number; userId?: number },
): Promise<{ heldForApproval: boolean }> {
  if (draft.kind === 'stock_count') {
    const sessionId = Number(draft.payload.sessionId);
    const lines = draft.payload.lines as Record<string, string> | undefined;
    if (lines && Object.keys(lines).length) {
      await updateStockCount(sessionId, {
        lines: Object.entries(lines).map(([id, countedQty]) => ({ id: Number(id), countedQty })),
      });
    }
    const resolve = String(draft.payload.resolveConflicts || '');
    const recheckedLineIds = Array.isArray(draft.payload.recheckedLineIds) ? draft.payload.recheckedLineIds : [];
    const resolutions = draft.payload.resolutions as Record<string, string> | undefined;
    try {
      const posted = await postStockCount(
        sessionId,
        {
          ...(resolve ? { resolveConflicts: resolve } : {}),
          ...(resolutions && Object.keys(resolutions).length ? { resolutions } : {}),
          ...(recheckedLineIds.length ? { recheckedLineIds } : {}),
        },
        { idempotencyKey: draft.idempotencyKey },
      );
      return { heldForApproval: (posted as { status?: string } | null)?.status === 'PENDING' };
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
    return { heldForApproval: false };
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
  useLayoutEffect(() => {
    bannerRef.current = setOutboxBanner;
  });
  const flushGuard = useRef(false);

  useEffect(() => {
    if (!companyId || !userId) return;
    const setBanner = (msg: string | null) => bannerRef.current?.(msg);
    const flush = async () => {
      if (flushGuard.current || (typeof navigator !== 'undefined' && !navigator.onLine)) return;
      flushGuard.current = true;
      let sent = 0;
      let held = 0;
      try {
        const pending = (await listDrafts(companyId, userId)).filter(
          (d) => d.kind === 'stock_count' || d.kind === 'stock_transfer',
        );
        if (pending.length) setBanner(t('billing.offlineOutboxPending'));

        // CR-143: flush stock_count one-by-one so 409 can surface the conflict modal.
        for (const draft of pending.filter((d) => d.kind === 'stock_count')) {
          try {
            const outcome = await flushStockDraft(draft, { companyId, userId });
            await removeDraft(companyId, userId, draft.idempotencyKey);
            sent += 1;
            if (outcome.heldForApproval) held += 1;
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
        sent += result.flushed;
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
        setBanner(
          left.length ? t('billing.offlineOutboxPending') : held ? t('inventory.queuedCountHeld', { count: String(held) }) : null,
        );
      } catch (err) {
        setBanner(
          t('offlineOutbox.syncFailed', {
            failed: '?',
            errors: err instanceof Error ? err.message : String(err),
          }),
        );
      } finally {
        flushGuard.current = false;
        if (sent > 0) window.dispatchEvent(new Event(STOCK_FLUSHED_EVENT));
      }
    };
    const onOnline = () => void flush();
    window.addEventListener('online', onOnline);
    window.addEventListener(STOCK_FLUSH_REQUEST_EVENT, onOnline);
    void flush();
    return () => {
      window.removeEventListener('online', onOnline);
      window.removeEventListener(STOCK_FLUSH_REQUEST_EVENT, onOnline);
    };
  }, [companyId, userId]);
}
