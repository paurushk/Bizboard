import { describe, expect, it } from 'vitest';

import {
  availableInWarehouse,
  discountModeForCustomer,
  lineSkipsStockGate,
  offlineTenderAllowed,
  samePosLine,
} from './posRules';

describe('posRules', () => {
  it('counts stock only in the selected warehouse', () => {
    const map = availableInWarehouse(
      [
        { product: 1, warehouse: 10, available: 0 },
        { product: 1, warehouse: 11, available: 25 },
      ],
      10,
    );
    expect(map.get(1)).toBe(0);
    expect(availableInWarehouse([{ product: 1, warehouse: 10, available: 4 }], '').size).toBe(0);
  });

  it('does not stock-gate services', () => {
    expect(lineSkipsStockGate({ productType: 'SERVICE', trackInventory: true })).toBe(true);
    expect(lineSkipsStockGate({ productType: 'GOODS', trackInventory: false })).toBe(true);
    expect(lineSkipsStockGate({ productType: 'GOODS', trackInventory: true })).toBe(false);
  });

  it('allows only cash offline', () => {
    expect(offlineTenderAllowed('CASH')).toBe(true);
    expect(offlineTenderAllowed('CARD')).toBe(false);
    expect(offlineTenderAllowed('CREDIT')).toBe(false);
  });

  it('uses before-tax discount when the customer has a GSTIN', () => {
    expect(discountModeForCustomer(true)).toBe('BEFORE_TAX');
    expect(discountModeForCustomer(false)).toBe('AFTER_TAX');
  });

  it('merges a batch line only when the lot matches', () => {
    expect(samePosLine(
      { productId: 1, batchNo: 'A', trackBatch: true },
      { productId: 1, batchNo: 'A', trackBatch: true },
    )).toBe(true);
    expect(samePosLine(
      { productId: 1, batchNo: 'A', trackBatch: true },
      { productId: 1, batchNo: 'B', trackBatch: true },
    )).toBe(false);
    expect(samePosLine(
      { productId: 1, trackBatch: false },
      { productId: 1, trackBatch: false },
    )).toBe(true);
  });
});