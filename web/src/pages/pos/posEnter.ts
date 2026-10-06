/** How Enter on the POS scanner chooses a product. Exact code beats a highlighted fuzzy row. */

export const POS_ENTER_EXACT_WINS = true;

export type PosEnterProduct = { id: number; sku: string; barcode?: string | null };

export type PosEnterChoice =
  | { action: 'add'; productId: number; via: 'exact' | 'highlight' }
  | { action: 'wait' }
  | { action: 'barcode-lookup' };

export function looksLikeHardwareScan(query: string): boolean {
  const q = query.trim();
  return q.length >= 8 && !/\s/.test(q);
}

export function findExactProduct(query: string, catalog: PosEnterProduct[]): PosEnterProduct | undefined {
  const q = query.trim().toLowerCase();
  if (!q) return undefined;
  return (
    catalog.find((p) => (p.barcode ?? '').toLowerCase() === q) ??
    catalog.find((p) => p.sku.toLowerCase() === q)
  );
}

export function choosePosEnter(args: {
  query: string;
  highlighted: PosEnterProduct | null;
  listOpen: boolean;
  catalog: PosEnterProduct[];
  optionsStale: boolean;
  exactWins?: boolean;
}): PosEnterChoice {
  const exactWins = args.exactWins ?? POS_ENTER_EXACT_WINS;
  const exact = exactWins ? findExactProduct(args.query, args.catalog) : undefined;
  if (exact) return { action: 'add', productId: exact.id, via: 'exact' };
  const scanPending = args.optionsStale && looksLikeHardwareScan(args.query);
  if (scanPending) return { action: 'wait' };
  if (args.listOpen && args.highlighted) {
    return { action: 'add', productId: args.highlighted.id, via: 'highlight' };
  }
  return { action: 'barcode-lookup' };
}
