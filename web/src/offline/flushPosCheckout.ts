import {
  createCustomer,
  ensurePosWalkIn,
  getCompany,
  posCheckout,
} from '@/api/resources';
import { buildAtomicPosInvoicePayload } from '@/pages/pos/posCheckoutPayload';
import { todayIso } from '@/components/billing';
import { preferredInvoiceType } from '@/onboarding/taxHints';
import {
  updateDraft,
  type OutboxDraft,
} from '@/offline/invoiceDraftCache';
import type { SalesInvoice } from '@/types/domain';

/** Flush a POS outbox draft through the same atomic checkout the counter uses.
 * Cash is the default. Named credit flushes only when the draft was accepted as offline credit.
 * Card, UPI, bank, and cheque stay on the device until the cashier finishes them online.
 */
export async function flushPosDraft(draft: OutboxDraft): Promise<SalesInvoice> {
  const payload = draft.payload || {};
  const mode = draft.paymentMode ?? payload.paymentMode ?? 'CASH';
  const offlineCredit = Boolean(payload.offlineCredit);
  if (mode !== 'CASH' && !(mode === 'CREDIT' && offlineCredit)) {
    throw new Error(
      `Offline ${mode} sales cannot be synced. Take cash, or finish this tender while online. The sale was not posted as cash.`,
    );
  }
  let customerId = Number(draft.customerId || payload.customer || 0);
  const pendingName = String(
    draft.pendingCustomerName || payload.pendingCustomerName || '',
  ).trim();
  if (!customerId && pendingName) {
    // One customer per draft. Sharing one id between drafts that merely typed the same name would
    // merge different people into one ledger and credit-limit balance.
    const created = await createCustomer({ name: pendingName, status: 'ACTIVE' });
    customerId = created.id;
    await updateDraft(draft.companyId, draft.userId, draft.idempotencyKey, {
      customerId,
      payload: { ...payload, customer: customerId },
    });
  }
  if (!customerId) {
    const walkIn = await ensurePosWalkIn();
    customerId = walkIn.id;
    await updateDraft(draft.companyId, draft.userId, draft.idempotencyKey, {
      customerId,
      payload: { ...payload, customer: customerId },
    });
  }
  const lines = draft.lines ?? [];
  if (!lines.length) {
    throw new Error('POS draft has no lines');
  }
  const company = await getCompany();
  const taxEnabled = preferredInvoiceType(company.registrationType) !== 'NON_GST';
  const posInvoiceType = taxEnabled ? 'RETAIL' : 'NON_GST';
  const isInclusive = company.priceMode === 'INCLUSIVE';
  // The request is sent under draft.idempotencyKey on every retry. Pin the date so a retry after
  // midnight replays the same body instead of being refused as a reused key.
  let invoiceDate = typeof payload.invoiceDate === 'string' ? payload.invoiceDate : '';
  if (!invoiceDate) {
    invoiceDate = todayIso();
    await updateDraft(draft.companyId, draft.userId, draft.idempotencyKey, {
      payload: { ...payload, invoiceDate },
    });
  }
  const warehouse = Number(payload.warehouse || 0) || undefined;
  const body = {
    idempotency_key: draft.idempotencyKey,
    confirm_blank_pos: true,
    invoice: buildAtomicPosInvoicePayload({
      customer: customerId,
      invoiceType: posInvoiceType,
      priceModeInclusive: isInclusive,
      invoiceDate,
      warehouseId: warehouse,
      taxEnabled,
      lines,
      invoiceDiscountMode: 'AFTER_TAX' as const,
    }),
    offline_credit: mode === 'CREDIT',
    offline: true,
    shift_id: typeof payload.shiftId === 'number' ? payload.shiftId : undefined,
    credit_cached_at: typeof payload.creditCachedAt === 'string' ? payload.creditCachedAt : undefined,
    terminal_id: typeof payload.terminalId === 'string' ? payload.terminalId : undefined,
    outage_id: typeof payload.outageId === 'string' ? payload.outageId : undefined,
    payment: { mode },
  };
  const result = await posCheckout(body, { idempotencyKey: draft.idempotencyKey });
  const completed = result.invoice;
  if (!completed?.id) {
    throw new Error('POS checkout did not return an invoice');
  }
  return completed;
}

export async function flushPosBatch(drafts: OutboxDraft[]): Promise<{
  invoices: SalesInvoice[];
  errors: Array<{ index: number; detail: string }>;
}> {
  const { apiClient, unwrapData } = await import('@/api/client');
  const company = await getCompany();
  const taxEnabled = preferredInvoiceType(company.registrationType) !== 'NON_GST';
  const checkouts = [];
  for (const draft of drafts.slice(0, 50)) {
    const payload = draft.payload || {};
    const mode = draft.paymentMode ?? payload.paymentMode ?? 'CASH';
    checkouts.push({
      idempotency_key: draft.idempotencyKey,
      confirm_blank_pos: true,
      offline: true,
      offline_credit: mode === 'CREDIT' && Boolean(payload.offlineCredit),
      shift_id: payload.shiftId,
      terminal_id: payload.terminalId,
      credit_cached_at: payload.creditCachedAt,
      outage_id: payload.outageId,
      invoice: buildAtomicPosInvoicePayload({
        customer: Number(draft.customerId || payload.customer || 0),
        invoiceType: taxEnabled ? 'RETAIL' : 'NON_GST',
        priceModeInclusive: company.priceMode === 'INCLUSIVE',
        invoiceDate: typeof payload.invoiceDate === 'string' ? payload.invoiceDate : todayIso(),
        warehouseId: Number(payload.warehouse || 0) || undefined,
        taxEnabled,
        lines: draft.lines ?? [],
        invoiceDiscountMode: 'AFTER_TAX',
      }),
      payment: { mode },
    });
  }
  const response: { data: unknown } = await apiClient.post('/sales/pos/batch-sync/', { checkouts });
  const body = unwrapData<{
    results?: Array<{ invoice?: SalesInvoice }>;
    errors?: Array<{ index?: number; detail?: string }>;
  }>(response.data);
  return {
    invoices: (body.results ?? []).map((row) => row.invoice).filter((row): row is SalesInvoice => Boolean(row?.id)),
    errors: (body.errors ?? []).map((row) => ({ index: Number(row.index ?? -1), detail: String(row.detail || '') })),
  };
}
