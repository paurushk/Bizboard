import { useEffect } from 'react';
import {
  createSalesInvoice,
  updateSalesInvoice,
} from '@/api/resources';
import { flushOutbox, listDrafts } from '@/offline/invoiceDraftCache';
import { t } from '@/i18n';

/**
 * BB-000751: flush offline invoice drafts when online.
 * Returns nothing — caller owns outboxBanner state.
 */
export function useInvoiceOffline(
  companyId: number,
  userId: number,
  setOutboxBanner: (msg: string | null) => void,
): void {
  useEffect(() => {
    if (!companyId || !userId) return;
    const flush = async () => {
      const pending = (await listDrafts(companyId, userId)).filter((d) => d.kind === 'invoice');
      if (pending.length) setOutboxBanner(t('billing.offlineOutboxPending'));
      const result = await flushOutbox(
        companyId,
        userId,
        async (draft) => {
          if (draft.invoiceId) {
            await updateSalesInvoice(draft.invoiceId, draft.payload as never);
          } else {
            await createSalesInvoice(draft.payload as never, { idempotencyKey: draft.idempotencyKey });
          }
        },
        (draft) => draft.kind === 'invoice',
      );
      if (result.failed > 0) {
        setOutboxBanner(
          `Offline sync failed (${result.failed}): ${result.errors.slice(0, 3).join(' · ')}`,
        );
        return;
      }
      const left = (await listDrafts(companyId, userId)).filter((d) => d.kind === 'invoice');
      setOutboxBanner(left.length ? t('billing.offlineOutboxPending') : null);
    };
    const onOnline = () => void flush();
    window.addEventListener('online', onOnline);
    void flush();
    return () => window.removeEventListener('online', onOnline);
  }, [companyId, userId, setOutboxBanner]);
}
