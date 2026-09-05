// F1-008: the IndexedDB path (idbAvailable() === true) was completely
// untested before this file -- every existing test in invoiceDraftCache.test.ts
// forces setOutboxStorageMode('localStorage'), so the IDB merge, migration,
// and flushOutbox-locking logic never actually ran under test. fake-indexeddb
// gives jsdom a real (in-memory) IndexedDB implementation to exercise it.
import 'fake-indexeddb/auto';
import { beforeEach, describe, expect, it } from 'vitest';
import {
  clearAllDrafts,
  enqueueDraft,
  flushOutbox,
  listDrafts,
  loadInvoiceDraft,
  saveInvoiceDraft,
  setOutboxStorageMode,
  type OutboxDraft,
} from './invoiceDraftCache';

// Mirrors the private constants in invoiceDraftCache.ts (not exported).
const IDB_NAME = 'bizboard-invoice-outbox';
const IDB_STORE = 'drafts';
const IDB_VERSION = 1;
const LS_PREFIX = 'bizboard:invoice-outbox:v2:';
const LS_V1_PREFIX = 'bizboard:invoice-draft:';
const USER_ID = 9;

function lsKey(companyId: number): string {
  return `${LS_PREFIX}${companyId}:${USER_ID}`;
}

function v1Key(companyId: number): string {
  return `${LS_V1_PREFIX}${companyId}:${USER_ID}`;
}

/** Write a draft directly into IndexedDB, bypassing the module under test --
 * used to construct a state IDB knows about that localStorage does not.
 * Closes its own connection so it never blocks a later open in the same
 * test run (fake-indexeddb enforces the same connection-lifecycle rules a
 * real browser does). */
function putRawIdbDraft(draft: OutboxDraft): Promise<void> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(IDB_NAME, IDB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(IDB_STORE)) {
        db.createObjectStore(IDB_STORE, { keyPath: 'id' });
      }
    };
    req.onsuccess = () => {
      const db = req.result;
      const tx = db.transaction(IDB_STORE, 'readwrite');
      tx.objectStore(IDB_STORE).put(draft);
      tx.oncomplete = () => {
        db.close();
        resolve();
      };
      tx.onerror = () => {
        db.close();
        reject(tx.error);
      };
    };
    req.onerror = () => reject(req.error);
  });
}

// Each test uses its own companyId so drafts never collide across tests --
// simpler and more robust than tearing down the shared fake-indexeddb
// database between tests (deleteDatabase blocks on any open connection,
// including ones the module under test itself never explicitly closes,
// which is realistic browser behaviour but not worth fighting in a test).
let nextCompanyId = 9000;
function freshCompanyId(): number {
  nextCompanyId += 1;
  return nextCompanyId;
}

describe('invoice outbox v2 (IndexedDB path)', () => {
  beforeEach(() => {
    localStorage.clear();
    setOutboxStorageMode('auto');
  });

  it('merges a draft that exists only in IDB with one that exists only in localStorage', async () => {
    const companyId = freshCompanyId();
    // Only in IDB (localStorage was never written for this one).
    await putRawIdbDraft({
      version: 2,
      id: `${companyId}:${USER_ID}:idb-only`,
      companyId,
      userId: USER_ID,
      kind: 'invoice',
      idempotencyKey: 'idb-only',
      savedAt: new Date().toISOString(),
      payload: { customer: 1 },
    });
    // Only in localStorage (never written to IDB).
    localStorage.setItem(
      lsKey(companyId),
      JSON.stringify([
        {
          version: 2,
          id: `${companyId}:${USER_ID}:local-only`,
          companyId,
          userId: USER_ID,
          kind: 'invoice',
          idempotencyKey: 'local-only',
          savedAt: new Date().toISOString(),
          payload: { customer: 2 },
        },
      ]),
    );

    const listed = await listDrafts(companyId, USER_ID);
    const keys = listed.map((d) => d.idempotencyKey).sort();
    expect(keys).toEqual(['idb-only', 'local-only']);
  });

  it('IDB entries win over a divergent localStorage copy of the same draft', async () => {
    const companyId = freshCompanyId();
    await putRawIdbDraft({
      version: 2,
      id: `${companyId}:${USER_ID}:dup`,
      companyId,
      userId: USER_ID,
      kind: 'invoice',
      idempotencyKey: 'dup',
      savedAt: new Date().toISOString(),
      payload: { note: 'from-idb' },
    });
    localStorage.setItem(
      lsKey(companyId),
      JSON.stringify([
        {
          version: 2,
          id: `${companyId}:${USER_ID}:dup`,
          companyId,
          userId: USER_ID,
          kind: 'invoice',
          idempotencyKey: 'dup',
          savedAt: new Date().toISOString(),
          payload: { note: 'stale-local-copy' },
        },
      ]),
    );

    const listed = await listDrafts(companyId, USER_ID);
    expect(listed).toHaveLength(1);
    expect(listed[0]?.payload.note).toBe('from-idb');
  });

  it('enqueueDraft still succeeds via localStorage when IDB.open fails', async () => {
    const companyId = freshCompanyId();
    const originalOpen = indexedDB.open.bind(indexedDB);
    // @ts-expect-error -- deliberately break IDB.open for this one test.
    indexedDB.open = () => {
      const req: Partial<IDBOpenDBRequest> = {};
      queueMicrotask(() => req.onerror?.(new Event('error') as never));
      return req as IDBOpenDBRequest;
    };
    try {
      const saved = await enqueueDraft(companyId, USER_ID, {
        kind: 'invoice',
        payload: { customer: 3 },
        idempotencyKey: 'idb-down',
      });
      expect(saved.idempotencyKey).toBe('idb-down');
      const listed = await listDrafts(companyId, USER_ID);
      expect(listed.map((d) => d.idempotencyKey)).toEqual(['idb-down']);
    } finally {
      indexedDB.open = originalOpen;
    }
  });

  it('migrateV1IfNeeded preserves a pre-existing v2 draft instead of clobbering it', async () => {
    const companyId = freshCompanyId();
    localStorage.setItem(
      lsKey(companyId),
      JSON.stringify([
        {
          version: 2,
          id: `${companyId}:${USER_ID}:existing-v2`,
          companyId,
          userId: USER_ID,
          kind: 'pos',
          idempotencyKey: 'existing-v2',
          savedAt: new Date().toISOString(),
          payload: {},
          customerId: 5,
          paymentMode: 'CASH',
          lines: [],
        },
      ]),
    );
    localStorage.setItem(
      v1Key(companyId),
      JSON.stringify({
        version: 1,
        customerId: 7,
        lines: [
          {
            productId: 1, productName: 'Legacy', sku: 'L1', quantity: 1,
            unitPrice: 50, gstRate: 0,
          },
        ],
        paymentMode: 'UPI',
        idempotencyKey: 'legacy-v1',
        savedAt: new Date().toISOString(),
      }),
    );

    const listed = await listDrafts(companyId, USER_ID);
    const keys = listed.map((d) => d.idempotencyKey).sort();
    expect(keys).toEqual(['existing-v2', 'legacy-v1']);
    // The v1 key is consumed on migration, not left to re-migrate every call.
    expect(localStorage.getItem(v1Key(companyId))).toBeNull();

    const legacy = loadInvoiceDraft(companyId, USER_ID);
    expect(legacy?.customerId).toBe(7);
  });

  it('a second concurrent flushOutbox call does not re-send the same draft', async () => {
    const companyId = freshCompanyId();
    await enqueueDraft(companyId, USER_ID, {
      kind: 'pos',
      payload: {},
      idempotencyKey: 'concurrent-1',
      customerId: 1,
      paymentMode: 'CASH',
      lines: [],
    });
    let calls = 0;
    const sendFn = async () => {
      calls += 1;
      await new Promise((r) => setTimeout(r, 20));
    };

    const [first, second] = await Promise.all([
      flushOutbox(companyId, USER_ID, sendFn),
      flushOutbox(companyId, USER_ID, sendFn),
    ]);

    // Exactly one of the two concurrent calls did the work; the other saw the
    // lock held and returned immediately -- the draft is sent (and removed)
    // exactly once, not twice.
    expect(calls).toBe(1);
    expect(first.flushed + second.flushed).toBe(1);
    expect(await listDrafts(companyId, USER_ID)).toHaveLength(0);
  });

  it('clearAllDrafts removes drafts stored in IDB, not just localStorage', async () => {
    const companyId = freshCompanyId();
    await enqueueDraft(companyId, USER_ID, {
      kind: 'invoice',
      payload: {},
      idempotencyKey: 'to-wipe',
    });
    expect(await listDrafts(companyId, USER_ID)).toHaveLength(1);

    await clearAllDrafts(companyId, USER_ID);
    expect(await listDrafts(companyId, USER_ID)).toHaveLength(0);

    // Saving again afterward must not resurrect the wiped draft via a stale
    // IDB row that clearAllDrafts missed.
    saveInvoiceDraft(companyId, USER_ID, { customerId: 1, lines: [], paymentMode: 'CASH' });
    const listed = await listDrafts(companyId, USER_ID);
    expect(listed.filter((d) => d.idempotencyKey === 'to-wipe')).toHaveLength(0);
  });
});
