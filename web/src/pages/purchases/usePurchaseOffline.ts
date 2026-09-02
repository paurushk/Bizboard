import { useEffect } from 'react';
import {
  completePurchase,
  createAllocation,
  createPurchase,
  createSupplierPayment,
  updatePurchase,
} from '@/api/resources';
import { t } from '@/i18n';
import { flushOutbox, isFlushableDraft, listDrafts, type OutboxDraft } from '@/offline/invoiceDraftCache';
import { toNumber } from '@/utils/money';
import type { PaymentMode, PurchaseInvoice } from '@/types/domain';

function takePurchaseMeta(raw: Record<string, unknown>, draft: OutboxDraft) {
  const completeIntent = Boolean(draft.completeIntent) || Boolean(raw._completeIntent);
  const confirmBlankPos = Boolean(raw._confirmBlankPos || raw.confirmBlankPos);
  const confirmGstinTotalChange = Boolean(raw._confirmGstinTotalChange || raw.confirmGstinTotalChange);
  const confirmAmend = Boolean(raw.confirmAmend);
  const amountPaid = toNumber(
    typeof raw._amountPaid === 'number' || typeof raw._amountPaid === 'string'
      ? raw._amountPaid
      : typeof raw.amountPaid === 'number' || typeof raw.amountPaid === 'string'
        ? raw.amountPaid
        : 0,
  );
  const paymentMode = String(raw._paymentMode ?? raw.paymentMode ?? draft.paymentMode ?? 'CASH') as PaymentMode;
  const supplierId = Number(raw._supplierId ?? raw.supplierId ?? raw.supplier ?? 0);
  const invoiceDate = String(raw.invoiceDate ?? '');
  const status = String(raw.status ?? '').toUpperCase();
  const payload = { ...raw };
  delete payload._completeIntent;
  delete payload._confirmBlankPos;
  delete payload._confirmGstinTotalChange;
  delete payload._amountPaid;
  delete payload.amountPaid;
  delete payload._paymentMode;
  delete payload.paymentMode;
  delete payload._supplierId;
  delete payload.supplierId;
  delete payload.status;
  return {
    payload,
    completeIntent,
    confirmBlankPos,
    confirmGstinTotalChange,
    confirmAmend,
    amountPaid,
    paymentMode,
    supplierId,
    invoiceDate,
    status,
  };
}

async function allocatePurchasePayment(
  invoice: PurchaseInvoice,
  opts: {
    amountPaid: number;
    paymentMode: PaymentMode;
    supplierId: number;
    invoiceDate: string;
    idempotencyKey?: string;
  },
): Promise<void> {
  if (!(opts.amountPaid > 0) || invoice.status !== 'COMPLETED' || !opts.supplierId) return;
  const already = toNumber(invoice.paid);
  const toAllocate = Math.max(0, opts.amountPaid - already);
  if (toAllocate <= 0) return;
  const keyBase = opts.idempotencyKey || invoice.number || String(invoice.id);
  const payment = await createSupplierPayment(
    {
      supplier: opts.supplierId,
      amount: toAllocate,
      mode: opts.paymentMode,
      paymentDate: opts.invoiceDate || undefined,
      notes: `Against ${invoice.number ?? invoice.id}`,
    },
    { idempotencyKey: `purchase-pay-${keyBase}` },
  );
  await createAllocation(
    {
      supplierPayment: payment.id,
      purchaseInvoice: invoice.id,
      amount: toAllocate,
    },
    { idempotencyKey: `purchase-alloc-${keyBase}` },
  );
}

/** Flush one queued purchase draft — shared with OfflineOutboxPage. */
export async function flushPurchaseDraft(draft: OutboxDraft): Promise<void> {
  const meta = takePurchaseMeta({ ...(draft.payload as Record<string, unknown>) }, draft);
  let invoice: PurchaseInvoice;
  if (draft.invoiceId) {
    if (meta.status === 'COMPLETED') {
      if (!meta.confirmAmend && !meta.completeIntent) {
        throw new Error(t('billing.offlineAmendRequiresConfirm'));
      }
      invoice = await updatePurchase(draft.invoiceId, {
        ...meta.payload,
        confirmAmend: true,
      } as never);
    } else {
      invoice = await updatePurchase(draft.invoiceId, meta.payload as never);
    }
  } else {
    invoice = await createPurchase(meta.payload as never, { idempotencyKey: draft.idempotencyKey });
  }
  if (meta.completeIntent && invoice.status === 'DRAFT') {
    invoice = await completePurchase(invoice.id, {
      confirmBlankPos: meta.confirmBlankPos,
      confirmGstinTotalChange: meta.confirmGstinTotalChange,
    });
  }
  await allocatePurchasePayment(invoice, { ...meta, idempotencyKey: draft.idempotencyKey });
}

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
          await flushPurchaseDraft(draft);
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
