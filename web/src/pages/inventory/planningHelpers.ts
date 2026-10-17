import type { PlanningLine } from '@/api/osPlan';
import { toNumber } from '@/utils/money';

// A short godown can get a transfer and a purchase for the same item: the two rows need separate keys.
export const planRowKey = (
  row: Pick<PlanningLine, 'productId' | 'warehouseId'> & { transferFromWarehouseId?: number | null },
) => `${row.productId}-${row.warehouseId}-${row.transferFromWarehouseId ? `t${row.transferFromWarehouseId}` : 'p'}`;

export interface SupplierPick {
  id: number;
  name: string;
}

/** The quantity the buyer will order: what they typed, else what was suggested. */
export function effectiveQty(row: PlanningLine, edits: Record<string, string>): string {
  const typed = edits[planRowKey(row)];
  return typed !== undefined ? typed : String(row.suggestedQty);
}

export function qtyProblem(row: PlanningLine, edits: Record<string, string>): boolean {
  const qty = Number(effectiveQty(row, edits));
  return !Number.isFinite(qty) || qty <= 0;
}

/** What a whole-unit item (pieces, boxes) is rounded up to when the order is made. */
export function orderedQty(row: PlanningLine, edits: Record<string, string>): number {
  const qty = Number(effectiveQty(row, edits));
  if (!Number.isFinite(qty) || qty <= 0) return 0;
  return row.wholeUnitsOnly ? Math.ceil(qty) : qty;
}

export function effectiveSupplier(
  row: PlanningLine,
  overrides: Record<string, SupplierPick>,
): { id: number | null; name: string } {
  const picked = overrides[planRowKey(row)];
  if (picked) return { id: picked.id, name: picked.name };
  return { id: row.supplierId ?? null, name: row.supplierName ?? '' };
}

export interface PreviewGroup {
  supplierId: number;
  supplierName: string;
  lines: number;
  estimate: number;
}

export interface DraftPreview {
  /** One draft order per supplier. */
  groups: PreviewGroup[];
  /** Purchase rows with no supplier yet: left out until one is chosen. */
  noSupplier: PlanningLine[];
  /** Rows that are transfers between godowns, not purchases: opened on the transfer page instead. */
  transfers: PlanningLine[];
  /** Rows with a quantity the server would refuse. */
  invalid: PlanningLine[];
}

export function buildPreview(
  rows: PlanningLine[],
  edits: Record<string, string>,
  overrides: Record<string, SupplierPick>,
): DraftPreview {
  const out: DraftPreview = { groups: [], noSupplier: [], transfers: [], invalid: [] };
  const byId = new Map<number, PreviewGroup>();
  for (const row of rows) {
    if (row.transferFromWarehouseId) {
      out.transfers.push(row);
      continue;
    }
    if (qtyProblem(row, edits)) {
      out.invalid.push(row);
      continue;
    }
    const supplier = effectiveSupplier(row, overrides);
    if (!supplier.id) {
      out.noSupplier.push(row);
      continue;
    }
    const group = byId.get(supplier.id) ?? { supplierId: supplier.id, supplierName: supplier.name, lines: 0, estimate: 0 };
    group.lines += 1;
    group.estimate += orderedQty(row, edits) * toNumber(row.lastPrice);
    byId.set(supplier.id, group);
  }
  out.groups = [...byId.values()].sort((a, b) => a.supplierName.localeCompare(b.supplierName));
  return out;
}

/** The rows sent to the server: only purchase rows that will really be ordered, with the edits applied. */
export function draftRows(
  rows: PlanningLine[],
  edits: Record<string, string>,
  overrides: Record<string, SupplierPick>,
): PlanningLine[] {
  return rows
    .filter((row) => !row.transferFromWarehouseId && !qtyProblem(row, edits))
    .map((row) => ({
      ...row,
      suggestedQty: effectiveQty(row, edits),
      supplierId: effectiveSupplier(row, overrides).id,
    }));
}
