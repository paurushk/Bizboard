import { describe, expect, it } from 'vitest';
import { computeStockKpis, type SummaryRow } from '@/pages/inventory/stockKpis';

const summary: SummaryRow[] = [
  { product: 'Tea', sku: 'T1', warehouseId: 1, stockValue: '100' },
  { product: 'Tea', sku: 'T1', warehouseId: 2, stockValue: '50' },
  { product: 'Rice', sku: 'R1', warehouseId: 1, stockValue: '400' },
];
const shown = [
  { product: 1, availableNum: 5 },
  { product: 1, availableNum: 3 },
  { product: 2, availableNum: 0 },
];

describe('computeStockKpis', () => {
  it('counts items once however many godowns hold them, and does not add up units', () => {
    const kpis = computeStockKpis(shown, summary, {});
    expect(kpis.itemsInStock).toBe(1);
    expect(kpis.itemsOut).toBe(1);
  });

  it('values the same rows the list shows', () => {
    expect(computeStockKpis(shown, summary, {}).value).toBe(550);
    expect(computeStockKpis(shown, summary, { warehouseId: '1' }).value).toBe(500);
    expect(computeStockKpis(shown, summary, { query: 'tea' }).value).toBe(150);
    expect(computeStockKpis(shown, summary, { warehouseId: '2', query: 'rice' }).value).toBe(0);
  });

  it('shows no value rather than a wrong one under a custom-field filter', () => {
    expect(computeStockKpis(shown, summary, { customFieldFilterActive: true }).value).toBeNull();
  });

  it('reports a balance that disagrees with the movement history', () => {
    expect(computeStockKpis(shown, summary, {}).hasDrift).toBe(false);
    expect(computeStockKpis(shown, [{ ...summary[0], balanceDrift: true }], {}).hasDrift).toBe(true);
    expect(computeStockKpis(shown, [{ ...summary[0], reservedDrift: true }], {}).hasDrift).toBe(true);
  });
});
