import { useEffect } from 'react';
import {
  completeSalesInvoice,
  createSalesInvoice,
  updateSalesInvoice,
} from '@/api/resources';
import { flushOutbox, listDrafts } from '@/offline/invoiceDraftCache';
import { t } from '@/i18n';

/**
 * BB-000751: flush offline invoice drafts when online.
 * Honors completeIntent the same way the Outbox page does.
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
          const payload = { ...(draft.payload as Record<string, unknown>) };
          const completeIntent =
            Boolean(draft.completeIntent) || Boolean(payload._completeIntent);
          const confirmSalesRcm = Boolean(payload._confirmSalesRcm || payload.confirmSalesRcm);
          const confirmBlankPos = Boolean(payload._confirmBlankPos || payload.confirmBlankPos);
          const confirmGstinTotalChange = Boolean(
            payload._confirmGstinTotalChange || payload.confirmGstinTotalChange,
          );
          delete payload._completeIntent;
          delete payload._confirmSalesRcm;
          delete payload._confirmBlankPos;
          delete payload._confirmGstinTotalChange;
          delete payload.status;
          if (draft.invoiceId) {
            const status = String((draft.payload as Record<string, unknown>).status ?? '').toUpperCase();
            if (status === 'COMPLETED') {
              throw new Error(t('billing.offlineAmendRequiresConfirm'));
            }
            const invoice = await updateSalesInvoice(draft.invoiceId, payload as never);
            if (completeIntent && invoice.status === 'DRAFT') {
              await completeSalesInvoice(invoice.id, {
                confirmSalesRcm,
                confirmBlankPos,
                confirmGstinTotalChange,
              });
            }
            return;
          }
          const invoice = await createSalesInvoice(payload as never, {
            idempotencyKey: draft.idempotencyKey,
          });
          if (completeIntent && invoice.status === 'DRAFT') {
            await completeSalesInvoice(invoice.id, {
              confirmSalesRcm,
              confirmBlankPos,
              confirmGstinTotalChange,
            });
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
