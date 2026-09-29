import type { Product } from '@/types/domain';

/** Exact barcode or SKU wins. Otherwise match name, SKU, or barcode. */
export function filterProductsForPicker(options: Product[], query: string): Product[] {
  const q = query.trim().toLowerCase();
  if (!q) return options;
  const exact = options.filter(
    (product) =>
      (product.barcode ?? '').toLowerCase() === q || (product.sku ?? '').toLowerCase() === q,
  );
  if (exact.length > 0) return exact;
  return options.filter((product) => {
    const name = (product.name ?? '').toLowerCase();
    const sku = (product.sku ?? '').toLowerCase();
    const barcode = (product.barcode ?? '').toLowerCase();
    return name.includes(q) || sku.includes(q) || barcode.includes(q);
  });
}

export function exactBarcodeOrSku(options: Product[], query: string): Product | null {
  const q = query.trim().toLowerCase();
  if (q.length < 3) return null;
  const exact = options.filter(
    (product) => (product.barcode ?? '').toLowerCase() === q || (product.sku ?? '').toLowerCase() === q,
  );
  return exact.length === 1 ? exact[0] : null;
}
