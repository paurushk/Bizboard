import type { LineItem } from '@/types/domain';
import { toNumber } from '@/utils/money';

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
}

export function invoiceItemsToSourceLines(
  items: LineItem[],
  // F2-013: quantities already returned on earlier return documents, per
  // product — subtracted from maxQty so the same units can't be returned twice.
  alreadyReturnedByProduct?: Map<number, number>,
): InvoiceSourceLine[] {
  return items.map((item, idx) => ({
    key: `src-${item.id ?? idx}-${item.product}`,
    lineId: item.id,
    sourceItemId: item.id,
    product: item.product,
    productName: item.productName ?? item.description ?? `Product #${item.product}`,
    maxQty: Math.max(
      0,
      toNumber(item.quantity) - (alreadyReturnedByProduct?.get(item.product) ?? 0),
    ),
    quantity: 0,
    unitPrice: toNumber(item.unitPrice),
    gstRate: toNumber(item.gstRate),
    cessRate: toNumber(item.cessRate),
    discountPercent: toNumber(item.discountPercent),
    included: false,
    condition: 'SELLABLE',
  }));
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
