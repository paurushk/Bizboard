import { useEffect } from 'react';
import {
  completeSalesInvoice,
  createAllocation,
  createReceipt,
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
    customerId,
    invoiceDate,
    status,
  };
}

async function allocateInvoicePayment(
  invoice: SalesInvoice,
  opts: {
    amountReceived: number;
    paymentMode: PaymentMode;
    customerId: number;
    invoiceDate: string;
    idempotencyKey?: string;
  },
): Promise<void> {
  if (!(opts.amountReceived > 0) || invoice.status !== 'COMPLETED' || !opts.customerId) return;
  const already = toNumber(invoice.received);
  const toAllocate = Math.max(0, opts.amountReceived - already);
  if (toAllocate <= 0) return;
  const keyBase = opts.idempotencyKey || '';
  const receipt = await createReceipt(
    {
      customer: opts.customerId,
      amount: toAllocate,
      mode: opts.paymentMode,
      receiptDate: opts.invoiceDate || undefined,
      notes: `Against ${invoice.number ?? invoice.id}`,
    },
    keyBase ? { idempotencyKey: `${keyBase}-receipt` } : undefined,
  );
  await createAllocation(
    {
      receipt: receipt.id,
      salesInvoice: invoice.id,
      amount: toAllocate,
    },
    keyBase ? { idempotencyKey: `${keyBase}-alloc` } : undefined,
  );
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
    invoice = await completeSalesInvoice(invoice.id, {
      confirmSalesRcm: meta.confirmSalesRcm,
      confirmBlankPos: meta.confirmBlankPos,
      confirmGstinTotalChange: meta.confirmGstinTotalChange,
    });
  }
  await allocateInvoicePayment(invoice, { ...meta, idempotencyKey: draft.idempotencyKey });
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
