import { apiClient, unwrapData } from '@/api/client';

const DB_NAME = 'bizboard-pos-catalog';
const STORE = 'products';

export interface PosCatalogRow {
  id: number;
  name: string;
  sku: string;
  barcode: string;
  price: string;
  gst: string;
  hsn: string;
  unit: string;
  trackBatch: boolean;
  trackSerial: boolean;
  productType: string;
  updatedAt?: string;
}

interface CatalogPage {
  results: Array<Record<string, unknown>>;
  deletedIds?: number[];
  deleted_ids?: number[];
  nextCursor?: number | null;
  next_cursor?: number | null;
}

/** The API renderer camelCases keys. Read either spelling so a renderer change cannot blank the flags. */
function pick(raw: Record<string, unknown>, camel: string, snake: string): unknown {
  return raw[camel] !== undefined ? raw[camel] : raw[snake];
}

const FULL_SYNC_EVERY_MS = 7 * 24 * 36e5;

function openDb(companyId: number): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(`${DB_NAME}-${companyId}`, 1);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE)) {
        const store = db.createObjectStore(STORE, { keyPath: 'id' });
        store.createIndex('barcode', 'barcode', { unique: false });
        store.createIndex('sku', 'sku', { unique: false });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

export function mapRow(raw: Record<string, unknown>): PosCatalogRow {
  return {
    id: Number(raw.id),
    name: String(raw.name || ''),
    sku: String(raw.sku || ''),
    barcode: String(raw.barcode || ''),
    price: String(raw.price || '0'),
    gst: String(raw.gst || '0'),
    hsn: String(raw.hsn || ''),
    unit: String(raw.unit || ''),
    trackBatch: Boolean(pick(raw, 'trackBatch', 'track_batch')),
    trackSerial: Boolean(pick(raw, 'trackSerial', 'track_serial')),
    productType: String(pick(raw, 'productType', 'product_type') || ''),
    updatedAt: pick(raw, 'updatedAt', 'updated_at') ? String(pick(raw, 'updatedAt', 'updated_at')) : undefined,
  };
}

/** Delta since the last sync, or a full sync when there is none or it is a week old. */
export async function syncPosCatalog(companyId: number, updatedAfter?: string): Promise<number> {
  const startedAt = new Date().toISOString();
  const lastRaw = localStorage.getItem(`bb_pos_catalog_synced:${companyId}`);
  const last = lastRaw ? Date.parse(lastRaw) : NaN;
  const delta = updatedAfter
    ?? (Number.isFinite(last) && Date.now() - last < FULL_SYNC_EVERY_MS ? lastRaw ?? undefined : undefined);
  const seen = new Set<number>();
  let cursor: number | null = 0;
  let count = 0;
  const db = await openDb(companyId);
  try {
    while (cursor != null) {
      const response: { data: unknown } = await apiClient.get('/products/pos-catalog/', {
        params: { cursor: cursor || undefined, updated_after: delta },
      });
      const page: CatalogPage = unwrapData<CatalogPage>(response.data);
      const rows = (page.results || []).map(mapRow);
      const removed = page.deletedIds ?? page.deleted_ids ?? [];
      await new Promise<void>((resolve, reject) => {
        const tx = db.transaction(STORE, 'readwrite');
        const store = tx.objectStore(STORE);
        for (const row of rows) {
          store.put(row);
          seen.add(row.id);
        }
        for (const id of removed) store.delete(id);
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
      });
      count += rows.length;
      cursor = page.nextCursor ?? page.next_cursor ?? null;
    }
    if (!delta) {
      // A full sync is the whole catalogue, so anything not returned was removed or deactivated.
      await new Promise<void>((resolve, reject) => {
        const tx = db.transaction(STORE, 'readwrite');
        const store = tx.objectStore(STORE);
        const keys = store.getAllKeys();
        keys.onsuccess = () => {
          for (const key of keys.result as number[]) {
            if (!seen.has(Number(key))) store.delete(key);
          }
        };
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
      });
    }
  } finally {
    db.close();
  }
  // Stamp the start, so a product edited during the sync is picked up by the next delta.
  localStorage.setItem(`bb_pos_catalog_synced:${companyId}`, startedAt);
  return count;
}

function indexGet(store: IDBObjectStore, index: string, key: string): Promise<PosCatalogRow | null> {
  return new Promise((resolve, reject) => {
    const request = store.index(index).get(key);
    request.onsuccess = () => resolve((request.result as PosCatalogRow | undefined) ?? null);
    request.onerror = () => reject(request.error);
  });
}

export async function findLocalCatalog(companyId: number, code: string): Promise<PosCatalogRow | null> {
  const db = await openDb(companyId);
  try {
    const raw = code.trim();
    const wanted = raw.toLowerCase();
    // Exact keys through the indexes first, so a scan does not read the whole catalogue.
    const store = db.transaction(STORE, 'readonly').objectStore(STORE);
    for (const key of new Set([raw, wanted, raw.toUpperCase()])) {
      const hit = (await indexGet(store, 'barcode', key)) ?? (await indexGet(store, 'sku', key));
      if (hit) return hit;
    }
    // Different capitalisation than the stored code: one pass over the rows.
    return await new Promise<PosCatalogRow | null>((resolve, reject) => {
      const request = db.transaction(STORE, 'readonly').objectStore(STORE).getAll();
      request.onsuccess = () => {
        const rows = (request.result || []) as PosCatalogRow[];
        resolve(rows.find((row) => row.barcode.toLowerCase() === wanted || row.sku.toLowerCase() === wanted) || null);
      };
      request.onerror = () => reject(request.error);
    });
  } finally {
    db.close();
  }
}

export async function syncPosPriceLists(companyId: number, customerIds: number[]): Promise<number[]> {
  const response: { data: unknown } = await apiClient.get('/products/pos-price-lists/', {
    params: { customers: customerIds.filter(Boolean).join(',') },
  });
  const page = unwrapData<{ lists?: Array<{ id: number }>; customers?: Array<{ id: number; price_list: number | null }> }>(response.data);
  const ids = (page.lists ?? []).map((row) => row.id);
  localStorage.setItem(`bb_pos_price_lists:${companyId}`, JSON.stringify({
    ids,
    customers: page.customers ?? [],
  }));
  return ids;
}

export function priceListMissing(companyId: number, priceListId: number | null | undefined): boolean {
  if (!priceListId) return false;
  try {
    const raw = localStorage.getItem(`bb_pos_price_lists:${companyId}`);
    const ids = raw ? (JSON.parse(raw) as { ids?: number[] }).ids ?? [] : [];
    return !ids.includes(priceListId);
  } catch {
    return true;
  }
}

export function catalogAgeHours(companyId: number): number | null {
  const raw = localStorage.getItem(`bb_pos_catalog_synced:${companyId}`);
  if (!raw) return null;
  const then = Date.parse(raw);
  if (!Number.isFinite(then)) return null;
  return (Date.now() - then) / 36e5;
}

export function catalogSellBlocked(ageHours: number | null, blockAfter = 72): boolean {
  return ageHours != null && ageHours >= blockAfter;
}
