/**
 * Offline outbox for new customer receipts (Money In).
 *
 * A cashier with no connection can still record cash and cheque receipts. Each is kept on this
 * device under the Idempotency-Key it will be sent with, so a replay creates one receipt however
 * many times the send is attempted. Voids and refunds are never queued: they change books that
 * may have moved since, so they need a live answer.
 *
 * Rules, as built:
 * - The receipt keeps the date the cashier saw (`receiptDate` in the payload). The server still
 *   applies its period gate and the future-date rule when the send arrives.
 * - The receipt number is assigned by the server when the send arrives, so numbers follow arrival
 *   order, not the date the money was taken (as for any back-dated entry).
 * - A send the server refuses for a reason that will not change (the bill was paid meanwhile, the
 *   period closed, the customer was blocked) is not retried forever: it moves to "needs attention"
 *   with the reason, for a person to discard or re-enter.
 * - A send that fails for a connection or server reason stays queued and is tried again.
 */

import type { createReceipt } from '@/api/resources';

type CreatePayload = Parameters<typeof createReceipt>[0];

const DB_NAME = 'bizboard-receipt-outbox';
const STORE = 'receipts';

export type QueuedReceiptStatus = 'queued' | 'conflict';

export interface QueuedReceipt {
  /** The Idempotency-Key. One key, one receipt. */
  id: string;
  companyId: number;
  userId: number;
  payload: CreatePayload;
  customerName: string;
  queuedAt: number;
  status: QueuedReceiptStatus;
  error?: string;
}

/** Only these modes are queued; everything else needs the server to answer now. */
export const OFFLINE_RECEIPT_MODES = ['CASH', 'CHEQUE'] as const;

export function canQueueReceipt(mode: string): boolean {
  return (OFFLINE_RECEIPT_MODES as readonly string[]).includes(mode);
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === 'undefined') {
      reject(new Error('IndexedDB not supported'));
      return;
    }
    const request = indexedDB.open(DB_NAME, 1);
    request.onupgradeneeded = () => {
      request.result.createObjectStore(STORE, { keyPath: 'id' });
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function withStore<T>(mode: IDBTransactionMode, run: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await openDb();
  try {
    return await new Promise<T>((resolve, reject) => {
      const tx = db.transaction(STORE, mode);
      const request = run(tx.objectStore(STORE));
      tx.oncomplete = () => resolve(request.result);
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error);
    });
  } finally {
    db.close();
  }
}

export async function queueReceipt(entry: Omit<QueuedReceipt, 'queuedAt' | 'status'>): Promise<void> {
  if (!canQueueReceipt(String(entry.payload.mode))) {
    throw new Error(`A ${entry.payload.mode} receipt cannot be saved offline.`);
  }
  await withStore('readwrite', (store) => store.put({ ...entry, queuedAt: Date.now(), status: 'queued' }));
}

export async function listQueuedReceipts(companyId: number, userId: number): Promise<QueuedReceipt[]> {
  try {
    const all = await withStore<QueuedReceipt[]>('readonly', (store) => store.getAll());
    return all
      .filter((row) => row.companyId === companyId && row.userId === userId)
      .sort((a, b) => a.queuedAt - b.queuedAt);
  } catch {
    return [];
  }
}

export async function removeQueuedReceipt(id: string): Promise<void> {
  await withStore('readwrite', (store) => store.delete(id));
}

async function updateQueued(id: string, patch: Partial<QueuedReceipt>): Promise<void> {
  const db = await openDb();
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite');
      const store = tx.objectStore(STORE);
      const get = store.get(id);
      get.onsuccess = () => {
        if (get.result) store.put({ ...get.result, ...patch });
      };
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  } finally {
    db.close();
  }
}

/** True when the server answered and said no. False for a lost connection or a server fault. */
export function isDeterministicRefusal(error: unknown): boolean {
  const response = (error as { response?: { status?: number; data?: { error?: { code?: string } } } })?.response;
  const status = response?.status;
  // Another tab (or an earlier attempt) is still sending this very key: not a refusal, try again.
  if (status === 409 && String(response?.data?.error?.code ?? '').toLowerCase() === 'idempotency_in_flight') {
    return false;
  }
  return typeof status === 'number' && status >= 400 && status < 500 && status !== 408 && status !== 429;
}

export interface FlushResult {
  sent: number;
  conflicts: number;
  remaining: number;
}

/**
 * Send every queued receipt of this user, oldest first, each under its own key. Stops at the first
 * connection or server failure (the rest would fail the same way) and leaves it queued.
 */
export async function flushReceiptOutbox(
  companyId: number,
  userId: number,
  send: (payload: CreatePayload, idempotencyKey: string) => Promise<unknown>,
  describe: (error: unknown) => string = (error) => String((error as Error)?.message ?? error),
): Promise<FlushResult> {
  const rows = await listQueuedReceipts(companyId, userId);
  let sent = 0;
  let conflicts = 0;
  let stopped = false;
  for (const row of rows) {
    if (row.status !== 'queued') {
      conflicts += 1;
      continue;
    }
    if (stopped) continue;
    try {
      await send(row.payload, row.id);
      await removeQueuedReceipt(row.id);
      sent += 1;
    } catch (error) {
      if (isDeterministicRefusal(error)) {
        await updateQueued(row.id, { status: 'conflict', error: describe(error) });
        conflicts += 1;
      } else {
        stopped = true;
      }
    }
  }
  const remaining = (await listQueuedReceipts(companyId, userId)).filter((row) => row.status === 'queued').length;
  return { sent, conflicts, remaining };
}

/** Put a refused receipt back in the queue to try again as it is. */
export async function retryQueuedReceipt(id: string): Promise<void> {
  await updateQueued(id, { status: 'queued', error: undefined });
}
