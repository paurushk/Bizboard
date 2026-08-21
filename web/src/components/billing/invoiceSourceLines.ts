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
}

export function invoiceItemsToSourceLines(items: LineItem[]): InvoiceSourceLine[] {
  return items.map((item, idx) => ({
    key: `src-${item.id ?? idx}-${item.product}`,
    lineId: item.id,
    sourceItemId: item.id,
    product: item.product,
    productName: item.productName ?? item.description ?? `Product #${item.product}`,
    maxQty: toNumber(item.quantity),
    quantity: 0,
    unitPrice: toNumber(item.unitPrice),
    gstRate: toNumber(item.gstRate),
    cessRate: toNumber(item.cessRate),
    discountPercent: toNumber(item.discountPercent),
    included: false,
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
  const n = Math.max(0, Math.floor(qty) || 0);
  return Math.min(n, line.maxQty);
}

export function activeSourceLines(lines: InvoiceSourceLine[]): InvoiceSourceLine[] {
  return lines.filter((l) => l.included && l.quantity > 0);
}
