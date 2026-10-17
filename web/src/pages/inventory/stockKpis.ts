import { toNumber } from '@/utils/money';

/** A row of the inventory summary report (product x godown), as the page maps it. */
export interface SummaryRow {
  product?: string;
  sku?: string;
  warehouseId?: number | string | null;
  stockValue?: string | number | null;
  balanceDrift?: boolean;
  reservedDrift?: boolean;
}

export interface StockKpis {
  /** Items that have something available (counted once however many godowns hold them). */
  itemsInStock: number;
  /** Items shown with nothing available. */
  itemsOut: number;
  /** Value of the rows on screen, from the same filters; null when it cannot be worked out. */
  value: number | null;
  /** Some balance disagrees with the movement history. */
  hasDrift: boolean;
}

interface ShownRow {
  product: number | string;
  availableNum: number;
}

/**
 * The KPI chips under Current stock. Quantity is not added up: kilograms, pieces and boxes do not
 * make a number. Value uses the summary rows narrowed by the same godown and search the list uses,
 * so the figures move together when a filter changes. With a custom-field filter the summary
 * cannot be narrowed the same way, so no value is shown rather than a wrong one.
 */
export function computeStockKpis(
  shown: ShownRow[],
  summary: SummaryRow[],
  filters: { warehouseId?: string; query?: string; customFieldFilterActive?: boolean },
): StockKpis {
  const perItem = new Map<string, number>();
  for (const row of shown) {
    const key = String(row.product);
    perItem.set(key, (perItem.get(key) ?? 0) + row.availableNum);
  }
  let itemsInStock = 0;
  let itemsOut = 0;
  for (const qty of perItem.values()) {
    if (qty > 0) itemsInStock += 1;
    else itemsOut += 1;
  }

  const q = (filters.query ?? '').trim().toLowerCase();
  const narrowed = summary.filter((row) => {
    if (filters.warehouseId && String(row.warehouseId ?? '') !== String(filters.warehouseId)) return false;
    if (q && !`${row.product ?? ''} ${row.sku ?? ''}`.toLowerCase().includes(q)) return false;
    return true;
  });
  const value = filters.customFieldFilterActive
    ? null
    : narrowed.reduce((sum, row) => sum + toNumber(row.stockValue), 0);
  return {
    itemsInStock,
    itemsOut,
    value,
    hasDrift: summary.some((row) => row.balanceDrift || row.reservedDrift),
  };
}
