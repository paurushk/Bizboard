/** Pure counter rules. The page and the offline flush both use these. */

export type PosStockRow = {
  product: number;
  warehouse?: number | null;
  available?: string | number | null;
};

export function availableInWarehouse(
  rows: PosStockRow[],
  warehouseId: number | '' | null | undefined,
): Map<number, number> {
  const map = new Map<number, number>();
  if (warehouseId === '' || warehouseId == null) return map;
  for (const row of rows) {
    if (Number(row.warehouse) !== Number(warehouseId)) continue;
    const id = Number(row.product);
    const qty = Number(row.available ?? 0);
    if (!Number.isFinite(qty)) continue;
    map.set(id, (map.get(id) ?? 0) + qty);
  }
  return map;
}

export function lineSkipsStockGate(product: {
  productType?: string;
  trackInventory?: boolean;
}): boolean {
  return product.productType === 'SERVICE' || product.trackInventory === false;
}

export function offlineTenderAllowed(
  mode: string,
  opts?: { offlineCredit?: boolean; namedCustomer?: boolean },
): boolean {
  if (mode === 'CASH') return true;
  return mode === 'CREDIT' && Boolean(opts?.offlineCredit && opts?.namedCustomer);
}

export function offlineCreditBlock(opts: {
  enabled: boolean;
  named: boolean;
  stopCredit: boolean;
  billTotal: number;
  priorTotal: number;
  priorCount: number;
  cacheAgeMs: number | null;
}): string | null {
  if (!opts.enabled) return 'Offline credit is turned off.';
  if (!opts.named) return 'Offline credit needs a named customer.';
  if (opts.stopCredit) return 'This customer is on stop-credit.';
  if (opts.cacheAgeMs == null || opts.cacheAgeMs > 4 * 60 * 60 * 1000) {
    return 'Offline credit needs a credit check from the last 4 hours.';
  }
  if (opts.priorTotal + opts.billTotal > 5000) return 'Offline credit is capped at Rs 5,000 for this customer during the outage.';
  if (opts.priorCount >= 20) return 'Offline credit already has 20 bills on this terminal.';
  return null;
}

export function discountModeForCustomer(hasGstin: boolean): 'BEFORE_TAX' | 'AFTER_TAX' {
  return hasGstin ? 'BEFORE_TAX' : 'AFTER_TAX';
}

export function samePosLine(
  existing: { productId: number; batchNo?: string; trackBatch?: boolean },
  incoming: { productId: number; batchNo?: string; trackBatch?: boolean },
): boolean {
  if (existing.productId !== incoming.productId) return false;
  if (!incoming.trackBatch) return true;
  const left = (existing.batchNo || '').trim().toLowerCase();
  const right = (incoming.batchNo || '').trim().toLowerCase();
  return left !== '' && left === right;
}
