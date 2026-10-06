/** Company- and user-scoped drafts that survive a reload. Not the offline outbox. */

export const DRAFT_VERSION = 1;
export const DRAFT_TTL_MS = 36 * 60 * 60 * 1000;
export const LEGACY_POS_CART_PREFIX = 'bizboard:pos-active-cart:';

export type DraftKind = 'sales-invoice' | 'purchase-bill' | 'pos-sessions';

export type StoredDraft<T> = {
  version: typeof DRAFT_VERSION;
  savedAt: string;
  payload: T;
};

export type DraftRead<T> =
  | { ok: true; payload: T; savedAt: string }
  | { ok: false; reason: 'missing' | 'expired' | 'version' | 'corrupt' };

export type DraftWrite = { ok: true } | { ok: false; reason: 'quota' };

export function draftKey(companyId: number, userId: number, kind: DraftKind): string {
  return `bizboard:draft:v1:${companyId}:${userId}:${kind}`;
}

export function legacyPosCartKey(companyId: number): string {
  return `${LEGACY_POS_CART_PREFIX}${companyId}`;
}

const KINDS: DraftKind[] = ['sales-invoice', 'purchase-bill', 'pos-sessions'];

function storage(): Storage | null {
  try {
    return typeof localStorage === 'undefined' ? null : localStorage;
  } catch {
    return null;
  }
}

export function readDraft<T>(
  companyId: number,
  userId: number,
  kind: DraftKind,
  now = Date.now(),
): DraftRead<T> {
  const store = storage();
  if (!store || !companyId || !userId) return { ok: false, reason: 'missing' };
  let raw: string | null;
  try {
    raw = store.getItem(draftKey(companyId, userId, kind));
  } catch {
    return { ok: false, reason: 'missing' };
  }
  if (!raw) return { ok: false, reason: 'missing' };
  let parsed: StoredDraft<T> | null = null;
  try {
    parsed = JSON.parse(raw) as StoredDraft<T>;
  } catch {
    store.removeItem(draftKey(companyId, userId, kind));
    return { ok: false, reason: 'corrupt' };
  }
  if (!parsed || parsed.version !== DRAFT_VERSION || typeof parsed.savedAt !== 'string') {
    store.removeItem(draftKey(companyId, userId, kind));
    return { ok: false, reason: 'version' };
  }
  const saved = Date.parse(parsed.savedAt);
  if (!Number.isFinite(saved) || now - saved > DRAFT_TTL_MS) {
    store.removeItem(draftKey(companyId, userId, kind));
    return { ok: false, reason: 'expired' };
  }
  return { ok: true, payload: parsed.payload, savedAt: parsed.savedAt };
}

export function writeDraft<T>(companyId: number, userId: number, kind: DraftKind, payload: T): DraftWrite {
  const store = storage();
  if (!store || !companyId || !userId) return { ok: false, reason: 'quota' };
  const body: StoredDraft<T> = { version: DRAFT_VERSION, savedAt: new Date().toISOString(), payload };
  try {
    store.setItem(draftKey(companyId, userId, kind), JSON.stringify(body));
    return { ok: true };
  } catch {
    return { ok: false, reason: 'quota' };
  }
}

export function removeDraft(companyId: number, userId: number, kind: DraftKind): void {
  const store = storage();
  if (!store || !companyId || !userId) return;
  try {
    store.removeItem(draftKey(companyId, userId, kind));
  } catch {
    /* private mode */
  }
}

/** Logout on a shared counter PC. Also drops the pre-user cart key. */
export function clearForUser(companyId: number, userId: number): void {
  const store = storage();
  if (!store) return;
  if (companyId && userId) {
    for (const kind of KINDS) removeDraft(companyId, userId, kind);
  }
  if (companyId) {
    try {
      store.removeItem(legacyPosCartKey(companyId));
    } catch {
      /* ignore */
    }
  }
}
