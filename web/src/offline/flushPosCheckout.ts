import {
  completeSalesInvoice,
  createAllocation,
  createCustomer,
  createReceipt,
  createSalesInvoice,
  deleteSalesInvoice,
  getCompany,
  getSalesInvoice,
} from '@/api/resources';
import { todayIso } from '@/components/billing';
import { preferredInvoiceType } from '@/onboarding/taxHints';
import { toNumber } from '@/utils/money';
import type { OutboxDraft } from '@/offline/invoiceDraftCache';

/** Flush a POS outbox draft: create+complete invoice, cash receipt, allocate. */
export async function flushPosDraft(draft: OutboxDraft): Promise<void> {
  const payload = draft.payload || {};
  const mode = draft.paymentMode ?? payload.paymentMode ?? 'CASH';
  if (mode === 'UPI') {
    throw new Error('UPI POS drafts must be finished on the POS screen while online.');
  }
  let customerId = Number(draft.customerId || payload.customer || 0);
  const pendingName = String(
    draft.pendingCustomerName || payload.pendingCustomerName || '',
  ).trim();
  if (!customerId && pendingName) {
    const created = await createCustomer({ name: pendingName, status: 'ACTIVE' });
    customerId = created.id;
  }
  if (!customerId) {
    throw new Error('POS draft is missing a customer');
  }
  const lines = draft.lines ?? [];
  if (!lines.length) {
    throw new Error('POS draft has no lines');
  }
  const company = await getCompany();
  const taxEnabled = preferredInvoiceType(company.registrationType) !== 'NON_GST';
  const posInvoiceType = taxEnabled ? 'RETAIL' : 'NON_GST';
  const isInclusive = company.priceMode === 'INCLUSIVE';
  const invoiceDate = todayIso();
  const invoice = await createSalesInvoice(
    {
      customer: customerId,
      invoiceType: posInvoiceType,
      priceMode: isInclusive ? 'INCLUSIVE' : 'EXCLUSIVE',
      invoiceDate,
      dueDate: invoiceDate,
      paymentTermsDays: 0,
      autoRoundOff: true,
      items: lines.map((line) => ({
        product: line.productId,
        description: line.productName,
        quantity: line.quantity,
        unitPrice: line.unitPrice,
        unitPriceInclusive: isInclusive ? line.unitPrice : undefined,
        gstRate: taxEnabled ? line.gstRate : 0,
        cessRate: taxEnabled ? (line.cessRate ?? 0) : 0,
        discountPercent: line.discountPercent ?? 0,
        discountAmount: line.discountAmount,
        serialNumbers: line.serials,
        supplyType: line.supplyType,
        unitName: line.unitName || undefined,
      })),
    },
    { idempotencyKey: draft.idempotencyKey },
  );
  let completed;
  try {
    // F1-001: carry the same idempotency key `complete` sees on every retry
    // of this draft. The backend's `sales_invoice_complete` scope is
    // idempotent (core/idempotency.py) — a retry with this key replays the
    // stored response from a completion that already happened server-side
    // instead of re-running SalesService.complete() against an
    // already-COMPLETED invoice.
    completed = await completeSalesInvoice(invoice.id, {
      confirmBlankPos: true,
      idempotencyKey: `${draft.idempotencyKey}-complete`,
    });
  } catch (err) {
    // F1-001: belt-and-suspenders for the case an idempotency record can't
    // be found (key mismatch, record cleared) but the invoice genuinely
    // did complete server-side before this process died — e.g. the create
    // above returned the pre-existing invoice from *its* idempotency
    // replay, so completeSalesInvoice's own key was never actually used
    // for a first attempt. Fetch and check status before assuming failure;
    // only delete (and only the still-DRAFT invoice this flush created)
    // when it genuinely never completed.
    let existing;
    try {
      existing = await getSalesInvoice(invoice.id);
    } catch {
      /* probe failed too — handled below, fall through without deleting */
    }
    if (existing?.status === 'COMPLETED') {
      completed = existing;
    } else if (existing) {
      // Confirmed still DRAFT — genuinely failed, safe to clean up.
      try {
        await deleteSalesInvoice(invoice.id);
      } catch {
        /* leftover draft if delete is blocked */
      }
      throw err;
    } else {
      // Status truly unknown (the probe itself failed, e.g. still
      // offline) — don't guess. Leave the invoice alone and rethrow so
      // this draft stays queued as failed and gets retried (idempotently)
      // on the next flush pass, instead of risking a delete of a real sale.
      throw err;
    }
  }
  const invoiceTotal = toNumber(completed.grandTotal);
  const receipt = await createReceipt(
    {
      customer: customerId,
      amount: invoiceTotal,
      mode: 'CASH',
      receiptDate: invoiceDate,
      notes: `POS — ${completed.number ?? completed.id}`,
    },
    { idempotencyKey: `${draft.idempotencyKey}-receipt` },
  );
  await createAllocation(
    {
      receipt: receipt.id,
      salesInvoice: completed.id,
      amount: invoiceTotal,
    },
    { idempotencyKey: `${draft.idempotencyKey}-alloc` },
  );
}
