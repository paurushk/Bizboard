import { describe, expect, it } from 'vitest';
import { availablePosBatches, expiryForChosenBatch } from './posBatchExpiry';

describe('expiryForChosenBatch', () => {
  const lots = [
    { batchNo: 'LOT-1', expiryDate: '2026-12-31' },
    { batchNo: 'lot-2', expiryDate: null },
  ];

  it('returns the expiry of the typed batch and does not choose another lot', () => {
    expect(expiryForChosenBatch(lots, 'lot-1')).toBe('2026-12-31');
    expect(expiryForChosenBatch(lots, 'LOT-2')).toBeNull();
    expect(expiryForChosenBatch(lots, '')).toBeNull();
    expect(expiryForChosenBatch(lots, 'missing')).toBeNull();
  });
});

describe('availablePosBatches', () => {
  const rows = [
    { product: 1, warehouse: 4, batchNo: 'Lot B', nearestExpiry: '2027-12-01', available: '3' },
    { product: 1, warehouse: 4, batchNo: 'Lot A', nearestExpiry: '2027-01-01', available: '10.000' },
    { product: 1, warehouse: 4, batchNo: 'Empty', nearestExpiry: '2026-01-01', available: '0' },
    { product: 1, warehouse: 9, batchNo: 'Other godown', nearestExpiry: '2026-06-01', available: '5' },
    { product: 2, warehouse: 4, batchNo: 'Other item', nearestExpiry: null, available: 8 },
    { product: 1, warehouse: 4, batchNo: '', nearestExpiry: null, available: 4 },
  ];

  it('lists only in-stock lots for the product and godown, soonest expiry first', () => {
    expect(availablePosBatches(rows, 1, 4)).toEqual([
      { batchNo: 'Lot A', expiryDate: '2027-01-01', available: 10 },
      { batchNo: 'Lot B', expiryDate: '2027-12-01', available: 3 },
    ]);
  });

  it('returns nothing until a godown is selected', () => {
    expect(availablePosBatches(rows, 1, '')).toEqual([]);
  });
});
