import { describe, expect, it } from 'vitest';
import type { StockBalance } from '@/types/domain';
import { adjustmentValue, currentRecordedQty, parseAdjustQty } from '@/pages/inventory/adjustmentHelpers';

const row = (over: Partial<StockBalance>): StockBalance => ({
  product: 1,
  warehouse: 10,
  productName: 'Rice',
  sku: 'R1',
  onHand: 0,
  reserved: 0,
  available: 0,
  reorderLevel: 0,
  ...over,
});

describe('currentRecordedQty', () => {
  const rows = [
    row({ onHand: '5', batchNo: 'A' }),
    row({ onHand: '7', batchNo: 'B' }),
    row({ onHand: '3', warehouse: 11, batchNo: 'A' }),
    row({ product: 2, onHand: '99' }),
  ];

  it('adds every lot of the item in the chosen godown instead of taking the first row', () => {
    expect(currentRecordedQty(rows, 1, 10)).toBe(12);
  });

  it('uses only the chosen lot when one is picked', () => {
    expect(currentRecordedQty(rows, 1, 10, 7, (id) => (id === 7 ? 'B' : undefined))).toBe(7);
  });

  it('adds all godowns when none is chosen', () => {
    expect(currentRecordedQty(rows, 1)).toBe(15);
  });

  it('is zero without a product', () => {
    expect(currentRecordedQty(rows, null)).toBe(0);
  });
});

describe('parseAdjustQty', () => {
  it('accepts fractions below one', () => {
    expect(parseAdjustQty('0.5')).toBe(0.5);
  });
  it.each(['', ' ', '0', '-1', 'abc'])('rejects %j', (raw) => {
    expect(parseAdjustQty(raw)).toBeNull();
  });
});

describe('adjustmentValue', () => {
  it('is quantity times purchase price, to the paisa', () => {
    expect(adjustmentValue(2.5, '10.10')).toBe(25.25);
  });
});
