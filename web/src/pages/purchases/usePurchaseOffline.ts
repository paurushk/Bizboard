import { useEffect } from 'react';
import { completePurchase, createPurchase, updatePurchase } from '@/api/resources';
import { flushOutbox, isFlushableDraft, listDrafts } from '@/offline/invoiceDraftCache';
import { t } from '@/i18n';

/** Flush queued purchase bills (not local autosave) when the browser is online. */
export function usePurchaseOffline(
  companyId: number,
  userId: number,
  setOutboxBanner: (msg: string | null) => void,
): void {
  useEffect(() => {
    if (!companyId || !userId) return;
    const flush = async () => {
      const pending = (await listDrafts(companyId, userId)).filter(
        (d) => d.kind === 'purchase' && isFlushableDraft(d),
      );
      if (pending.length) setOutboxBanner(t('billing.offlineOutboxPending'));
      const result = await flushOutbox(
        companyId,
        userId,
        async (draft) => {
          const payload = { ...(draft.payload as Record<string, unknown>) };
          const completeIntent =
            Boolean(draft.completeIntent) || Boolean(payload._completeIntent);
          const confirmBlankPos = Boolean(payload._confirmBlankPos || payload.confirmBlankPos);
          const confirmGstinTotalChange = Boolean(
            payload._confirmGstinTotalChange || payload.confirmGstinTotalChange,
          );
          delete payload._completeIntent;
          delete payload._confirmBlankPos;
          delete payload._confirmGstinTotalChange;
          delete payload.status;
          let invoice;
          if (draft.invoiceId) {
            const status = String((draft.payload as Record<string, unknown>).status ?? '').toUpperCase();
            if (status === 'COMPLETED') {
              throw new Error(t('billing.offlineAmendRequiresConfirm'));
            }
            invoice = await updatePurchase(draft.invoiceId, payload as never);
          } else {
            invoice = await createPurchase(payload as never, { idempotencyKey: draft.idempotencyKey });
          }
          if (completeIntent && invoice.status === 'DRAFT') {
            await completePurchase(invoice.id, { confirmBlankPos, confirmGstinTotalChange });
          }
        },
        (draft) => draft.kind === 'purchase' && isFlushableDraft(draft),
      );
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
        (d) => d.kind === 'purchase' && isFlushableDraft(d),
      );
      setOutboxBanner(left.length ? t('billing.offlineOutboxPending') : null);
    };
    const onOnline = () => void flush();
    window.addEventListener('online', onOnline);
    void flush();
    return () => window.removeEventListener('online', onOnline);
  }, [companyId, userId, setOutboxBanner]);
}
