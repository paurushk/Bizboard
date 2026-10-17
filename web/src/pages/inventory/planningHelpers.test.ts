import { describe, expect, it } from 'vitest';
import type { PlanningLine } from '@/api/osPlan';
import {
  buildPreview,
  draftRows,
  effectiveQty,
  effectiveSupplier,
  orderedQty,
  planRowKey,
  qtyProblem,
} from '@/pages/inventory/planningHelpers';

const row = (over: Partial<PlanningLine> = {}): PlanningLine => ({
  productId: 1,
  productName: 'Tea',
  warehouseId: 10,
  warehouseName: 'Main',
  suggestedQty: '7',
  daysToStockout: 3,
  supplierId: 5,
  supplierName: 'Mega',
  transferFromWarehouseId: null,
  transferFromWarehouseName: '',
  lastPrice: '20',
  wholeUnitsOnly: true,
  ...over,
});

describe('quantity', () => {
  it('is what was typed, else what was suggested', () => {
    expect(effectiveQty(row(), {})).toBe('7');
    expect(effectiveQty(row(), { [planRowKey(row())]: '12' })).toBe('12');
  });
  it('is refused when it is empty, zero, negative or not a number', () => {
    for (const typed of ['', '0', '-3', 'abc']) {
      expect(qtyProblem(row(), { [planRowKey(row())]: typed })).toBe(true);
    }
    expect(qtyProblem(row(), {})).toBe(false);
  });
  it('rounds pieces up and leaves weights alone', () => {
    expect(orderedQty(row(), { [planRowKey(row())]: '2.5' })).toBe(3);
    expect(orderedQty(row({ wholeUnitsOnly: false }), { [planRowKey(row())]: '2.5' })).toBe(2.5);
    expect(orderedQty(row(), { [planRowKey(row())]: '0' })).toBe(0);
  });
});

describe('supplier', () => {
  it('uses the last supplier unless one was picked', () => {
    expect(effectiveSupplier(row(), {})).toEqual({ id: 5, name: 'Mega' });
    expect(effectiveSupplier(row(), { [planRowKey(row())]: { id: 9, name: 'Other' } })).toEqual({ id: 9, name: 'Other' });
    expect(effectiveSupplier(row({ supplierId: null, supplierName: '' }), {})).toEqual({ id: null, name: '' });
  });
});

describe('buildPreview', () => {
  const rows = [
    row({ productId: 1 }),
    row({ productId: 2, suggestedQty: '2.5' }),
    row({ productId: 3, supplierId: null, supplierName: '' }),
    row({ productId: 4, transferFromWarehouseId: 2 }),
    row({ productId: 5, suggestedQty: '0' }),
    row({ productId: 6, supplierId: 8, supplierName: 'Alpha' }),
  ];
  it('groups by supplier with an estimate and sets aside what will not be ordered', () => {
    const preview = buildPreview(rows, {}, {});
    expect(preview.groups.map((g) => [g.supplierName, g.lines, g.estimate])).toEqual([
      ['Alpha', 1, 140],
      ['Mega', 2, 7 * 20 + 3 * 20],
    ]);
    expect(preview.noSupplier.map((r) => r.productId)).toEqual([3]);
    expect(preview.transfers.map((r) => r.productId)).toEqual([4]);
    expect(preview.invalid.map((r) => r.productId)).toEqual([5]);
  });
  it('lets a picked supplier move a row out of "no supplier"', () => {
    const preview = buildPreview(rows, {}, { [planRowKey(rows[2])]: { id: 5, name: 'Mega' } });
    expect(preview.noSupplier).toEqual([]);
    expect(preview.groups.find((g) => g.supplierName === 'Mega')?.lines).toBe(3);
  });
});

describe('draftRows', () => {
  it('sends only purchase rows that will be ordered, with the edits applied', () => {
    const rows = [row({ productId: 1 }), row({ productId: 4, transferFromWarehouseId: 2 }), row({ productId: 5 })];
    const sent = draftRows(rows, { [planRowKey(rows[0])]: '9', [planRowKey(rows[2])]: '0' }, {
      [planRowKey(rows[0])]: { id: 77, name: 'New' },
    });
    expect(sent).toHaveLength(1);
    expect(sent[0]).toMatchObject({ productId: 1, suggestedQty: '9', supplierId: 77 });
  });
});
