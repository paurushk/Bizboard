import { useEffect } from 'react';
import {
  completeSalesInvoice,
  createSalesInvoice,
  updateSalesInvoice,
} from '@/api/resources';
import { t } from '@/i18n';
import { flushOutbox, listDrafts, type OutboxDraft } from '@/offline/invoiceDraftCache';
import { toNumber } from '@/utils/money';
import type { PaymentMode, SalesInvoice } from '@/types/domain';

function takeInvoiceMeta(raw: Record<string, unknown>, draft: OutboxDraft) {
  const completeIntent = Boolean(draft.completeIntent) || Boolean(raw._completeIntent);
  const confirmSalesRcm = Boolean(raw._confirmSalesRcm || raw.confirmSalesRcm);
  const confirmBlankPos = Boolean(raw._confirmBlankPos || raw.confirmBlankPos);
  const confirmGstinTotalChange = Boolean(raw._confirmGstinTotalChange || raw.confirmGstinTotalChange);
  const confirmAmend = Boolean(raw.confirmAmend);
  const amountReceived = toNumber(
    typeof raw._amountReceived === 'number' || typeof raw._amountReceived === 'string'
      ? raw._amountReceived
      : typeof raw.amountReceived === 'number' || typeof raw.amountReceived === 'string'
        ? raw.amountReceived
        : 0,
  );
  const paymentMode = String(raw._paymentMode ?? raw.paymentMode ?? draft.paymentMode ?? 'CASH') as PaymentMode;
  const chequeNumber = String(raw._chequeNumber ?? raw.chequeNumber ?? '');
  const chequeBankName = String(raw._chequeBankName ?? raw.chequeBankName ?? '');
  const chequeDate = String(raw._chequeDate ?? raw.chequeDate ?? '');
  const chequeImageRaw = raw._chequeImage ?? raw.chequeImage;
  const chequeImage = typeof chequeImageRaw === 'number' ? chequeImageRaw : null;
  const customerId = Number(raw._customerId ?? raw.customerId ?? draft.customerId ?? raw.customer ?? 0);
  const invoiceDate = String(raw.invoiceDate ?? '');
  const status = String(raw.status ?? '').toUpperCase();
  const payload = { ...raw };
  delete payload._completeIntent;
  delete payload._confirmSalesRcm;
  delete payload._confirmBlankPos;
  delete payload._confirmGstinTotalChange;
  delete payload._amountReceived;
  delete payload.amountReceived;
  delete payload._paymentMode;
  delete payload.paymentMode;
  delete payload._chequeNumber;
  delete payload._chequeBankName;
  delete payload._chequeDate;
  delete payload._chequeImage;
  delete payload._customerId;
  delete payload.customerId;
  delete payload.status;
  return {
    payload,
    completeIntent,
    confirmSalesRcm,
    confirmBlankPos,
    confirmGstinTotalChange,
    confirmAmend,
    amountReceived,
    paymentMode,
    chequeNumber,
    chequeBankName,
    chequeDate,
    chequeImage,
    customerId,
    invoiceDate,
    status,
  };
}

/** Flush one queued invoice draft — shared with OfflineOutboxPage. */
export async function flushInvoiceDraft(draft: OutboxDraft): Promise<void> {
  const meta = takeInvoiceMeta({ ...(draft.payload as Record<string, unknown>) }, draft);
  let invoice: SalesInvoice;
  if (draft.invoiceId) {
    if (meta.status === 'COMPLETED') {
      if (!meta.confirmAmend && !meta.completeIntent) {
        throw new Error(t('billing.offlineAmendRequiresConfirm'));
      }
      invoice = await updateSalesInvoice(draft.invoiceId, {
        ...meta.payload,
        confirmAmend: true,
        expectedAmendRevision:
          (meta.payload as { expectedAmendRevision?: number }).expectedAmendRevision ?? 0,
      } as never);
    } else {
      invoice = await updateSalesInvoice(draft.invoiceId, meta.payload as never);
    }
  } else {
    invoice = await createSalesInvoice(meta.payload as never, {
      idempotencyKey: draft.idempotencyKey,
    });
  }
  if (meta.completeIntent && invoice.status === 'DRAFT') {
    const collects = meta.amountReceived > 0 && meta.paymentMode !== 'CREDIT';
    invoice = await completeSalesInvoice(invoice.id, {
      confirmSalesRcm: meta.confirmSalesRcm,
      confirmBlankPos: meta.confirmBlankPos,
      confirmGstinTotalChange: meta.confirmGstinTotalChange,
      idempotencyKey: draft.idempotencyKey,
      ...(collects
        ? {
            amountReceived: meta.amountReceived,
            paymentMode: meta.paymentMode,
            ...(meta.paymentMode === 'CHEQUE'
              ? {
                  chequeNumber: meta.chequeNumber,
                  chequeBankName: meta.chequeBankName,
                  chequeDate: meta.chequeDate || undefined,
                  chequeImage: meta.chequeImage,
                }
              : {}),
          }
        : {}),
    });
  }
}

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
          await flushInvoiceDraft(draft);
        },
        (draft) => draft.kind === 'invoice',
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
      const left = (await listDrafts(companyId, userId)).filter((d) => d.kind === 'invoice');
      setOutboxBanner(left.length ? t('billing.offlineOutboxPending') : null);
    };
    const onOnline = () => void flush();
    window.addEventListener('online', onOnline);
    void flush();
    return () => window.removeEventListener('online', onOnline);
  }, [companyId, userId, setOutboxBanner]);
}
