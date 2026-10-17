import type { StockBalance } from '@/types/domain';
import { toNumber } from '@/utils/money';

/**
 * The balance an adjustment will act on. A batch-tracked item has one row per lot: with a lot
 * chosen it is that lot's quantity, otherwise it is the whole item in the chosen godown (not the
 * first row that happens to match).
 */
export function currentRecordedQty(
  rows: StockBalance[],
  productId: number | null | undefined,
  warehouseId?: number | null,
  batchId?: number | null,
  batchNoOf?: (batchId: number) => string | undefined,
): number {
  if (!productId) return 0;
  const lotNo = batchId ? batchNoOf?.(batchId) : undefined;
  let total = 0;
  for (const row of rows) {
    if (Number(row.product) !== Number(productId)) continue;
    if (warehouseId && Number(row.warehouse) !== Number(warehouseId)) continue;
    if (lotNo !== undefined && row.batchNo !== lotNo) continue;
    total += toNumber(row.onHand);
  }
  return total;
}

/** Parse the typed quantity. Fractions are allowed (kg, metres); zero, negatives and junk are not. */
export function parseAdjustQty(raw: string): number | null {
  const text = raw.trim();
  if (!text) return null;
  const value = Number(text);
  if (!Number.isFinite(value) || value <= 0) return null;
  return value;
}

export function adjustmentValue(qty: number, purchasePrice: string | number | null | undefined): number {
  return Math.round(qty * toNumber(purchasePrice) * 100) / 100;
}
