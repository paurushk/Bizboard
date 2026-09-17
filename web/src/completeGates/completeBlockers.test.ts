import { describe, expect, it } from 'vitest';
import {
  firstCompleteDisabledReason,
  posPayDisabledReason,
  previewAllowsComplete,
  returnCompleteDisabledReason,
  serialCountMatchesQty,
} from './completeBlockers';
import { clientPreviewTotals } from '@/api/legacy/sales';

describe('firstCompleteDisabledReason', () => {
  it('CG-02 / CG-20: company GSTIN required beats party+line', () => {
    expect(
      firstCompleteDisabledReason({ canSave: true, gstinRequired: true, posKnown: true }),
    ).toMatch(/GSTIN/i);
  });

  it('CG-01 / CG-15: unknown place of supply names the party role', () => {
    expect(
      firstCompleteDisabledReason({ canSave: true, posKnown: false, partyRole: 'customer' }),
    ).toMatch(/customer state or GSTIN/i);
    expect(
      firstCompleteDisabledReason({ canSave: true, posKnown: false, partyRole: 'supplier' }),
    ).toMatch(/supplier state or GSTIN/i);
  });

  it('CG-16: missing purchase batch names the item', () => {
    expect(
      firstCompleteDisabledReason({
        canSave: true,
        posKnown: true,
        missingBatchName: 'Batch Syrup 50ml',
      }),
    ).toBe('Batch Syrup 50ml needs a batch number before Complete');
  });

  it('CG-17: missing serial names the item', () => {
    expect(
      firstCompleteDisabledReason({
        canSave: true,
        posKnown: true,
        missingSerialName: 'Serial Ampoule',
      }),
    ).toMatch(/Serial Ampoule/);
  });

  it('CG-03: stock BLOCK', () => {
    expect(
      firstCompleteDisabledReason({ canSave: true, posKnown: true, stockBlocked: true }),
    ).toMatch(/Insufficient stock/i);
  });

  it('CG-07: credit hold', () => {
    expect(
      firstCompleteDisabledReason({ canSave: true, posKnown: true, creditHold: true }),
    ).toMatch(/collection hold/i);
  });

  it('CG-08: credit limit exceeded', () => {
    expect(
      firstCompleteDisabledReason({ canSave: true, posKnown: true, creditLimitExceeded: true }),
    ).toMatch(/credit limit/i);
  });

  it('CG-06: RCM unconfirmed', () => {
    expect(
      firstCompleteDisabledReason({ canSave: true, posKnown: true, rcmUnconfirmed: true }),
    ).toMatch(/reverse charge/i);
  });

  it('CG-05 / CG-19: zero quantity', () => {
    expect(
      firstCompleteDisabledReason({ canSave: true, posKnown: true, zeroQty: true }),
    ).toMatch(/quantity greater than zero/i);
  });

  it('CG-27: note over cap', () => {
    expect(
      firstCompleteDisabledReason({ canSave: false, overCap: true }),
    ).toMatch(/source/i);
  });

  it('CG-04 / CG-18 / CG-25: preview pending', () => {
    expect(
      firstCompleteDisabledReason({ canSave: true, posKnown: true, previewPending: true }),
    ).toMatch(/preview/i);
  });

  it('CG-14: live IRN lock', () => {
    expect(
      firstCompleteDisabledReason({ canSave: true, posKnown: true, irnLocked: true }),
    ).toMatch(/IRN/i);
  });
});

describe('previewAllowsComplete — CG-04 / CG-18 / CG-25', () => {
  it('allows complete offline or when ready or when preview errored (fallback)', () => {
    expect(previewAllowsComplete(false, false, null)).toBe(true);
    expect(previewAllowsComplete(true, true, null)).toBe(true);
    expect(previewAllowsComplete(true, false, 'timeout')).toBe(true);
  });

  it('blocks only while the preview is still in flight', () => {
    expect(previewAllowsComplete(true, false, null)).toBe(false);
  });
});

describe('serialCountMatchesQty — CG-09 / CG-17', () => {
  it('requires an exact serial count', () => {
    expect(serialCountMatchesQty('', 1)).toBe(false);
    expect(serialCountMatchesQty('SN-1', 1)).toBe(true);
    expect(serialCountMatchesQty('SN-1, SN-2', 2)).toBe(true);
    expect(serialCountMatchesQty('SN-1', 2)).toBe(false);
  });
});

describe('posPayDisabledReason — CG-28 / CG-29 / CG-30 / CG-31', () => {
  it('names writes-blocked, busy, stock, batch, and serial', () => {
    expect(posPayDisabledReason({ mode: 'CASH', writesBlocked: true })).toMatch(/read-only|suspended|trial/i);
    expect(posPayDisabledReason({ mode: 'CASH', busy: true })).toMatch(/in progress/i);
    expect(posPayDisabledReason({ mode: 'CASH', stockBlocked: true })).toMatch(/Insufficient stock/i);
    expect(posPayDisabledReason({ mode: 'CASH', missingBatch: true })).toMatch(/batch/i);
    expect(posPayDisabledReason({ mode: 'CASH', missingSerial: true })).toMatch(/serial/i);
  });
});

describe('returnCompleteDisabledReason — CG-36', () => {
  it('names writes-blocked, owner-only, missing source, and no lines', () => {
    expect(returnCompleteDisabledReason({ writesBlocked: true })).toMatch(/read-only|suspended|trial/i);
    expect(returnCompleteDisabledReason({ permissionDenied: true })).toMatch(/Owner/i);
    expect(returnCompleteDisabledReason({ missingSource: true })).toMatch(/customer\/supplier/i);
    expect(returnCompleteDisabledReason({ noLines: true })).toMatch(/at least one item/i);
  });
});

describe('clientPreviewTotals — POS mock tender', () => {
  it('computes a grand total from snake_case lines so mock cash pay is not stranded', () => {
    const totals = clientPreviewTotals({
      items: [{ quantity: 2, unit_price: 100, gst_rate: 18 }],
    });
    expect(totals.subtotal).toBe(200);
    expect(totals.grandTotal).toBeGreaterThan(200);
  });
});
