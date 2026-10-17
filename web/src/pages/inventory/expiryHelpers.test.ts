import { describe, expect, it } from 'vitest';
import {
  qtyFor,
  qtyProblem,
  rowKey,
  splitByExpired,
  totalValue,
  writeOffable,
  type ExpiryRow,
} from '@/pages/inventory/expiryHelpers';

const row = (over: Partial<ExpiryRow> = {}): ExpiryRow => ({
  product: 1, productName: 'Milk', batch: 2, batchNo: 'L1', warehouse: 3, warehouseName: 'Main',
  expiryDate: '2026-10-01', onHand: '10', reserved: '3', available: '7', unitCost: '20', value: '140.00',
  daysToExpiry: -2, expired: true, ...over,
});

describe('expiry helpers', () => {
  it('splits expired lots from ones about to expire', () => {
    const { expired, soon } = splitByExpired([row(), row({ batch: 9, expired: false, daysToExpiry: 4 })]);
    expect(expired).toHaveLength(1);
    expect(soon).toHaveLength(1);
  });

  it('writes off what is free, not what orders are holding', () => {
    expect(writeOffable(row())).toBe(7);
    expect(writeOffable(row({ available: undefined }))).toBe(10);
    expect(writeOffable(row({ available: '-2' }))).toBe(0);
    expect(qtyFor(row(), {})).toBe('7');
  });

  it('refuses an empty, zero, negative or too-large quantity', () => {
    const key = rowKey(row());
    for (const typed of ['', '0', '-1', 'x', '8']) expect(qtyProblem(row(), { [key]: typed })).toBe(true);
    expect(qtyProblem(row(), { [key]: '7' })).toBe(false);
    expect(qtyProblem(row(), {})).toBe(false);
    expect(qtyProblem(row({ available: '0' }), {})).toBe(true);
  });

  it('values the write-off from each lot cost, or says nothing when costs are hidden', () => {
    const a = row();
    const b = row({ batch: 9, unitCost: '5', available: '4' });
    expect(totalValue([a, b], {})).toBe(7 * 20 + 4 * 5);
    expect(totalValue([a, b], { [rowKey(a)]: '1' })).toBe(20 + 20);
    expect(totalValue([row({ unitCost: null })], {})).toBeNull();
  });
});
