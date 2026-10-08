import 'fake-indexeddb/auto';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const get = vi.fn();
vi.mock('@/api/client', () => ({
  apiClient: { get: (...args: unknown[]) => get(...args) },
  unwrapData: <T,>(data: unknown) => data as T,
}));

const { findLocalCatalog, syncPosCatalog } = await import('./posCatalog');

const COMPANY = 7;

function row(id: number, extra: Record<string, unknown> = {}) {
  return {
    id,
    name: `Item ${id}`,
    sku: `SKU-${id}`,
    barcode: `890000${id}`,
    price: '10.00',
    gst: '18',
    hsn: '1234',
    unit: 'PCS',
    trackBatch: false,
    trackSerial: false,
    productType: 'GOODS',
    ...extra,
  };
}

beforeEach(async () => {
  get.mockReset();
  localStorage.clear();
  indexedDB.deleteDatabase(`bizboard-pos-catalog-${COMPANY}`);
});

describe('offline catalogue sync', () => {
  it('reads camelCase flags and pages through the cursor', async () => {
    get
      .mockResolvedValueOnce({ data: { results: [row(1, { trackBatch: true })], nextCursor: 1 } })
      .mockResolvedValueOnce({ data: { results: [row(2)], nextCursor: null } });
    const count = await syncPosCatalog(COMPANY);
    expect(count).toBe(2);
    expect(get).toHaveBeenCalledTimes(2);
    const hit = await findLocalCatalog(COMPANY, 'SKU-1');
    expect(hit?.trackBatch).toBe(true);
  });

  it('a full sync drops products that are no longer returned', async () => {
    get.mockResolvedValueOnce({ data: { results: [row(1), row(2)], nextCursor: null } });
    await syncPosCatalog(COMPANY);
    expect(await findLocalCatalog(COMPANY, 'SKU-2')).not.toBeNull();
    // A week later the stored stamp is stale, so this is a full sync again, and 2 is gone.
    localStorage.setItem(`bb_pos_catalog_synced:${COMPANY}`, new Date(Date.now() - 8 * 24 * 36e5).toISOString());
    get.mockResolvedValueOnce({ data: { results: [row(1)], nextCursor: null } });
    await syncPosCatalog(COMPANY);
    expect(await findLocalCatalog(COMPANY, 'SKU-2')).toBeNull();
    expect(await findLocalCatalog(COMPANY, 'SKU-1')).not.toBeNull();
  });

  it('a delta sync asks only for changes and applies removals', async () => {
    get.mockResolvedValueOnce({ data: { results: [row(1), row(2)], nextCursor: null } });
    await syncPosCatalog(COMPANY);
    get.mockResolvedValueOnce({ data: { results: [row(3)], deleted_ids: [2], next_cursor: null } });
    await syncPosCatalog(COMPANY);
    const params = get.mock.calls[1][1].params as { updated_after?: string };
    expect(params.updated_after).toBeTruthy();
    expect(await findLocalCatalog(COMPANY, 'SKU-2')).toBeNull();
    expect(await findLocalCatalog(COMPANY, 'SKU-3')).not.toBeNull();
    expect(await findLocalCatalog(COMPANY, 'SKU-1')).not.toBeNull();
  });

  it('finds a code by barcode, by SKU, and with different capitalisation', async () => {
    get.mockResolvedValueOnce({ data: { results: [row(5, { sku: 'Abc-5' })], nextCursor: null } });
    await syncPosCatalog(COMPANY);
    expect((await findLocalCatalog(COMPANY, '8900005'))?.id).toBe(5);
    expect((await findLocalCatalog(COMPANY, 'Abc-5'))?.id).toBe(5);
    expect((await findLocalCatalog(COMPANY, 'ABC-5'))?.id).toBe(5);
    expect(await findLocalCatalog(COMPANY, 'missing')).toBeNull();
  });

  it('keeps the old stamp when a sync fails, so the next one covers the gap', async () => {
    get.mockResolvedValueOnce({ data: { results: [row(1)], nextCursor: null } });
    await syncPosCatalog(COMPANY);
    const before = localStorage.getItem(`bb_pos_catalog_synced:${COMPANY}`);
    get.mockRejectedValueOnce(new Error('offline'));
    await expect(syncPosCatalog(COMPANY)).rejects.toThrow('offline');
    expect(localStorage.getItem(`bb_pos_catalog_synced:${COMPANY}`)).toBe(before);
  });
});
