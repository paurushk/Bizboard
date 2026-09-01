import { getErrorMessage, newIdempotencyKey } from '@/api/client';
import type { PaymentMode } from '@/types/domain';

const IDB_NAME = 'bizboard-invoice-outbox';
const IDB_STORE = 'drafts';
const IDB_VERSION = 1;
const LS_PREFIX = 'bizboard:invoice-outbox:v2:';
const LS_V1_PREFIX = 'bizboard:invoice-draft:';

export type OutboxKind = 'invoice' | 'pos' | 'purchase' | 'stock_count' | 'stock_transfer';

export interface InvoiceDraftLine {
  productId: number;
  productName: string;
  sku: string;
  quantity: number;
  unitPrice: number;
  gstRate: number;
  cessRate?: number;
  discountPercent?: number;
  discountAmount?: number;
  serials?: string[];
  supplyType?: string;
  unitName?: string;
}

/** BB-000572: drafts are plaintext in IndexedDB/localStorage on shared POS devices. */
/** BB-000580: this outbox is the sync path. iOS does not guarantee Background Sync. */
export const OUTBOX_PLAINTEXT_WARNING =
  'Offline drafts are stored unencrypted on this device. Sign out clears them. Do not use shared counter logins for sensitive customer data.';

/** UXW2-008: remember dismiss so the warning does not stack every visit when online. */
export const OUTBOX_WARNING_DISMISS_KEY = 'bizboard.dismiss.outboxPlaintext';

/** @deprecated v1 POS shape — still readable for migration. */
export interface InvoiceDraft {
  version: 1;
  customerId: number;
  lines: InvoiceDraftLine[];
  paymentMode: PaymentMode;
  idempotencyKey: string;
  savedAt: string;
}

export interface OutboxDraft {
  version: 2;
  id: string;
  companyId: number;
  userId: number;
  kind: OutboxKind;
  idempotencyKey: string;
  savedAt: string;
  payload: Record<string, unknown>;
  invoiceId?: number | null;
  customerId?: number;
  paymentMode?: PaymentMode;
  lines?: InvoiceDraftLine[];
  pendingCustomerName?: string;
  completeIntent?: boolean;
}

let forceLocalStorage = false;

export function setOutboxStorageMode(mode: 'auto' | 'localStorage'): void {
  forceLocalStorage = mode === 'localStorage';
}

function scopeKey(companyId: number, userId: number): string {
  return `${companyId}:${userId}`;
}

function lsKey(companyId: number, userId: number): string {
  return `${LS_PREFIX}${scopeKey(companyId, userId)}`;
}

function v1Key(companyId: number, userId: number): string {
  return `${LS_V1_PREFIX}${companyId}:${userId}`;
}

function idbAvailable(): boolean {
  if (forceLocalStorage) return false;
  try {
    return typeof indexedDB !== 'undefined';
  } catch {
    return false;
  }
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(IDB_NAME, IDB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(IDB_STORE)) {
        db.createObjectStore(IDB_STORE, { keyPath: 'id' });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error ?? new Error('IndexedDB open failed'));
  });
}

async function idbGetAll(): Promise<OutboxDraft[]> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(IDB_STORE, 'readonly');
    const req = tx.objectStore(IDB_STORE).getAll();
    req.onsuccess = () => resolve((req.result as OutboxDraft[]) ?? []);
    req.onerror = () => reject(req.error ?? new Error('IndexedDB getAll failed'));
  });
}

async function idbPut(draft: OutboxDraft): Promise<void> {
  const db = await openDb();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(IDB_STORE, 'readwrite');
    tx.objectStore(IDB_STORE).put(draft);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error ?? new Error('IndexedDB put failed'));
  });
}

async function idbDelete(id: string): Promise<void> {
  const db = await openDb();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(IDB_STORE, 'readwrite');
    tx.objectStore(IDB_STORE).delete(id);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error ?? new Error('IndexedDB delete failed'));
  });
}

function readLocal(companyId: number, userId: number): OutboxDraft[] {
  try {
    const raw = localStorage.getItem(lsKey(companyId, userId));
    if (!raw) return [];
    const parsed = JSON.parse(raw) as OutboxDraft[];
    return Array.isArray(parsed) ? parsed.filter((d) => d?.version === 2) : [];
  } catch {
    return [];
  }
}

function writeLocal(companyId: number, userId: number, drafts: OutboxDraft[]): void {
  try {
    localStorage.setItem(lsKey(companyId, userId), JSON.stringify(drafts));
  } catch (err) {
    const quota = err instanceof DOMException && (
      err.name === 'QuotaExceededError' || err.code === 22 || err.code === 1014
    );
    if (quota) {
      throw new Error('OUTBOX_STORAGE_FULL');
    }
    throw err;
  }
}

async function scopedIdbDrafts(companyId: number, userId: number): Promise<OutboxDraft[] | null> {
  if (!idbAvailable()) return null;
  try {
    return (await idbGetAll()).filter((d) => d.companyId === companyId && d.userId === userId);
  } catch {
    return null;
  }
}

/** IDB is canonical when it reads; localStorage only supplies drafts IDB never stored. */
async function mergeDurable(companyId: number, userId: number): Promise<OutboxDraft[]> {
  const local = readLocal(companyId, userId);
  const idb = await scopedIdbDrafts(companyId, userId);
  if (!idb) return local;
  const byId = new Map<string, OutboxDraft>();
  for (const draft of idb) byId.set(draft.id, draft);
  for (const draft of local) {
    if (!byId.has(draft.id)) byId.set(draft.id, draft);
  }
  return [...byId.values()];
}

function mirrorNativePrefs(companyId: number, userId: number, drafts: OutboxDraft[]): void {
  void import('@/lib/native')
    .then(({ isNative, prefsSet }) => {
      if (isNative()) {
        return prefsSet(lsKey(companyId, userId), JSON.stringify(drafts), { skipLocal: true });
      }
      return undefined;
    })
    .catch(() => undefined);
}

function migrateV1IfNeeded(companyId: number, userId: number): OutboxDraft[] {
  try {
    const raw = localStorage.getItem(v1Key(companyId, userId));
    if (!raw) return [];
    const parsed = JSON.parse(raw) as InvoiceDraft;
    if (parsed.version !== 1 || !Array.isArray(parsed.lines)) return [];
    const idempotencyKey = parsed.idempotencyKey || newIdempotencyKey();
    const migrated: OutboxDraft = {
      version: 2,
      id: `${scopeKey(companyId, userId)}:${idempotencyKey}`,
      companyId,
      userId,
      kind: 'pos',
      idempotencyKey,
      savedAt: parsed.savedAt || new Date().toISOString(),
      payload: {
        customer: parsed.customerId,
        items: parsed.lines,
        paymentMode: parsed.paymentMode,
      },
      customerId: parsed.customerId,
      paymentMode: parsed.paymentMode,
      lines: parsed.lines,
    };
    const existing = readLocal(companyId, userId).filter((d) => d.idempotencyKey !== idempotencyKey);
    writeLocal(companyId, userId, [...existing, migrated]);
    if (idbAvailable()) {
      void idbPut(migrated).catch(() => undefined);
    }
    localStorage.removeItem(v1Key(companyId, userId));
    return [migrated];
  } catch {
    return [];
  }
}

export async function listDrafts(companyId: number, userId: number): Promise<OutboxDraft[]> {
  const migrated = migrateV1IfNeeded(companyId, userId);
  const idb = await scopedIdbDrafts(companyId, userId);
  const local = readLocal(companyId, userId);
  const byId = new Map<string, OutboxDraft>();
  if (idb) {
    for (const draft of idb) byId.set(draft.id, draft);
    for (const draft of local) {
      if (!byId.has(draft.id)) byId.set(draft.id, draft);
    }
  } else {
    for (const draft of local) byId.set(draft.id, draft);
    try {
      const { isNative, prefsGet } = await import('@/lib/native');
      if (isNative()) {
        const raw = await prefsGet(lsKey(companyId, userId));
        if (raw) {
          const parsed = JSON.parse(raw) as OutboxDraft[];
          if (Array.isArray(parsed)) {
            for (const draft of parsed) {
              if (draft?.version === 2 && !byId.has(draft.id)) byId.set(draft.id, draft);
            }
          }
        }
      }
    } catch {
      /* native prefs are a fallback only when IDB is unavailable */
    }
  }
  for (const draft of migrated) {
    if (!byId.has(draft.id)) byId.set(draft.id, draft);
  }
  return [...byId.values()].sort(
    (a, b) => new Date(a.savedAt).getTime() - new Date(b.savedAt).getTime(),
  );
}

export async function enqueueDraft(
  companyId: number,
  userId: number,
  input: {
    kind: OutboxKind;
    payload: Record<string, unknown>;
    idempotencyKey?: string;
    invoiceId?: number | null;
    customerId?: number;
    paymentMode?: PaymentMode;
    lines?: InvoiceDraftLine[];
    pendingCustomerName?: string;
    completeIntent?: boolean;
  },
): Promise<OutboxDraft> {
  const idempotencyKey = input.idempotencyKey || newIdempotencyKey();
  const draft: OutboxDraft = {
    version: 2,
    id: `${scopeKey(companyId, userId)}:${idempotencyKey}`,
    companyId,
    userId,
    kind: input.kind,
    idempotencyKey,
    savedAt: new Date().toISOString(),
    payload: input.payload,
    invoiceId: input.invoiceId ?? null,
    customerId: input.customerId,
    paymentMode: input.paymentMode,
    lines: input.lines,
    pendingCustomerName: input.pendingCustomerName,
    completeIntent: input.completeIntent,
  };

  const existing = (await mergeDurable(companyId, userId)).filter(
    (d) => d.idempotencyKey !== idempotencyKey,
  );
  const next = [...existing, draft];
  let persisted = false;
  if (idbAvailable()) {
    try {
      await idbPut(draft);
      persisted = true;
    } catch {
      persisted = false;
    }
  }
  try {
    writeLocal(companyId, userId, next);
    persisted = true;
  } catch (err) {
    if (!persisted) throw err;
  }
  mirrorNativePrefs(companyId, userId, next);
  if (!persisted) {
    throw new Error('OUTBOX_STORAGE_FULL');
  }
  return draft;
}

export async function removeDraft(
  companyId: number,
  userId: number,
  idempotencyKey: string,
): Promise<void> {
  const id = `${scopeKey(companyId, userId)}:${idempotencyKey}`;
  if (idbAvailable()) {
    await idbDelete(id);
  }
  writeLocal(
    companyId,
    userId,
    readLocal(companyId, userId).filter((d) => d.idempotencyKey !== idempotencyKey),
  );
  mirrorNativePrefs(companyId, userId, await mergeDurable(companyId, userId));
}

export async function clearAllDrafts(companyId: number, userId: number): Promise<void> {
  const drafts = await listDrafts(companyId, userId);
  await Promise.all(drafts.map((d) => removeDraft(companyId, userId, d.idempotencyKey)));
  localStorage.removeItem(lsKey(companyId, userId));
  localStorage.removeItem(v1Key(companyId, userId));
  mirrorNativePrefs(companyId, userId, []);
}

export function assertFlushableLine(line: InvoiceDraftLine): void {
  if ((line.cessRate ?? 0) < 0) {
    throw new Error('Invalid cess rate on outbox line');
  }
}

export async function flushOutbox(
  companyId: number,
  userId: number,
  sendFn: (draft: OutboxDraft) => Promise<void>,
  filter?: (draft: OutboxDraft) => boolean,
): Promise<{ flushed: number; failed: number; errors: string[] }> {
  const drafts = (await listDrafts(companyId, userId)).filter(
    (d) => isFlushableDraft(d) && (filter ? filter(d) : true),
  );
  let flushed = 0;
  let failed = 0;
  const errors: string[] = [];
  for (const draft of drafts) {
    try {
      for (const line of draft.lines ?? []) assertFlushableLine(line);
      await sendFn(draft);
      await removeDraft(companyId, userId, draft.idempotencyKey);
      flushed += 1;
    } catch (err) {
      failed += 1;
      errors.push(getErrorMessage(err));
    }
  }
  return { flushed, failed, errors };
}

/** POS compatibility wrappers over the v2 outbox (localStorage-first for sync callers). */
export function saveInvoiceDraft(
  companyId: number,
  userId: number,
  draft: Omit<InvoiceDraft, 'version' | 'savedAt' | 'idempotencyKey'> & {
    idempotencyKey?: string;
  },
): InvoiceDraft {
  const full: InvoiceDraft = {
    version: 1,
    customerId: draft.customerId,
    lines: draft.lines,
    paymentMode: draft.paymentMode,
    idempotencyKey: draft.idempotencyKey ?? newIdempotencyKey(),
    savedAt: new Date().toISOString(),
  };
  void enqueueDraft(companyId, userId, {
    kind: 'pos',
    payload: {
      customer: full.customerId,
      items: full.lines,
      paymentMode: full.paymentMode,
    },
    idempotencyKey: full.idempotencyKey,
    customerId: full.customerId,
    paymentMode: full.paymentMode,
    lines: full.lines,
  });
  return full;
}

export function loadInvoiceDraft(companyId: number, userId: number): InvoiceDraft | null {
  const migrated = migrateV1IfNeeded(companyId, userId);
  const local = [...readLocal(companyId, userId), ...migrated];
  const pos = [...local].reverse().find((d) => d.kind === 'pos');
  if (!pos || !pos.lines || pos.customerId == null || !pos.paymentMode) return null;
  return {
    version: 1,
    customerId: pos.customerId,
    lines: pos.lines,
    paymentMode: pos.paymentMode,
    idempotencyKey: pos.idempotencyKey,
    savedAt: pos.savedAt,
  };
}

export async function loadInvoiceDraftAsync(
  companyId: number,
  userId: number,
): Promise<InvoiceDraft | null> {
  const drafts = await listDrafts(companyId, userId);
  const pos = [...drafts].reverse().find((d) => d.kind === 'pos');
  if (!pos || !pos.lines || pos.customerId == null || !pos.paymentMode) return null;
  return {
    version: 1,
    customerId: pos.customerId,
    lines: pos.lines,
    paymentMode: pos.paymentMode,
    idempotencyKey: pos.idempotencyKey,
    savedAt: pos.savedAt,
  };
}

export async function clearInvoiceDraft(companyId: number, userId: number): Promise<void> {
  const drafts = await listDrafts(companyId, userId);
  await Promise.all(
    drafts.filter((d) => d.kind === 'pos').map((d) => removeDraft(companyId, userId, d.idempotencyKey)),
  );
  localStorage.removeItem(v1Key(companyId, userId));
}

export const PURCHASE_AUTOSAVE_KEY = 'purchase-editor-draft';

export function isFlushableDraft(draft: OutboxDraft): boolean {
  return draft.idempotencyKey !== PURCHASE_AUTOSAVE_KEY;
}
export async function savePurchaseDraft(
  companyId: number,
  userId: number,
  payload: Record<string, unknown>,
  idempotencyKey?: string,
): Promise<OutboxDraft> {
  return enqueueDraft(companyId, userId, {
    kind: 'purchase',
    payload,
    idempotencyKey: idempotencyKey || PURCHASE_AUTOSAVE_KEY,
  });
}

export async function loadPurchaseDraft(
  companyId: number,
  userId: number,
): Promise<OutboxDraft | null> {
  const drafts = await listDrafts(companyId, userId);
  return drafts.find((d) => d.kind === 'purchase' && d.idempotencyKey === PURCHASE_AUTOSAVE_KEY) ?? null;
}

export async function clearPurchaseDraft(companyId: number, userId: number): Promise<void> {
  await removeDraft(companyId, userId, PURCHASE_AUTOSAVE_KEY);
}
