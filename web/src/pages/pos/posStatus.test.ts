import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  cashPendingStorageKey,
  clampPosQuantity,
  clearCashPendingStorage,
  clearPosPendingStorageForUser,
  clearUpiPendingStorage,
  completeFailureUiAction,
  computePosLineTax,
  isSerialOrBatchRuleError,
  parseCashPending,
  parseUpiPending,
  persistCashPending,
  persistUpiPending,
  posCashSettlementPhase,
  posChipState,
  resolveSaleGestureKey,
  restoreCashPending,
  restoreUpiPending,
  serializeCashPending,
  serializeUpiPending,
  serialsMatchAddQty,
  unpaidRecoverFromAbort,
  upiPendingStorageKey,
} from './posStatus';

describe('posChipState (A-04)', () => {
  it('is Unsaved when the cart is local-only and online', () => {
    expect(posChipState({ cartCount: 2, hasOutbox: false, offline: false, justCompleted: false })).toBe(
      'unsaved',
    );
  });

  it('is Offline queued when the outbox has items or the cart is held offline', () => {
    expect(posChipState({ cartCount: 1, hasOutbox: true, offline: true, justCompleted: false })).toBe(
      'offline',
    );
    expect(posChipState({ cartCount: 1, hasOutbox: false, offline: true, justCompleted: false })).toBe(
      'offline',
    );
  });

  it('is Saved draft when queued drafts exist and the device is online', () => {
    expect(posChipState({ cartCount: 0, hasOutbox: true, offline: false, justCompleted: false })).toBe(
      'saved',
    );
  });

  it('is Completed after a posted sale with an empty cart', () => {
    expect(posChipState({ cartCount: 0, hasOutbox: false, offline: false, justCompleted: true })).toBe(
      'completed',
    );
  });
});

describe('serialsMatchAddQty (R-009)', () => {
  it('accepts serial text whose count matches qty', () => {
    expect(serialsMatchAddQty('SN-1', 1)).toEqual(['SN-1']);
    expect(serialsMatchAddQty('SN-1, SN-2', 2)).toEqual(['SN-1', 'SN-2']);
  });

  it('refuses a blank or short serial list', () => {
    expect(serialsMatchAddQty('', 1)).toBeNull();
    expect(serialsMatchAddQty('SN-1', 2)).toBeNull();
  });
});

describe('isSerialOrBatchRuleError (R-067)', () => {
  it('matches serial and batch business-rule messages', () => {
    expect(isSerialOrBatchRuleError('Exactly 2 serial number(s) are required')).toBe(true);
    expect(isSerialOrBatchRuleError("A batch is required for tracked product 'X'.")).toBe(true);
    expect(isSerialOrBatchRuleError('Insufficient stock')).toBe(false);
  });
});

describe('unpaidRecoverFromAbort (A-04)', () => {
  it('returns a recover CTA target when an unpaid invoice id is present', () => {
    expect(
      unpaidRecoverFromAbort({ invoiceId: 44, invoiceNumber: 'POS-12' }),
    ).toEqual({ id: 44, number: 'POS-12' });
  });

  it('is null when UPI never created an invoice', () => {
    expect(unpaidRecoverFromAbort(null)).toBeNull();
  });
});

describe('POS durable resume (CR-001 / CR-010)', () => {
  it('pos_online_cash_retry_after_receipt_failure_does_not_double_complete', () => {
    const mint = vi.fn(() => 'fresh-key');
    expect(resolveSaleGestureKey('sale-key-1', mint)).toBe('sale-key-1');
    expect(mint).not.toHaveBeenCalled();
    expect(resolveSaleGestureKey(null, mint)).toBe('fresh-key');
    expect(mint).toHaveBeenCalledTimes(1);

    expect(posCashSettlementPhase(null)).toBe('create_complete');
    expect(posCashSettlementPhase({ invoiceId: 501 })).toBe('receipt_alloc');
  });

  it('createCompletedInvoice_unknown_status_keeps_cart_and_key', () => {
    expect(completeFailureUiAction(null)).toEqual({
      clearCart: false,
      clearKey: false,
      unpaidRecover: false,
      keepRetryable: true,
    });
    expect(completeFailureUiAction('DRAFT')).toEqual({
      clearCart: false,
      clearKey: false,
      unpaidRecover: false,
      keepRetryable: true,
    });
    expect(completeFailureUiAction('COMPLETED').clearCart).toBe(false);
  });
});

describe('POS line totals & qty discipline (CR-009 / CR-012)', () => {
  it('pos_inclusive_line_row_matches_tender_total (CR-009)', () => {
    // 1 item @ ₹118 inclusive with 18% GST intra-state
    const result = computePosLineTax({
      quantity: 1,
      unitPrice: 118,
      gstRate: 18,
      discountPercent: 0,
      isInclusive: true,
      intraState: true,
    });
    // Exclusive unit price should be 100, taxable 100, CGST 9, SGST 9, lineTotal 118
    expect(result.taxableAmount).toBe(100);
    expect(result.cgst).toBe(9);
    expect(result.sgst).toBe(9);
    expect(result.lineTotal).toBe(118);
  });

  it('pos_rejects_qty_below_0_001_and_caps_absurd_qty (CR-012)', () => {
    expect(clampPosQuantity(0)).toBe(0);
    expect(clampPosQuantity(-5)).toBe(0);
    expect(clampPosQuantity(0.0001)).toBe(0.001);
    expect(clampPosQuantity(1.23456)).toBe(1.235);
    expect(clampPosQuantity(10)).toBe(10);
    expect(clampPosQuantity(999999999)).toBe(999999);
  });
});

describe('POS cashPending session restore (CR-091)', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it('serialize_restore_round_trips_and_clears', () => {
    const pending = {
      invoiceId: 88,
      invoiceNumber: 'POS-88',
      customer: 12,
      amount: 118.5,
      key: 'sale-key-88',
    };
    expect(cashPendingStorageKey(7, 3)).toBe('bizboard.pos.cashPending.7:3');
    expect(parseCashPending(serializeCashPending(pending))).toEqual(pending);

    persistCashPending(7, 3, pending);
    expect(restoreCashPending(7, 3)).toEqual(pending);
    expect(restoreCashPending(7, 9)).toBeNull();
    expect(restoreCashPending(0, 3)).toBeNull();
    expect(parseCashPending('not-json')).toBeNull();
    expect(parseCashPending('{"invoiceId":"x"}')).toBeNull();

    clearCashPendingStorage(7, 3);
    expect(restoreCashPending(7, 3)).toBeNull();
  });

  it('pos_logout_clears_cash_pending_storage', () => {
    const pending = {
      invoiceId: 1,
      invoiceNumber: 'POS-1',
      customer: 2,
      amount: 10,
      key: 'k',
    };
    persistCashPending(7, 3, pending);
    clearPosPendingStorageForUser(7, 3);
    expect(restoreCashPending(7, 3)).toBeNull();
  });
});

describe('POS upiPending session restore (CR-108)', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it('pos_upi_reload_mid_settlement_resumes_confirm', () => {
    const pending = {
      invoiceId: 91,
      invoiceNumber: 'POS-91',
      customer: 3,
      amount: 250,
      key: 'upi-key-91',
      upiQr: { intentUrl: 'upi://pay?pa=x', qrPngBase64: 'abc' },
    };
    expect(upiPendingStorageKey(7, 3)).toBe('bizboard.pos.upiPending.7:3');
    expect(parseUpiPending(serializeUpiPending(pending))).toEqual(pending);
    persistUpiPending(7, 3, pending);
    clearUpiPendingStorage(7, 3);
    expect(restoreUpiPending(7, 3)).toBeNull();
  });

  it('pos_upi_without_invoice_persists_and_aborts_cleanly', () => {
    const pending = {
      customer: 5,
      amount: 450,
      key: 'upi-draft-key',
      upiQr: { intentUrl: 'upi://pay?pa=y', qrPngBase64: 'def' },
      lines: [
        { productId: 1, productName: 'Widget', sku: 'WID-1', quantity: 2, unitPrice: 225, gstRate: 18 },
      ],
    };
    expect(parseUpiPending(serializeUpiPending(pending))).toEqual(pending);
    expect(unpaidRecoverFromAbort(pending)).toBeNull();
    persistUpiPending(7, 3, pending);
    expect(restoreUpiPending(7, 3)).toEqual(pending);
    clearUpiPendingStorage(7, 3);
    expect(restoreUpiPending(7, 3)).toBeNull();
  });
});

describe('POS cess line tax (CR-110)', () => {
  it('pos_cess_line_total_matches_preview', () => {
    const result = computePosLineTax({
      quantity: 1,
      unitPrice: 100,
      gstRate: 18,
      discountPercent: 0,
      isInclusive: false,
      intraState: true,
      cessRate: 12,
    });
    expect(result.taxableAmount).toBe(100);
    expect(result.cgst).toBe(9);
    expect(result.sgst).toBe(9);
    expect(result.cess).toBe(12);
    expect(result.lineTotal).toBe(130);
  });
});

