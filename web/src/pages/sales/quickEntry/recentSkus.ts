/**
 * Recent products for Quick Entry. Only ids (plus name/sku as a loading placeholder) are stored:
 * price and GST always come from live product data, never from this device (QOE-03).
 */
const RECENT_SKUS_KEY = 'bizboard:quick-entry-recent-skus-v2';
const LEGACY_KEY = 'bizboard:quick-entry-recent-skus';
export const RECENT_SKUS_MAX = 8;

export interface RecentSku {
  id: number;
  name: string;
  sku: string;
}

function store(): Storage | null {
  try {
    return typeof localStorage === 'undefined' ? null : localStorage;
  } catch {
    return null;
  }
}

export function loadRecentSkus(companyId: number): RecentSku[] {
  const ls = store();
  if (!ls) return [];
  try {
    const raw = ls.getItem(`${RECENT_SKUS_KEY}:${companyId}`);
    const parsed = raw ? (JSON.parse(raw) as RecentSku[]) : [];
    return Array.isArray(parsed)
      ? parsed.filter((p) => p && Number.isFinite(p.id)).map((p) => ({ id: p.id, name: p.name ?? '', sku: p.sku ?? '' }))
      : [];
  } catch {
    return [];
  }
}

export function saveRecentSku(companyId: number, product: { id: number; name: string; sku: string }): RecentSku[] {
  const ls = store();
  const next = [
    { id: product.id, name: product.name, sku: product.sku },
    ...loadRecentSkus(companyId).filter((p) => p.id !== product.id),
  ].slice(0, RECENT_SKUS_MAX);
  if (!ls) return next;
  try {
    ls.setItem(`${RECENT_SKUS_KEY}:${companyId}`, JSON.stringify(next));
    // The old key stored prices and GST rates; drop it so stale values are never read again.
    ls.removeItem(`${LEGACY_KEY}:${companyId}`);
  } catch {
    // best-effort — a full/blocked localStorage must not break quick-entry
  }
  return next;
}

/** Drop products that are gone or inactive so a rejected item never lingers on the device. */
export function forgetRecentSkus(companyId: number, dropIds: number[]): RecentSku[] {
  const drop = new Set(dropIds);
  const next = loadRecentSkus(companyId).filter((p) => !drop.has(p.id));
  const ls = store();
  if (ls) {
    try {
      ls.setItem(`${RECENT_SKUS_KEY}:${companyId}`, JSON.stringify(next));
    } catch {
      /* ignore */
    }
  }
  return next;
}
