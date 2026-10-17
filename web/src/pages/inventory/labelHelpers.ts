import type { Product } from '@/types/domain';
import { toNumber } from '@/utils/money';

/** Most copies of one label the page will print or download in one go. */
export const MAX_COPIES = 200;
/** The thermal-printer (ZPL) download is capped by the server at this many. */
export const MAX_ZPL_COPIES = 50;

export type LabelSize = 'small' | 'medium' | 'large' | 'a4_3x8' | 'a4_2x7';

export const LABEL_SIZES: Record<LabelSize, { width: string; minHeight: string }> = {
  small: { width: '2.6in', minHeight: '1.3in' },
  medium: { width: '3.2in', minHeight: '2in' },
  large: { width: '4in', minHeight: '2.5in' },
  // Sticker sheets on A4: 3 across x 8 down (70 x 37 mm) and 2 across x 7 down (99.1 x 38.1 mm).
  a4_3x8: { width: '70mm', minHeight: '37mm' },
  a4_2x7: { width: '99.1mm', minHeight: '38.1mm' },
};

/** Sticker-sheet templates: how many labels fit across and down one A4 page. */
export const SHEET_TEMPLATES: Partial<Record<LabelSize, { columns: number; rows: number }>> = {
  a4_3x8: { columns: 3, rows: 8 },
  a4_2x7: { columns: 2, rows: 7 },
};

/** Sizes a thermal (ZPL) printer can print: the sheet templates are for a normal printer. */
export function isThermalSize(size: LabelSize): size is 'small' | 'medium' | 'large' {
  return size === 'small' || size === 'medium' || size === 'large';
}

/** CODE128 takes printable ASCII. Anything else prints as a blank or wrong barcode. */
export function isCode128Encodable(code: string): boolean {
  if (!code) return false;
  for (const ch of code) {
    const point = ch.codePointAt(0) ?? 0;
    if (point < 32 || point > 126) return false;
  }
  return true;
}

/** A positive whole number of copies, never more than the cap. */
export function clampCopies(value: unknown, max = MAX_COPIES): number {
  const n = Math.trunc(toNumber(value as string | number));
  if (!Number.isFinite(n) || n < 0) return 0;
  return Math.min(n, max);
}

/**
 * The price on the shelf: MRP when there is one. An MRP of 0 means "not set", not "free", so it
 * falls back to the selling price instead of printing 0.
 */
export function labelPrice(product: Pick<Product, 'mrp' | 'sellingPrice'>): string | number {
  return toNumber(product.mrp) > 0 ? (product.mrp as string | number) : (product.sellingPrice as string | number);
}

/** `?items=12:5,13:2` from a purchase bill: item id and how many came in. */
export function parseLabelItems(search: string | null): Array<{ productId: number; copies: number }> {
  if (!search) return [];
  const out: Array<{ productId: number; copies: number }> = [];
  for (const part of search.split(',')) {
    const [id, qty] = part.split(':');
    const productId = Number(id);
    if (!Number.isInteger(productId) || productId <= 0) continue;
    out.push({ productId, copies: Math.max(1, clampCopies(Math.ceil(Number(qty) || 1))) });
  }
  return out;
}

export function labelItemsParam(items: Array<{ product: number; quantity: string | number }>): string {
  const merged = new Map<number, number>();
  for (const item of items) {
    if (!item.product) continue;
    merged.set(item.product, (merged.get(item.product) ?? 0) + Math.max(1, Math.ceil(toNumber(item.quantity))));
  }
  return [...merged.entries()].map(([id, qty]) => `${id}:${qty}`).join(',');
}

/**
 * The text a label carries, in the form the thermal-printer file prints it. The server writes the same
 * fields into the ZPL, so the two labels for one item read the same.
 */
export function labelFields(
  product: Pick<Product, 'name' | 'barcode' | 'sku' | 'mrp' | 'sellingPrice'>,
  batch: { batchNo: string; expiryDate?: string | null } | null,
): { name: string; code: string; price: string; batch: string; expiry: string } {
  return {
    name: product.name,
    code: (product.barcode || product.sku || '').trim(),
    price: `Rs ${toNumber(labelPrice(product)).toFixed(2)}`,
    batch: batch?.batchNo ?? '',
    expiry: batch?.expiryDate ?? '',
  };
}
