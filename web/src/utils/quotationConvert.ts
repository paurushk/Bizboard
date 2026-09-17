import { toNumber } from '@/utils/money';
import type { LineItem } from '@/types/domain';

/** CFT-115: qty still convertible on a quotation line. */
export function remainingQuotationQty(line: {
  quantity?: string | number;
  convertedQuantity?: string | number;
}): number {
  const quoted = toNumber(line.quantity);
  const converted = toNumber(line.convertedQuantity);
  return Math.max(0, quoted - converted);
}

export type ConvertLinePayload = { id: number; quantity: number };

/** Build convert API items from per-line convert qty. Omits zero/empty lines. */
export function buildConvertItemsPayload(
  lines: Array<Pick<LineItem, 'id' | 'quantity' | 'convertedQuantity'>>,
  convertQtyById: Record<number, number>,
): ConvertLinePayload[] {
  const out: ConvertLinePayload[] = [];
  for (const line of lines) {
    if (line.id == null) continue;
    const remaining = remainingQuotationQty(line);
    const raw = convertQtyById[line.id];
    const qty = Number.isFinite(raw) ? raw : remaining;
    if (qty <= 0) continue;
    if (qty > remaining) {
      throw new Error(`Convert quantity ${qty} exceeds remaining ${remaining}`);
    }
    out.push({ id: line.id, quantity: qty });
  }
  return out;
}

/** True when converting `converting` still leaves qty on the quotation. */
export function quotationHasRemainingAfterConvert(
  lines: Array<Pick<LineItem, 'id' | 'quantity' | 'convertedQuantity'>>,
  converting: ConvertLinePayload[],
): boolean {
  const byId = new Map(converting.map((row) => [row.id, row.quantity]));
  for (const line of lines) {
    if (line.id == null) continue;
    const left = remainingQuotationQty(line) - (byId.get(line.id) ?? 0);
    if (left > 0) return true;
  }
  return false;
}
