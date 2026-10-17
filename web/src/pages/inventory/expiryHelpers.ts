import { toNumber } from '@/utils/money';

/** A row of the expiry alert list as the page reads it. */
export interface ExpiryRow {
  product: number;
  productName: string;
  batch: number;
  batchNo: string;
  warehouse: number;
  warehouseName: string;
  expiryDate: string;
  onHand: string | number;
  reserved?: string | number;
  /** What can be written off: on hand less what orders are holding. */
  available?: string | number;
  unitCost?: string | number | null;
  value?: string | number | null;
  daysToExpiry: number;
  expired: boolean;
  /** The purchase bill this lot came in on, when it can be traced. */
  purchaseInvoice?: number | null;
}

/** Where "Return to supplier" goes: the return form for the lot's own bill, else a blank one. */
export function supplierReturnHref(row: Pick<ExpiryRow, 'purchaseInvoice'>): string {
  return row.purchaseInvoice ? `/purchases/returns?purchase=${row.purchaseInvoice}` : '/purchases/returns?create=1';
}

export const rowKey = (row: Pick<ExpiryRow, 'product' | 'batch' | 'warehouse'>) =>
  `${row.product}-${row.batch}-${row.warehouse}`;

export function splitByExpired(rows: ExpiryRow[]): { expired: ExpiryRow[]; soon: ExpiryRow[] } {
  return { expired: rows.filter((r) => r.expired), soon: rows.filter((r) => !r.expired) };
}

/** Held-for-order stock cannot be written off, so the default is what is free. */
export function writeOffable(row: ExpiryRow): number {
  const available = row.available === undefined ? toNumber(row.onHand) : toNumber(row.available);
  return Math.max(0, available);
}

export function qtyFor(row: ExpiryRow, typed: Record<string, string>): string {
  const mine = typed[rowKey(row)];
  return mine !== undefined ? mine : String(writeOffable(row));
}

/** Empty, zero, negative, not a number, or more than can be written off. */
export function qtyProblem(row: ExpiryRow, typed: Record<string, string>): boolean {
  const qty = Number(qtyFor(row, typed));
  return !Number.isFinite(qty) || qty <= 0 || qty > writeOffable(row);
}

/** Worth of what would be written off, from each lot's unit cost; null when costs are hidden. */
export function totalValue(rows: ExpiryRow[], typed: Record<string, string>): number | null {
  let sum = 0;
  for (const row of rows) {
    if (row.unitCost == null) return null;
    const qty = Number(qtyFor(row, typed));
    if (Number.isFinite(qty) && qty > 0) sum += qty * toNumber(row.unitCost);
  }
  return Math.round(sum * 100) / 100;
}
