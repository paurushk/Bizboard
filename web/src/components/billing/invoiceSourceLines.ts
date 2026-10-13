import type { LineItem, ReturnableLine } from '@/types/domain';
import { toNumber } from '@/utils/money';
import { formatSerialNumbersText, parseSerialNumbersText } from './lineHelpers';

/** Draft line sourced from an invoice with qty cap per original line. */
export interface InvoiceSourceLine {
  key: string;
  lineId?: number;
  sourceItemId?: number;
  product: number;
  productName: string;
  maxQty: number;
  quantity: number;
  unitPrice: number;
  gstRate: number;
  cessRate: number;
  discountPercent: number;
  included: boolean;
  condition?: 'SELLABLE' | 'DAMAGED';
  serialNumbersText?: string;
  soldSerialNumbers?: string[];
  trackSerial?: boolean;
  trackBatch?: boolean;
  batchNo?: string;
  batch?: number | null;
}

export type SourceLineProductMeta = {
  trackSerial?: boolean;
  trackBatch?: boolean;
};

export function sourceLineReturnPayload(
  line: InvoiceSourceLine,
  opts?: { includeBatch?: boolean; includeSourceItem?: boolean },
) {
  const serialNumbers = parseSerialNumbersText(line.serialNumbersText ?? '');
  return {
    product: line.product,
    ...(opts?.includeSourceItem !== false && line.sourceItemId != null
      ? { sourceItem: line.sourceItemId }
      : {}),
    quantity: hasSerialPickList(line) ? serialNumbers.length : line.quantity,
    unitPrice: line.unitPrice,
    ...(line.discountPercent ? { discountPercent: line.discountPercent } : {}),
    gstRate: line.gstRate,
    condition: line.condition || 'SELLABLE',
    ...(serialNumbers.length ? { serialNumbers } : {}),
    ...(opts?.includeBatch && line.batch ? { batch: line.batch } : {}),
  };
}

/** True when the operator picks sold serials from a list (quantity follows the picks). */
export function hasSerialPickList(line: InvoiceSourceLine): boolean {
  return Boolean(line.trackSerial && line.soldSerialNumbers && line.soldSerialNumbers.length > 0);
}

/** Serials currently picked on a line, in pick order. */
export function pickedSerials(line: InvoiceSourceLine): string[] {
  return parseSerialNumbersText(line.serialNumbersText ?? '');
}

/**
 * Toggle one sold serial. Quantity always equals the number picked and can never
 * exceed the line's returnable quantity, so the payload is valid by construction.
 */
export function toggleSerialPick(line: InvoiceSourceLine, serial: string): Partial<InvoiceSourceLine> {
  const current = pickedSerials(line);
  const next = current.includes(serial)
    ? current.filter((s) => s !== serial)
    : current.length >= Math.floor(line.maxQty)
      ? current
      : [...current, serial];
  return { serialNumbersText: formatSerialNumbersText(next), quantity: next.length };
}

/** Serials beyond the quantity are dropped when a free-text serial line's quantity shrinks. */
export function trimSerialsToQty(text: string | undefined, quantity: number): string {
  const serials = parseSerialNumbersText(text ?? '');
  const keep = Math.max(0, Math.trunc(quantity));
  return serials.length > keep ? formatSerialNumbersText(serials.slice(0, keep)) : (text ?? '');
}

export function invoiceItemsToSourceLines(
  items: LineItem[],
  // F2-013: quantities already returned on earlier return documents, per
  // product — subtracted from maxQty so the same units can't be returned twice.
  alreadyReturnedByProduct?: Map<number, number>,
  productsById?: Map<number, SourceLineProductMeta>,
  alreadyReturnedBySourceItem?: Map<number, number>,
  // Server-computed headroom (returns + standalone credit notes). When given it
  // replaces the client-side arithmetic and also hides already-returned serials.
  returnable?: ReturnableLine[],
): InvoiceSourceLine[] {
  const returnableByItem = new Map((returnable ?? []).map((r) => [r.sourceItem, r]));
  const remainingUnlinkedByProduct = new Map<number, number>();
  if (alreadyReturnedByProduct) {
    for (const [prodId, qty] of alreadyReturnedByProduct.entries()) {
      remainingUnlinkedByProduct.set(prodId, qty);
    }
  }
  return items.map((item, idx) => {
    const meta = productsById?.get(item.product);
    const serials = item.serialNumbers ?? [];
    const soldQty = toNumber(item.quantity);
    const byLine = item.id != null ? (alreadyReturnedBySourceItem?.get(item.id) ?? 0) : 0;
    const afterLine = Math.max(0, soldQty - byLine);
    const unlinkedPool = remainingUnlinkedByProduct.get(item.product) ?? 0;
    const takeUnlinked = Math.min(afterLine, unlinkedPool);
    if (takeUnlinked > 0) {
      remainingUnlinkedByProduct.set(item.product, unlinkedPool - takeUnlinked);
    }
    const serverRow = item.id != null ? returnableByItem.get(item.id) : undefined;
    const maxQty = serverRow
      ? Math.max(0, Math.round(serverRow.returnable * 1000) / 1000)
      : Math.max(0, Math.round((afterLine - takeUnlinked) * 1000) / 1000);
    const alreadyReturnedSerials = new Set(serverRow?.returnedSerials ?? []);
    const availableSerials = serials.filter((sn) => !alreadyReturnedSerials.has(sn));
    return {
      key: `src-${item.id ?? idx}-${item.product}`,
      lineId: item.id,
      sourceItemId: item.id,
      product: item.product,
      productName: item.productName ?? item.description ?? `Product #${item.product}`,
      maxQty,
      quantity: 0,
      unitPrice: toNumber(item.unitPrice),
      gstRate: toNumber(item.gstRate),
      cessRate: toNumber(item.cessRate),
      discountPercent: toNumber(item.discountPercent),
      included: false,
      condition: 'SELLABLE',
      // Nothing is pre-picked: the operator chooses which sold serials come back.
      serialNumbersText: '',
      soldSerialNumbers: availableSerials,
      trackSerial: Boolean(meta?.trackSerial || serials.length),
      trackBatch: Boolean(meta?.trackBatch || item.batch || item.batchNo),
      batchNo: item.batchNo ?? '',
      batch: item.batch ?? null,
    };
  });
}

export function noteItemsToSourceLines(
  items: LineItem[],
  invoiceItems: LineItem[],
): InvoiceSourceLine[] {
  const maxByProduct = new Map<number, number>();
  for (const inv of invoiceItems) {
    maxByProduct.set(inv.product, toNumber(inv.quantity));
  }
  return items.map((item, idx) => ({
    key: `edit-${item.id ?? idx}-${item.product}`,
    lineId: item.id,
    sourceItemId: item.id,
    product: item.product,
    productName: item.productName ?? item.description ?? `Product #${item.product}`,
    maxQty: maxByProduct.get(item.product) ?? toNumber(item.quantity),
    quantity: toNumber(item.quantity),
    unitPrice: toNumber(item.unitPrice),
    gstRate: toNumber(item.gstRate),
    cessRate: toNumber(item.cessRate),
    discountPercent: toNumber(item.discountPercent),
    included: true,
  }));
}

export function clampSourceLineQty(line: InvoiceSourceLine, qty: number): number {
  // F2-010: don't floor — a source line of 2.5 KG / 0.75 LTR must be
  // creditable / returnable for its real fractional amount. Just clamp to
  // [0, maxQty] and round to a sane 3dp to avoid float dust.
  const n = Math.max(0, Number.isFinite(qty) ? qty : 0);
  const clamped = Math.min(n, line.maxQty);
  return Math.round(clamped * 1000) / 1000;
}

export function activeSourceLines(lines: InvoiceSourceLine[]): InvoiceSourceLine[] {
  return lines.filter((l) => l.included && l.quantity > 0);
}
