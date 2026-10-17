import type { StockBalance } from '@/types/domain';
import { toNumber } from '@/utils/money';

/** How far below its reorder level an item is (never negative). */
export function shortfall(row: Pick<StockBalance, 'available' | 'reorderLevel'>): number {
  return Math.max(0, toNumber(row.reorderLevel) - toNumber(row.available));
}

/** A first order quantity: bring the item back to its reorder level, at least one unit. */
export function suggestedOrderQty(row: Pick<StockBalance, 'available' | 'reorderLevel'>): number {
  return Math.max(1, Math.round(shortfall(row) * 1000) / 1000);
}

/** The purchase-order editor reads `product` and `qty` from the address bar. */
export function reorderHref(row: Pick<StockBalance, 'product' | 'available' | 'reorderLevel'>): string {
  return `/purchases/orders/new?product=${row.product}&qty=${suggestedOrderQty(row)}`;
}

/** Biggest shortfall first; ties by name so the order is stable. */
export function sortByShortfall<T extends StockBalance>(rows: T[]): T[] {
  return [...rows].sort(
    (a, b) => shortfall(b) - shortfall(a) || String(a.productName).localeCompare(String(b.productName)),
  );
}

export function matchesSearch(row: Pick<StockBalance, 'productName' | 'sku'>, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return String(row.productName ?? '').toLowerCase().includes(q) || String(row.sku ?? '').toLowerCase().includes(q);
}
