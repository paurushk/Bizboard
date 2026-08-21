import type { Product } from '@/types/domain';

/** UXW2-016: emphasize SKU and optional stock so near-duplicate names are distinguishable. */
export function formatProductOptionLabel(
  product: Product,
  availableQty?: number | string | null,
): string {
  const parts = [`${product.name} · ${product.sku}`];
  if (product.unitName) parts.push(String(product.unitName));
  const qty =
    availableQty != null && availableQty !== ''
      ? availableQty
      : product.available ?? product.onHand;
  if (qty != null && qty !== '') parts.push(`avail ${qty}`);
  return parts.join(' · ');
}
