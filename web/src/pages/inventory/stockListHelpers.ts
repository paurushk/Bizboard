export const SORT_OPTIONS = ['name', 'available', '-available', '-on_hand'] as const;
export type StockSort = (typeof SORT_OPTIONS)[number];

/** A row's React key: product, godown and lot, so two lots of one item never collide. */
export function lotKey(lot: { product: number; warehouse?: number; batch?: number | null; id?: number }): string {
  return `lot-${lot.product}-${lot.warehouse ?? 'all'}-${lot.batch ?? 'none'}-${lot.id ?? ''}`;
}
