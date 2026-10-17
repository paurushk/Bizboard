import type { ChartAccount } from '@/api/resources';

/** Order accounts as a tree: each parent followed by its children, with a depth for indenting. */
export function toTree(rows: ChartAccount[]): Array<ChartAccount & { depth: number }> {
  const byParent = new Map<number | null, ChartAccount[]>();
  const ids = new Set(rows.map((r) => r.id));
  for (const r of rows) {
    // A row whose parent is hidden by a filter is shown at the top level so it never vanishes.
    const key = r.parent !== null && ids.has(r.parent) ? r.parent : null;
    byParent.set(key, [...(byParent.get(key) ?? []), r]);
  }
  const out: Array<ChartAccount & { depth: number }> = [];
  const walk = (parent: number | null, depth: number) => {
    for (const r of (byParent.get(parent) ?? []).sort((a, b) => a.code.localeCompare(b.code))) {
      out.push({ ...r, depth });
      walk(r.id, depth + 1);
    }
  };
  walk(null, 0);
  return out;
}
