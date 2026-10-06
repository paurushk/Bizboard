/** Lots the cashier can sell: stock on hand in the selected godown, soonest expiry first. */
export type PosStockLot = {
  product: number;
  warehouse?: number | null;
  batchNo?: string | null;
  nearestExpiry?: string | null;
  available?: string | number | null;
};

export type PosBatchChoice = {
  batchNo: string;
  expiryDate: string | null;
  available: number;
};

export function availablePosBatches(
  rows: PosStockLot[],
  productId: number,
  warehouseId: number | '' | null | undefined,
): PosBatchChoice[] {
  if (warehouseId === '' || warehouseId == null) return [];
  const grouped = new Map<string, PosBatchChoice>();
  for (const row of rows) {
    if (Number(row.product) !== Number(productId)) continue;
    if (Number(row.warehouse) !== Number(warehouseId)) continue;
    const batchNo = (row.batchNo ?? '').trim();
    if (!batchNo) continue;
    const qty = Number(row.available ?? 0);
    if (!Number.isFinite(qty) || qty <= 0) continue;
    const expiry = (row.nearestExpiry ?? '').trim() || null;
    const key = batchNo.toLowerCase();
    const existing = grouped.get(key);
    if (!existing) {
      grouped.set(key, { batchNo, expiryDate: expiry, available: qty });
      continue;
    }
    existing.available += qty;
    if (expiry && (!existing.expiryDate || expiry < existing.expiryDate)) {
      existing.expiryDate = expiry;
    }
  }
  return [...grouped.values()].sort((a, b) => {
    if (a.expiryDate && b.expiryDate && a.expiryDate !== b.expiryDate) {
      return a.expiryDate < b.expiryDate ? -1 : 1;
    }
    if (a.expiryDate && !b.expiryDate) return -1;
    if (!a.expiryDate && b.expiryDate) return 1;
    return a.batchNo.localeCompare(b.batchNo);
  });
}

/** A2-9: show the expiry already stored on the lot the cashier typed. Never pick a lot. */

export function expiryForChosenBatch(
  lots: Array<{ batchNo?: string | null; expiryDate?: string | null }>,
  batchNo: string,
): string | null {
  const key = batchNo.trim().toLowerCase();
  if (!key) return null;
  const match = lots.find((lot) => (lot.batchNo ?? '').trim().toLowerCase() === key);
  const expiry = match?.expiryDate?.trim();
  return expiry || null;
}
