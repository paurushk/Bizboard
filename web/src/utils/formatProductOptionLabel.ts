import type { Product } from '@/types/domain';

/** UXW2-016: emphasize SKU and optional stock so near-duplicate names are distinguishable.
 * Stock identity lives on StockBalance.available (B12) — never fall back to Product.onHand. */
export function formatProductOptionLabel(
  product: Product,
  availableQty?: number | string | null,
): string {
  const parts = [`${product.name} · ${product.sku}`];
  if (product.unitName) parts.push(String(product.unitName));
  if (availableQty != null && availableQty !== '') {
    parts.push(`avail ${availableQty}`);
  }
  return parts.join(' · ');
}
