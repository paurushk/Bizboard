import { parseSerialNumbersText } from '@/components/billing/lineHelpers';
import { calculateLineTax, extractExclusiveFromInclusiveLine } from '@/utils/tax';

export type PosChipState = 'unsaved' | 'offline' | 'saved' | 'completed' | null;

/** Incoming serial text must match the qty being added (usually 1). */
export function serialsMatchAddQty(text: string, addQty: number): string[] | null {
  const serials = parseSerialNumbersText(text);
  if (serials.length !== addQty) return null;
  return serials;
}

export function isSerialOrBatchRuleError(message: string): boolean {
  const m = message.toLowerCase();
  return /\bserial\b/.test(m) || /\bbatch\b/.test(m) || /\blot\b/.test(m);
}

/** A-04: chip matches local cart vs queued outbox vs posted sale. */
export function posChipState(opts: {
  cartCount: number;
  hasOutbox: boolean;
  offline: boolean;
  justCompleted: boolean;
}): PosChipState {
  if (opts.justCompleted && opts.cartCount === 0) return 'completed';
  if (opts.hasOutbox) return opts.offline ? 'offline' : 'saved';
  if (opts.cartCount > 0) return opts.offline ? 'offline' : 'unsaved';
  return null;
}

export type RecoverUnpaid = { id: number; number: string };

export function unpaidRecoverFromAbort(pending: {
  invoiceId?: number;
  invoiceNumber?: string | null;
  [key: string]: unknown;
} | null): RecoverUnpaid | null {
  if (!pending?.invoiceId) return null;
  return { id: pending.invoiceId, number: pending.invoiceNumber || `#${pending.invoiceId}` };
}

/** CR-001: reuse the in-flight sale gesture key; never remint mid-settlement. */
export function resolveSaleGestureKey(
  existingKey: string | null | undefined,
  mint: () => string,
): string {
  return existingKey || mint();
}

export type PosCashSettlementPhase = 'create_complete' | 'receipt_alloc';

/** CR-001: after complete succeeds, retries must settle receipt+alloc only. */
export function posCashSettlementPhase(
  pending: { invoiceId?: number } | null | undefined,
): PosCashSettlementPhase {
  return pending?.invoiceId ? 'receipt_alloc' : 'create_complete';
}

export type CompleteFailureUiAction = {
  clearCart: boolean;
  clearKey: boolean;
  unpaidRecover: boolean;
  keepRetryable: boolean;
};

/**
 * CR-010: unknown complete status must keep cart + key (probe may still be DRAFT).
 * Confirmed COMPLETED is returned as success upstream; DRAFT is deleted+rethrown.
 */
export function completeFailureUiAction(
  existingStatus: string | null | undefined,
): CompleteFailureUiAction {
  if (existingStatus === 'COMPLETED') {
    return { clearCart: false, clearKey: false, unpaidRecover: false, keepRetryable: false };
  }
  if (existingStatus) {
    return { clearCart: false, clearKey: false, unpaidRecover: false, keepRetryable: true };
  }
  return { clearCart: false, clearKey: false, unpaidRecover: false, keepRetryable: true };
}

/**
 * CR-012: Enforce 3dp money discipline and sane max quantity (999,999).
 * Returns 0 if quantity is zero or negative (triggers line removal).
 */
export function clampPosQuantity(qty: number): number {
  if (!Number.isFinite(qty) || qty <= 0) return 0;
  const clamped = Math.min(999999, Math.max(0.001, qty));
  return Math.round(clamped * 1000) / 1000;
}

/**
 * CR-009: Shared helper for line tax calculation across table and tender panel,
 * properly extracting exclusive unit price when priceMode is INCLUSIVE.
 */
export function computePosLineTax(params: {
  quantity: number;
  unitPrice: number;
  gstRate: number;
  discountPercent?: number;
  isInclusive: boolean;
  intraState: boolean | null;
  cessRate?: number;
}) {
  let unitPrice = params.unitPrice;
  let discountPercent = params.discountPercent || 0;
  if (params.isInclusive) {
    const extracted = extractExclusiveFromInclusiveLine({
      quantity: params.quantity,
      unitPriceInclusive: unitPrice,
      discountPercent,
      gstRate: params.gstRate,
      cessRate: params.cessRate ?? 0,
    });
    unitPrice = extracted.exclusiveUnitPrice;
    discountPercent = 0;
  }
  return calculateLineTax({
    quantity: params.quantity,
    unitPrice,
    gstRate: params.gstRate,
    discountPercent,
    intraState: params.intraState,
    cessRate: params.cessRate ?? 0,
  });
}

/** CR-091: mid-settlement cash resume across reload. */
export type PosCashPendingSnapshot = {
  invoiceId: number;
  invoiceNumber: string;
  customer: number;
  amount: number;
  key?: string;
};

/** CR-109: scope mid-settlement snapshots to companyId:userId (not company-only). */
export function cashPendingStorageKey(companyId: number, userId: number): string {
  return `bizboard.pos.cashPending.${companyId}:${userId}`;
}

export function serializeCashPending(pending: PosCashPendingSnapshot): string {
  return JSON.stringify(pending);
}

export function parseCashPending(raw: string | null | undefined): PosCashPendingSnapshot | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    const invoiceId = Number(parsed.invoiceId);
    const customer = Number(parsed.customer);
    const amount = Number(parsed.amount);
    if (!Number.isFinite(invoiceId) || invoiceId <= 0) return null;
    if (!Number.isFinite(customer) || customer <= 0) return null;
    if (!Number.isFinite(amount)) return null;
    return {
      invoiceId,
      invoiceNumber: String(parsed.invoiceNumber ?? `#${invoiceId}`),
      customer,
      amount,
      key: typeof parsed.key === 'string' && parsed.key ? parsed.key : undefined,
    };
  } catch {
    return null;
  }
}

export function persistCashPending(
  companyId: number,
  userId: number,
  pending: PosCashPendingSnapshot,
): void {
  if (typeof sessionStorage === 'undefined' || !companyId || !userId) return;
  try {
    sessionStorage.setItem(cashPendingStorageKey(companyId, userId), serializeCashPending(pending));
  } catch {
    /* quota / private mode */
  }
}

export function restoreCashPending(
  companyId: number,
  userId: number,
): PosCashPendingSnapshot | null {
  if (typeof sessionStorage === 'undefined' || !companyId || !userId) return null;
  try {
    return parseCashPending(sessionStorage.getItem(cashPendingStorageKey(companyId, userId)));
  } catch {
    return null;
  }
}

export function clearCashPendingStorage(companyId: number, userId: number): void {
  if (typeof sessionStorage === 'undefined' || !companyId || !userId) return;
  try {
    sessionStorage.removeItem(cashPendingStorageKey(companyId, userId));
  } catch {
    /* ignore */
  }
}

/** CR-109: wipe all POS settlement keys for this company+user on logout. */
export function clearPosPendingStorageForUser(companyId: number, userId: number): void {
  clearCashPendingStorage(companyId, userId);
  clearUpiPendingStorage(companyId, userId);
  // Legacy company-only keys (pre-CR-109) — best-effort wipe on shared devices.
  if (typeof sessionStorage === 'undefined' || !companyId) return;
  try {
    sessionStorage.removeItem(`bizboard.pos.cashPending.${companyId}`);
    sessionStorage.removeItem(`bizboard.pos.upiPending.${companyId}`);
  } catch {
    /* ignore */
  }
}

/** CR-108: mid-settlement UPI resume across reload (twin of cashPending). */
export type PosUpiPendingSnapshot = {
  invoiceId?: number;
  invoiceNumber?: string;
  customer: number;
  amount: number;
  key?: string;
  upiQr: Record<string, string> | null;
  lines?: any[];
  confirmBlankPos?: boolean;
};

export function upiPendingStorageKey(companyId: number, userId: number): string {
  return `bizboard.pos.upiPending.${companyId}:${userId}`;
}

export function serializeUpiPending(pending: PosUpiPendingSnapshot): string {
  return JSON.stringify(pending);
}

export function parseUpiPending(raw: string | null | undefined): PosUpiPendingSnapshot | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    const invoiceId =
      parsed.invoiceId !== undefined && parsed.invoiceId !== null
        ? Number(parsed.invoiceId)
        : undefined;
    const customer = Number(parsed.customer);
    const amount = Number(parsed.amount);
    if (invoiceId !== undefined && (!Number.isFinite(invoiceId) || invoiceId <= 0)) return null;
    if (!Number.isFinite(customer) || customer <= 0) return null;
    if (!Number.isFinite(amount)) return null;
    const upiQr =
      parsed.upiQr && typeof parsed.upiQr === 'object'
        ? (parsed.upiQr as Record<string, string>)
        : null;
    return {
      ...(invoiceId !== undefined
        ? { invoiceId, invoiceNumber: String(parsed.invoiceNumber ?? `#${invoiceId}`) }
        : {}),
      customer,
      amount,
      key: typeof parsed.key === 'string' && parsed.key ? parsed.key : undefined,
      upiQr,
      lines: Array.isArray(parsed.lines) ? (parsed.lines as any[]) : undefined,
      confirmBlankPos:
        typeof parsed.confirmBlankPos === 'boolean' ? parsed.confirmBlankPos : undefined,
    };
  } catch {
    return null;
  }
}

export function persistUpiPending(
  companyId: number,
  userId: number,
  pending: PosUpiPendingSnapshot,
): void {
  if (typeof sessionStorage === 'undefined' || !companyId || !userId) return;
  try {
    sessionStorage.setItem(upiPendingStorageKey(companyId, userId), serializeUpiPending(pending));
  } catch {
    /* quota / private mode */
  }
}

export function restoreUpiPending(
  companyId: number,
  userId: number,
): PosUpiPendingSnapshot | null {
  if (typeof sessionStorage === 'undefined' || !companyId || !userId) return null;
  try {
    return parseUpiPending(sessionStorage.getItem(upiPendingStorageKey(companyId, userId)));
  } catch {
    return null;
  }
}

export function clearUpiPendingStorage(companyId: number, userId: number): void {
  if (typeof sessionStorage === 'undefined' || !companyId || !userId) return;
  try {
    sessionStorage.removeItem(upiPendingStorageKey(companyId, userId));
  } catch {
    /* ignore */
  }
}

